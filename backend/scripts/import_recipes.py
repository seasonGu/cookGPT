"""全量导入:MySQL 菜谱 -> bge-m3 向量 -> Milvus Lite。

用法(先在项目根目录 .env 配好 MySQL 与 SILICONFLOW_API_KEY):
  uv run python -m backend.scripts.import_recipes --full            # 全量导入
  uv run python -m backend.scripts.import_recipes --limit 50        # 冒烟:只导前 50 条
  uv run python -m backend.scripts.import_recipes --start-id 5001   # 断点续跑:从 id 5001 继续
  uv run python -m backend.scripts.import_recipes --fake-embed      # 联调管道:随机向量,不调 API

幂等:按菜谱 id upsert,中断后重跑即可(已导入的会被覆盖,不会重复)。
"""

import argparse
import json
import math
import random
import sys
import time

import pymysql

from backend.app import config
from backend.app.embedding import embed_texts
from backend.app.mysql import get_conn
from backend.app.vector_store import COLLECTION, ensure_collection, get_client

READ_BATCH = 500  # 每次从 MySQL 读的行数(2GB 服务器内存平稳的关键)


def build_text(row: dict) -> str:
    """一条菜谱 -> 一段待 embedding 的文本(name+说明+食材+标签+忌口)。"""
    ingredients = row["ingredients"]
    if isinstance(ingredients, str):  # MySQL 里是 JSON 字符串
        ingredients = json.loads(ingredients)
    names = "、".join(x["name"] for x in ingredients)
    parts = [
        row["name"],
        row["description"] or "",
        f"食材:{names}",
        f"标签:{row['tags'] or ''}",
        f"忌口:{row['dietary'] or '无'}",
    ]
    return "。".join(p for p in parts if p)


def _count_rows(start_id: int) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM recipe WHERE id >= %s", (start_id,))
            return cur.fetchone()[0]


def _fetch_rows(limit: int | None, start_id: int):
    """流式读 MySQL(SS 游标),一次 yield 一批 dict。"""
    with get_conn(streaming=True) as conn:
        sql = (
            "SELECT id, name, description, ingredients, dietary, tags "
            "FROM recipe WHERE id >= %s ORDER BY id"
        )
        params: list = [start_id]
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        keys = [d[0] for d in cursor.description]
        while True:
            batch = cursor.fetchmany(READ_BATCH)
            if not batch:
                break
            yield [dict(zip(keys, values)) for values in batch]


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """联调用随机单位向量,不调 API(检索结果无意义,仅验证管道)。"""
    vectors = []
    for _ in texts:
        v = [random.uniform(-1, 1) for _ in range(config.EMBED_DIM)]
        norm = math.sqrt(sum(x * x for x in v))
        vectors.append([x / norm for x in v])
    return vectors


def main() -> int:
    parser = argparse.ArgumentParser(description="全量导入菜谱向量到 Milvus Lite")
    parser.add_argument("--full", action="store_true", help="全量导入(默认行为,显式声明)")
    parser.add_argument("--limit", type=int, default=None, help="只导前 N 条(冒烟测试)")
    parser.add_argument("--start-id", type=int, default=1, help="从指定 id 开始(断点续跑)")
    parser.add_argument("--fake-embed", action="store_true", help="随机向量代替 API(联调管道)")
    args = parser.parse_args()

    if not args.fake_embed and not config.SILICONFLOW_API_KEY:
        print("缺少 SILICONFLOW_API_KEY:请在 .env 配置,或加 --fake-embed 联调管道")
        return 1
    if not config.MYSQL_HOST:
        print("缺少 MYSQL_HOST:请在 .env 配置腾讯云 MySQL 内网地址")
        return 1

    client = get_client()
    ensure_collection(client)

    embedder = _fake_embed if args.fake_embed else embed_texts
    print(
        f"开始导入:MySQL {config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DB}"
        f" -> Milvus Lite {config.MILVUS_DB_PATH}"
        + (f" | 模型 {config.EMBED_MODEL}" if not args.fake_embed else " | 假向量(联调)")
    )

    try:
        total = _count_rows(args.start_id)
        imported = 0
        started = time.monotonic()
        for rows in _fetch_rows(args.limit, args.start_id):
            texts = [build_text(r) for r in rows]
            vectors = embedder(texts)
            data = [
                {
                    "id": int(r["id"]),
                    "name": r["name"],
                    "description": (r["description"] or "")[:2048],
                    "dietary": (r["dietary"] or "")[:255],
                    "tags": (r["tags"] or "")[:255],
                    "vector": v,
                }
                for r, v in zip(rows, vectors)
            ]
            client.upsert(collection_name=COLLECTION, data=data)
            imported += len(rows)
            elapsed = time.monotonic() - started
            pct = f"{imported / total:.1%}" if total else "?"
            eta = (elapsed / imported) * (total - imported) if total and imported else 0
            print(f"  已导入 {imported}/{total} ({pct}) | 用时 {elapsed:.0f}s | 预计剩余 {eta:.0f}s")
    except pymysql.MySQLError as e:
        print(f"✗ MySQL 连接失败:{e}")
        print("  请检查 .env 中 MYSQL_* 配置(内网地址、安全组放行、账号权限)")
        return 1

    count = client.query(collection_name=COLLECTION, filter="", output_fields=["count(*)"])[0]["count(*)"]
    print(f"✓ 完成:集合 {COLLECTION} 共 {count} 条")

    # 冒烟检索:验证 query -> 向量 -> 召回 全链路(假向量时跳过)
    if not args.fake_embed:
        query = "推荐一道不辣的家常菜"
        hits = client.search(
            collection_name=COLLECTION,
            data=[embed_texts([query])[0]],
            limit=3,
            output_fields=["name", "dietary"],
        )
        print(f"检索冒烟测试(query: {query}):")
        for h in hits[0]:
            print(f"  - {h['entity']['name']} (分数 {h['distance']:.3f} | 忌口:{h['entity']['dietary']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
