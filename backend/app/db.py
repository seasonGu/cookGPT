"""用户库:SQLite 初始化 + 连接。

2GB 小服务器上用户账号用本地 SQLite 足够(零额外内存);
以后要换腾讯云 MySQL,只需替换这里的建表/连接逻辑,业务层不用动。
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from backend.app.security import hash_password

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cookgpt.db"


@contextmanager
def get_conn():
    """每次请求一个短连接,避免多线程共享连接的问题。

    注意 sqlite3 的 `with conn:` 只提交事务、不关闭连接,
    这里用 contextmanager 保证退出时连接真正关闭。
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:  # 事务:正常退出 commit,异常 rollback
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """建表 + 写入演示账号(admin / admin123456)。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                salt          TEXT    NOT NULL,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                username   TEXT PRIMARY KEY,
                profile    TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        # 首次启动时种一个演示账号,方便直接登录体验
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count == 0:
            pw_hash, salt = hash_password("admin123456")
            conn.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                ("admin", pw_hash, salt),
            )
