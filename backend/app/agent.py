"""cookGPT Agent(LangGraph):意图解析 → 策略检索 → 搭配审核(可重试)→ 最终生成。

图结构:
                    ┌─ chitchat ───────────> chat ────────────> END   (寒暄/闲聊,不检索)
    parse ──────────┼─ preference_statement ┬ re_recommend ──> retrieve → critique ─(通过/耗尽)──> generate → END
                    │                       └ 否则 ──────────> acknowledge ──> END  (确认已记忌口)
                    └─ recipe_request ──────> retrieve → critique ─(通过/耗尽)──> generate → END
                                                   │ 未通过且未耗尽
                                                   └────────────> retrieve   (带审核反馈重新检索)

- parse 先做意图分类 + 提取用户画像增量(忌口/口味,跨会话持久化):
  寒暄闲聊走 chat 旁路;陈述偏好且上文刚推过菜(re_recommend)则带上
  新忌口重新检索;只是回答助手提问则 acknowledge 确认即可。
- 画像(dietary_excludes/taste_prefs)由 profile 模块按用户持久化,
  检索的忌口过滤 = 画像忌口 ∪ 本轮忌口,生成时也带上画像。
- parse/retrieve/critique 是同步节点;chat/acknowledge/generate 返回
  流式生成器,由接口层逐段推给前端,保住流式体验。
- 审核重试上限 MAX_RETRIES 防止死循环。
"""

import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from backend.app import profile as user_profile
from backend.app import rag
from backend.app.llm import complete, stream
from backend.app.tools import search_recipes_tool

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # 审核不通过时,最多带着反馈重新检索的次数

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    user_input: str  # 用户原始输入
    history: list[dict]  # 多轮对话历史(最近几轮)
    profile: dict  # 用户饮食画像(本轮开始时,从库读入)
    profile_update: dict  # parse 提取的画像增量(接口层负责落库)
    intent: str  # recipe_request / preference_statement / chitchat
    re_recommend: bool  # 偏好陈述且上文刚推过菜 -> 带新忌口重新检索
    parsed_constraints: dict  # 第一步 Parser 解析出的 JSON 约束
    retrieved_recipes: list[dict]  # 第二步检索到的候选菜谱(完整信息)
    critic_feedback: str  # 第三步 Critic 的审核意见
    is_approved: bool  # 审核是否通过
    retry_count: int  # 重试次数(防止死循环)
    final_menu: list[dict]  # 审核通过的菜单
    final_response: Any  # 最终输出:流式生成器(接口层消费)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PARSE_PROMPT = """把用户的消息解析成结构化意图、菜谱检索约束,并提取用户画像增量(忌口/口味偏好)。

输出 JSON(不要输出其他内容):
{
  "intent": "recipe_request | preference_statement | chitchat",
  "search_query": "改写后的检索词(描述想吃的菜品/口味/场景,25 字以内)",
  "dietary": ["辛辣", "海鲜", ...],
  "notes": "其他要求摘要:人数/场合/荤素搭配/口味偏好等,没有则写 无",
  "profile_update": {
    "add_excludes": ["辛辣", "海鲜", ...],
    "remove_excludes": [],
    "add_prefs": [],
    "remove_prefs": [],
    "notes": ""
  },
  "re_recommend": false
}

规则:
- intent 判定:
  * 用户在咨询菜谱/饮食(推荐、做法、忌口、食材、养生食疗等)→ "recipe_request"
  * 用户在陈述/回答忌口与口味偏好,如"我不喜欢吃辣"、"太油了"、"我喜欢清淡的" → "preference_statement"
  * 寒暄("你好"、"在吗")、道谢、闲聊、与饮食无关的问题 → "chitchat"
- profile_update:用户明确表达的长期忌口/口味都要提取;add_* 是新表达的,remove_* 是明确撤销的(如"我现在能吃辣了"要 remove_excludes=["辛辣"]);add_excludes 只从 ["辛辣", "海鲜"] 中选;add_prefs/remove_prefs 用简短词(如"清淡"、"川味"、"甜口");notes 填画像备注的变化,无变化留空;没有任何变化时所有字段留空
- re_recommend:仅当 intent="preference_statement" 且【上文助手刚推荐过菜/菜单、用户对此表达不满或提出新忌口】时为 true;助手在询问忌口/口味时用户的回答为 false
- re_recommend=true 时,search_query 写成"基于上文推荐、排除新忌口后的检索词"
- dietary 只从 ["辛辣", "海鲜"] 中选,是用户【不能吃】的;用户【想吃】的(如"想吃辣")不要放进去;没有忌口时返回 []
- 口语化需求转成菜品/做法描述:如"来大姨妈了"→"温补暖身汤"、"感冒了"→"清淡易消化"、"朋友聚餐"→"荤素搭配宴客菜"""

CRITIQUE_PROMPT = """你是 cookGPT 的主厨兼营养师,审核「为满足用户需求检索出的候选菜谱」。

用户需求:{user_input}
解析出的约束:{constraints}
候选菜谱:{recipes}

审核标准:
1. 忌口硬约束:凡与用户忌口冲突的菜(如用户不吃辣,候选带"辛辣"忌口标记)绝不能入选,出现即判不通过
2. 需求匹配:菜谱是否符合场景/人数/荤素搭配等要求;用户明确要求荤素搭配(如"要荤菜和素菜")而菜单只有荤或只有素时,必须判不通过,feedback 指出"需要补充素菜"或"需要补充荤菜"
3. 多样性:同类菜只保留一道

输出 JSON(不要输出其他内容):
{"is_pass": true/false, "feedback": "不通过时的具体改进意见,给检索步骤用(如:太油腻了,要清淡做法;通过时为空字符串)", "menu": [{"recipe_id": 123, "name": "菜名", "reason": "入选理由(结合用户需求)"}]}

menu 只从候选菜谱里选,recipe_id 必须是候选菜谱的 id;通过时选 1-3 道最合适的。"""

CHAT_PROMPT = """你是 cookGPT,一位亲切的 AI 私厨助手。用户的消息与菜谱咨询无关(寒暄、道谢、闲聊、其他问题)。

要求:
1. 简短友好地回应,一两句话即可,不要啰嗦
2. 自然地把话题引导回饮食:问问用户想吃什么、有什么忌口或场景
3. 不要推荐具体菜谱,不要编造食材和步骤
4. 中文"""

ACKNOWLEDGE_PROMPT = """你是 cookGPT,一位亲切的 AI 私厨助手。用户刚刚陈述了忌口或口味偏好,系统已记入他的饮食画像。

要求:
1. 用一两句话确认已记住,复述关键点(如"好嘞,记下你不吃辣了")
2. 如果画像里有其他已有偏好,可以顺带提一句(如"之前记着你喜欢清淡的")
3. 自然引导下一步:问用户想吃什么,或直接建议按新忌口推荐几道菜
4. 不要展开推荐具体菜谱,不要编造食材和步骤
5. 中文"""

GENERATE_PROMPT = """你是 cookGPT,一位专业又亲切的 AI 私厨,根据主厨审核通过的菜单为用户生成最终回答。

要求:
1. 回答带温度,先说明推荐逻辑(这些菜为什么适合用户的需求)
2. 每道菜给出食材和步骤(步骤按顺序编号),不要编造菜谱中不存在的内容
3. 推荐的菜带忌口标记(海鲜/辛辣/麸质等)时,简要提示一句
4. 严格尊重用户画像里的忌口与口味偏好:忌口菜绝不可入选,措辞上贴合偏好
5. 菜单为空或不足以满足需求时,基于常识给出饮食建议,并明确说明「菜谱库中未找到完全匹配的菜谱,以下为一般建议」
6. 简洁友好的中文"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _parse_json(raw: str) -> dict:
    """LLM 输出的 JSON 解析:容忍 markdown 代码块与前后缀杂文。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


# ---------------------------------------------------------------------------
# 节点
# ---------------------------------------------------------------------------


def parse_intent_node(state: AgentState) -> dict:
    """节点 1:意图解析 + 画像增量提取,user_input -> constraints/profile_update。"""
    history = state.get("history", [])[-4:]
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history) or "无"
    messages = [
        {"role": "system", "content": PARSE_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户饮食画像:\n{json.dumps(state['profile'], ensure_ascii=False)}\n\n"
                f"对话历史:\n{history_text}\n\n"
                f"当前消息:\n{state['user_input']}"
            ),
        },
    ]
    try:
        constraints = _parse_json(complete(messages, max_tokens=800))
    except Exception:
        logger.warning("意图解析失败,按菜谱请求兜底", exc_info=True)
        constraints = {
            "intent": "recipe_request",
            "search_query": state["user_input"],
            "dietary": [],
            "notes": "无",
            "profile_update": {},
            "re_recommend": False,
        }
    profile_update = constraints.get("profile_update") or {}
    # 节点内先合并出本轮生效的画像(检索/生成用);落库由接口层做,避免节点重复写
    merged = user_profile.merge_profile(state["profile"], profile_update)
    return {
        "parsed_constraints": constraints,
        "intent": constraints.get("intent", "recipe_request"),
        "re_recommend": bool(constraints.get("re_recommend", False)),
        "profile_update": profile_update,
        "profile": merged,
        "retry_count": 0,
    }


def chat_node(state: AgentState) -> dict:
    """旁路节点:寒暄/闲聊/无关问题,不调 RAG,直接大模型简单回应。"""
    history = state.get("history", [])[-4:]
    messages = [{"role": "system", "content": CHAT_PROMPT}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": state["user_input"]})

    def chat_stream():
        yield from stream(messages, max_tokens=300)

    return {"final_response": chat_stream()}


def acknowledge_node(state: AgentState) -> dict:
    """旁路节点:确认已记录用户的忌口/口味偏好,不检索。"""
    messages = [
        {"role": "system", "content": ACKNOWLEDGE_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户当前消息:{state['user_input']}\n"
                f"更新后的画像:{json.dumps(state['profile'], ensure_ascii=False)}"
            ),
        },
    ]

    def ack_stream():
        yield from stream(messages, max_tokens=200)

    return {"final_response": ack_stream()}


def retrieve_recipes_node(state: AgentState) -> dict:
    """节点 2:策略检索。忌口过滤 = 画像忌口 ∪ 本轮忌口;有 Critic 反馈则重新检索。"""
    constraints = state["parsed_constraints"]
    feedback = state.get("critic_feedback", "")
    # 画像忌口跨轮持续生效:用户上一轮说过"不吃辣",这一轮不重说也过滤
    dietary = list(state.get("profile", {}).get("dietary_excludes") or [])
    dietary += constraints.get("dietary", [])
    recipes = search_recipes_tool.invoke(
        {
            "query": constraints.get("search_query", state["user_input"]),
            "dietary": [d for d in dict.fromkeys(dietary) if d in ("辛辣", "海鲜")],
            "feedback": feedback,
        }
    )
    return {"retrieved_recipes": recipes}


def critique_menu_node(state: AgentState) -> dict:
    """节点 3:搭配审核。LLM 充当主厨/营养师,输出 is_pass/feedback/menu。"""
    messages = [
        {"role": "system", "content": CRITIQUE_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户需求:{state['user_input']}\n"
                f"解析出的约束:{json.dumps(state['parsed_constraints'], ensure_ascii=False)}\n"
                f"候选菜谱:{json.dumps(state['retrieved_recipes'], ensure_ascii=False, default=str)}"
            ),
        },
    ]
    raw = complete(messages, max_tokens=1000)
    try:
        result = _parse_json(raw)
    except Exception:
        logger.warning("审核解析失败,原始返回: %s", raw[:300])
        # 解析失败不静默通过:判不过并给反馈,触发一次重新检索
        result = {"is_pass": False, "feedback": "审核结果格式异常,请重新检索并调整候选", "menu": []}
    return {
        "is_approved": bool(result.get("is_pass")),
        "critic_feedback": str(result.get("feedback") or ""),
        "final_menu": result.get("menu") or [],
        "retry_count": state["retry_count"] + 1,
    }


def generate_response_node(state: AgentState) -> dict:
    """节点 4:最终生成。把审核通过的菜单转成有情绪价值的自然语言。

    返回流式生成器(惰性),由接口层迭代推流。
    """
    menu = state["final_menu"]
    recipes = state["retrieved_recipes"]
    chosen_ids = {int(m.get("recipe_id")) for m in menu}
    chosen = [r for r in recipes if int(r["id"]) in chosen_ids] or recipes[:2]

    history = state.get("history", [])[-6:]
    messages = [{"role": "system", "content": GENERATE_PROMPT}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append(
        {
            "role": "user",
            "content": (
                f"用户问题:{state['user_input']}\n"
                f"用户画像:{json.dumps(state['profile'], ensure_ascii=False)}\n"
                f"审核通过的菜单:{json.dumps(menu, ensure_ascii=False) if menu else '空'}\n"
                f"入选菜谱完整信息:\n{rag.build_context(chosen) if chosen else '无'}"
            ),
        }
    )

    def final_stream():
        yield from stream(messages, max_tokens=1024)

    return {"final_response": final_stream()}


# ---------------------------------------------------------------------------
# 路由与图
# ---------------------------------------------------------------------------


def route_after_parse(state: AgentState) -> str:
    """意图路由:
    - chitchat -> chat 旁路(不调 RAG)
    - preference_statement 且不需要重推 -> acknowledge 旁路(只确认记录)
    - 其余(菜谱请求 / 纠正上一轮推荐)-> 检索链路
    """
    intent = state.get("intent", "recipe_request")
    if intent == "chitchat":
        return "chat"
    if intent == "preference_statement" and not state.get("re_recommend"):
        return "acknowledge"
    return "retrieve"


def route_after_critique(state: AgentState) -> str:
    """条件路由:审核通过或重试耗尽 -> 生成;否则带反馈退回检索。"""
    if state["is_approved"] or state["retry_count"] >= MAX_RETRIES:
        return "generate"
    return "retrieve"


workflow = StateGraph(AgentState)
workflow.add_node("parse", parse_intent_node)
workflow.add_node("retrieve", retrieve_recipes_node)
workflow.add_node("critique", critique_menu_node)
workflow.add_node("generate", generate_response_node)
workflow.add_node("chat", chat_node)
workflow.add_node("acknowledge", acknowledge_node)
workflow.set_entry_point("parse")
workflow.add_conditional_edges(
    "parse",
    route_after_parse,
    {"retrieve": "retrieve", "chat": "chat", "acknowledge": "acknowledge"},
)
workflow.add_edge("chat", END)
workflow.add_edge("acknowledge", END)
workflow.add_edge("retrieve", "critique")
workflow.add_conditional_edges(
    "critique",
    route_after_critique,
    {"generate": "generate", "retrieve": "retrieve"},
)
workflow.add_edge("generate", END)

agent = workflow.compile()


def run_agent(user_input: str, history: list[dict], profile: dict | None = None) -> dict:
    """执行整张图,返回最终 State(含 final_response 流式生成器与 profile_update)。

    profile 由接口层从库读入传入;profile_update 也在接口层合并落库。
    """
    initial: AgentState = {
        "user_input": user_input,
        "history": history,
        "profile": profile or dict(user_profile.EMPTY_PROFILE),
        "profile_update": {},
        "intent": "recipe_request",
        "re_recommend": False,
        "parsed_constraints": {},
        "retrieved_recipes": [],
        "critic_feedback": "",
        "is_approved": False,
        "retry_count": 0,
        "final_menu": [],
        "final_response": None,
    }
    return agent.invoke(initial)
