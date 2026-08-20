"""MySQL 连接(腾讯云):导入脚本、问答检索与对话存储共用。

注意:pymysql 的 `with conn:` 不会提交事务(实测 1.2.0 退出即回滚),
所以这里自己实现 contextmanager:正常退出 commit,异常 rollback,始终 close。
"""

import pymysql
import pymysql.cursors
from contextlib import contextmanager

from backend.app import config


@contextmanager
def get_conn(streaming: bool = False):
    """streaming=True 用 SS 游标(大数据量流式读),否则普通游标。"""
    conn = pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.SSCursor if streaming else pymysql.cursors.Cursor,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
