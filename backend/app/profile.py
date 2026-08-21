"""用户饮食画像:忌口/口味偏好的跨会话持久化(按用户存,方案 B)。

画像由 parse 节点每轮提取增量(profile_update),本模块负责:
- 从 SQLite 读写画像
- 代码确定性地合并增量(不靠 LLM 合并,避免丢数据/乱改)

画像结构:
    {
        "dietary_excludes": ["辛辣", "海鲜"],  # 忌口硬约束,检索时过滤
        "taste_prefs": ["清淡"],               # 口味偏好软约束,生成时参考
        "notes": "3人聚餐"                      # 其他(场合/人数等)
    }
"""

import json
import logging

from backend.app.db import get_conn

logger = logging.getLogger(__name__)

EMPTY_PROFILE = {"dietary_excludes": [], "taste_prefs": [], "notes": ""}

# parse 节点输出的增量字段 -> 画像字段的映射
_LIST_FIELDS = (
    ("add_excludes", "dietary_excludes"),
    ("add_prefs", "taste_prefs"),
    ("remove_excludes", "dietary_excludes"),
    ("remove_prefs", "taste_prefs"),
)


def merge_profile(profile: dict, update: dict) -> dict:
    """把 parse 提取的增量合并进画像(纯函数,节点内和落库前各用一次)。

    语义:add_* 追加(去重)、remove_* 移除(支持"我现在能吃辣了"这类撤销)、
    notes 非空时整体覆盖。
    """
    merged = {
        "dietary_excludes": list(profile.get("dietary_excludes") or []),
        "taste_prefs": list(profile.get("taste_prefs") or []),
        "notes": profile.get("notes") or "",
    }
    for src, dst in _LIST_FIELDS:
        for item in update.get(src) or []:
            item = str(item).strip()
            if not item:
                continue
            if src.startswith("add") and item not in merged[dst]:
                merged[dst].append(item)
            elif src.startswith("remove") and item in merged[dst]:
                merged[dst].remove(item)
    notes = str(update.get("notes") or "").strip()
    if notes and notes != "无":
        merged["notes"] = notes
    return merged


def load_profile(username: str) -> dict:
    """读画像;没有记录或数据损坏时返回空画像,不阻塞聊天。"""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT profile FROM user_profiles WHERE username = ?", (username,)
            ).fetchone()
        if row is None:
            return dict(EMPTY_PROFILE)
        saved = json.loads(row["profile"])
        return {**EMPTY_PROFILE, **saved}
    except Exception:
        logger.warning("画像读取失败,按空画像处理", exc_info=True)
        return dict(EMPTY_PROFILE)


def save_profile(username: str, profile: dict) -> None:
    """UPSERT 画像(JSON 序列化存 SQLite)。"""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO user_profiles (username, profile, updated_at)
            VALUES (?, ?, datetime('now', 'localtime'))
            ON CONFLICT(username) DO UPDATE SET
                profile = excluded.profile,
                updated_at = excluded.updated_at
            """,
            (username, json.dumps(profile, ensure_ascii=False)),
        )
