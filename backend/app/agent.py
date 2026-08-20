"""cookGPT Agent(LangGraph):意图解析 → 策略检索 → 搭配审核(可重试)→ 最终生成。

图结构:
    parse ──> retrieve ──> critique ──(通过/重试耗尽)──> generate ──> END
                             │ 未通过且未耗尽
                             └────────────> retrieve   (带审核反馈重新检索)

- parse/retrieve/critique 是同步节点;generate 节点返回一个流式生成器,
  由接口层逐段推给前端,保住流式体验。
- 审核重试上限 MAX_RETRIES 防止死循环。
"""

import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

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

PARSE_PROMPT = """把用户的饮食需求解析成适合菜谱检索的结构化约束。

输出 JSON(不要输出其他内容):
{"search_query": "改写后的检索词(描述想吃的菜品/口味/场景,25 字以内)", "dietary": ["辛辣", "海鲜", ...], "notes": "其他要求摘要:人数/场合/荤素搭配/口味偏好等,没有则写 无"}

规则:
- 口语化需求转成菜品/做法描述:如"来大姨妈了"→"温补暖身汤"、"感冒了"→"清淡易消化"、"朋友聚餐"→"荤素搭配宴客菜"
- dietary 只从 ["辛辣", "海鲜"] 中选,是用户【不能吃】的;用户【想吃】的(如"想吃辣")不要放进去
- 没有忌口时 dietary 返回 []"""

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

GENERATE_PROMPT = """你是 cookGPT,一位专业又亲切的 AI 私厨,根据主厨审核通过的菜单为用户生成最终回答。

要求:
1. 回答带温度,先说明推荐逻辑(这些菜为什么适合用户的需求)
2. 每道菜给出食材和步骤(步骤按顺序编号),不要编造菜谱中不存在的内容
3. 推荐的菜带忌口标记(海鲜/辛辣/麸质等)时,简要提示一句
4. 菜单为空或不足以满足需求时,基于常识给出饮食建议,并明确说明「菜谱库中未找到完全匹配的菜谱,以下为一般建议」
5. 简洁友好的中文"""


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
    """节点 1:意图解析,user_input -> parsed_constraints(JSON)。"""
    history = state.get("history", [])[-4:]
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history) or "无"
    messages = [
        {"role": "system", "content": PARSE_PROMPT},
        {
            "role": "user",
            "content": f"对话历史:\n{history_text}\n\n当前需求:\n{state['user_input']}",
        },
    ]
    try:
        constraints = _parse_json(complete(messages, max_tokens=800))
    except Exception:
        logger.warning("意图解析失败,用原始 query 兜底", exc_info=True)
        constraints = {
            "search_query": state["user_input"],
            "dietary": [],
            "notes": "无",
        }
    return {"parsed_constraints": constraints, "retry_count": 0}


def retrieve_recipes_node(state: AgentState) -> dict:
    """节点 2:策略检索。若有 Critic 反馈,并入检索条件重新检索。"""
    constraints = state["parsed_constraints"]
    feedback = state.get("critic_feedback", "")
    recipes = search_recipes_tool.invoke(
        {
            "query": constraints.get("search_query", state["user_input"]),
            "dietary": [
                d for d in constraints.get("dietary", []) if d in ("辛辣", "海鲜")
            ],
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
workflow.set_entry_point("parse")
workflow.add_edge("parse", "retrieve")
workflow.add_edge("retrieve", "critique")
workflow.add_conditional_edges(
    "critique",
    route_after_critique,
    {"generate": "generate", "retrieve": "retrieve"},
)
workflow.add_edge("generate", END)

agent = workflow.compile()


def run_agent(user_input: str, history: list[dict]) -> dict:
    """执行整张图,返回最终 State(含 final_response 流式生成器)。"""
    initial: AgentState = {
        "user_input": user_input,
        "history": history,
        "parsed_constraints": {},
        "retrieved_recipes": [],
        "critic_feedback": "",
        "is_approved": False,
        "retry_count": 0,
        "final_menu": [],
        "final_response": None,
    }
    return agent.invoke(initial)
