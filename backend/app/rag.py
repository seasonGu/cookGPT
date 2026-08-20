"""检索层:向量召回(Milvus Lite)+ 取完整菜谱(MySQL)+ 提示词上下文构建。

(意图解析/查询改写、审核、生成等编排逻辑在 agent.py,检索工具在 tools.py)
"""

import json
import logging

from backend.app.embedding import embed_texts
from backend.app.mysql import get_conn
from backend.app.vector_store import (
    COLLECTION,
    ensure_collection,
    get_client,
    reset_client,
)

logger = logging.getLogger(__name__)

RECALL_K = 20  # Milvus 召回条数
USE_TOP_K = 6  # 取前 N 条完整菜谱拼 prompt
RECIPE_MAX_CHARS = 500  # 单条菜谱在 prompt 里的长度上限
MAX_STEPS = 8  # 单条菜谱步骤数量上限

# 忌口关键词 -> dietary 字段里要排除的值(规则匹配,与 LLM 解析互补)
DIETARY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("不辣", "不要辣", "不吃辣", "忌辣", "怕辣", "清淡"), "辛辣"),
    (("不吃海鲜", "忌海鲜", "海鲜过敏", "不要海鲜", "免海鲜"), "海鲜"),
)


def extract_dietary_filter(query: str, extra: list[str] | None = None) -> str | None:
    """从 query 提取忌口约束,生成 Milvus 标量过滤表达式;无约束返回 None。

    extra 是 LLM 解析阶段提取的忌口值(只接受 dietary 字段里存在的取值)。
    """
    excludes: list[str] = []
    for keywords, value in DIETARY_RULES:
        if any(k in query for k in keywords):
            excludes.append(value)
    for value in extra or []:
        if value not in excludes:
            excludes.append(value)
    # Milvus 表达式不支持 `not like` 连写,要用 not(...) 包裹
    return (
        " and ".join(f'not (dietary like "%{v}%")' for v in excludes)
        if excludes
        else None
    )


def search_recipes(
    query: str, top_k: int = RECALL_K, filter: str | None = None
) -> list[dict]:
    """query 向量化后在 Milvus 召回,返回含 id/score 的菜谱摘要。

    多取一倍再按菜名去重(生成数据里有大量同名菜谱),
    保证返回给 LLM 的候选是多样化的 top_k 条。
    """
    qvec = embed_texts([query])[0]
    client = get_client()
    ensure_collection(client)  # 应用进程重启后从磁盘重开 collection,需先 load
    # 连接被服务端踢掉(Too many pings 等)时:重置单例,重新拉起内嵌服务再试一次
    for attempt in range(2):
        try:
            hits = client.search(
                collection_name=COLLECTION,
                data=[qvec],
                limit=top_k * 2,
                filter=filter or "",
                output_fields=["name", "description", "dietary", "tags"],
            )[0]
            break
        except Exception:
            if attempt == 1:
                raise
            logger.warning("Milvus 连接异常,重置单例后重试", exc_info=True)
            reset_client()
            client = get_client()
            ensure_collection(client)
    seen: set[str] = set()
    results = []
    for h in hits:
        name = h["entity"]["name"]
        if name in seen:
            continue
        seen.add(name)
        results.append(
            {**h["entity"], "id": int(h["id"]), "score": round(h["distance"], 4)}
        )
        if len(results) >= top_k:
            break
    return results


def fetch_recipe_details(ids: list[int]) -> list[dict]:
    """按 id 从 MySQL 取完整菜谱(含食材/步骤),保持传入顺序;查不到的丢弃。"""
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    sql = (
        "SELECT id, name, description, ingredients, steps, dietary, tags, servings "
        f"FROM recipe WHERE id IN ({placeholders})"
    )
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, ids)
            rows = cur.fetchall()
    cols = ("id", "name", "description", "ingredients", "steps", "dietary", "tags", "servings")
    by_id = {r[0]: dict(zip(cols, r)) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def build_context(recipes: list[dict]) -> str:
    """把完整菜谱拼成给 LLM 的上下文文本(每条截断控制长度)。"""
    blocks = []
    for i, r in enumerate(recipes, 1):
        ingredients = r["ingredients"]
        if isinstance(ingredients, str):  # MySQL 里是 JSON 字符串
            ingredients = json.loads(ingredients)
        names = "、".join(x["name"] for x in ingredients)

        steps = r["steps"]
        if isinstance(steps, str):
            steps = json.loads(steps)
        steps_text = " ".join(f"{j + 1}.{s}" for j, s in enumerate(steps[:MAX_STEPS]))

        block = (
            f"【菜谱{i}】{r['name']}({r['servings']}人份)\n"
            f"说明:{r['description']}\n"
            f"食材:{names}\n"
            f"步骤:{steps_text}\n"
            f"忌口:{r['dietary']} | 标签:{r['tags']}"
        )
        blocks.append(block[:RECIPE_MAX_CHARS])
    return "\n\n".join(blocks)
