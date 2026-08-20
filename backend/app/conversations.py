"""对话记录存储:腾讯云 MySQL(conversation / message 两表)+ 会话 REST 接口。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.auth import get_current_user
from backend.app.mysql import get_conn
from backend.app.models import (
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_TABLE_SQL = (
    """
    CREATE TABLE IF NOT EXISTS conversation (
        id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        username   VARCHAR(32)     NOT NULL,
        title      VARCHAR(64)     NOT NULL DEFAULT '新对话',
        created_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                   ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        KEY idx_user_updated (username, updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS message (
        id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        conversation_id BIGINT UNSIGNED NOT NULL,
        role            VARCHAR(16)     NOT NULL,
        content         TEXT            NOT NULL,
        created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        KEY idx_conv (conversation_id, id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
)


def ensure_tables() -> None:
    """启动时建表(幂等)。MySQL 连不上时只告警,不影响应用启动。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            for sql in _TABLE_SQL:
                cur.execute(sql)


def list_conversations(username: str, limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, updated_at FROM conversation "
                "WHERE username = %s ORDER BY updated_at DESC, id DESC LIMIT %s",
                (username, limit),
            )
            rows = cur.fetchall()
    return [{"id": r[0], "title": r[1], "updated_at": str(r[2])} for r in rows]


def create_conversation(username: str, title: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversation (username, title) VALUES (%s, %s)",
                (username, title[:64]),
            )
            return cur.lastrowid


def get_messages(conversation_id: int, username: str) -> list[dict] | None:
    """返回会话消息;会话不存在或不属于该用户时返回 None。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username FROM conversation WHERE id = %s", (conversation_id,)
            )
            row = cur.fetchone()
        if row is None or row[0] != username:
            return None
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM message "
                "WHERE conversation_id = %s ORDER BY id",
                (conversation_id,),
            )
            rows = cur.fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]


def append_message(conversation_id: int, role: str, content: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO message (conversation_id, role, content) "
                "VALUES (%s, %s, %s)",
                (conversation_id, role, content),
            )
            cur.execute(
                "UPDATE conversation SET updated_at = NOW() WHERE id = %s",
                (conversation_id,),
            )


def delete_conversation(conversation_id: int, username: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM message WHERE conversation_id = %s", (conversation_id,)
            )
            cur.execute(
                "DELETE FROM conversation WHERE id = %s AND username = %s",
                (conversation_id, username),
            )
            return cur.rowcount > 0


# ---------------------------------------------------------------------------
# REST 接口
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ConversationResponse])
def list_conv(username: str = Depends(get_current_user)):
    return list_conversations(username)


@router.post("", response_model=ConversationResponse)
def create_conv(
    req: CreateConversationRequest, username: str = Depends(get_current_user)
):
    conv_id = create_conversation(username, req.title)
    return ConversationResponse(id=conv_id, title=req.title, updated_at="")


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def conv_messages(conversation_id: int, username: str = Depends(get_current_user)):
    msgs = get_messages(conversation_id, username)
    if msgs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在"
        )
    return msgs


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conv(conversation_id: int, username: str = Depends(get_current_user)):
    if not delete_conversation(conversation_id, username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在"
        )
