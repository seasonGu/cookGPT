"""Agent 可用的工具。目前只有一个:菜谱检索(向量召回 + MySQL 取完整数据)。"""

from langchain_core.tools import tool

from backend.app import rag


@tool
def search_recipes_tool(query: str, dietary: list[str], feedback: str = "") -> list[dict]:
    """在菜谱库中检索适合的菜谱,返回完整菜谱(含食材/步骤/忌口)。

    Args:
        query: 检索词,描述想吃的菜品/口味/场景,例如 "温补暖身汤"、"清淡家常菜"
        dietary: 需要排除的忌口,取值只能是 "辛辣" 或 "海鲜",没有则传空列表
        feedback: 上一轮审核给出的改进意见,会并入检索词;没有则传空字符串
    """
    search_text = f"{query} {feedback}".strip()
    filter_expr = rag.extract_dietary_filter(search_text, dietary)
    hits = rag.search_recipes(search_text, filter=filter_expr)
    return rag.fetch_recipe_details([h["id"] for h in hits[: rag.USE_TOP_K]])
