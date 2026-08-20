"""bge-m3 embedding:硅基流动 API,内置 429/网络错误重试。"""

import time

import httpx

from backend.app import config


class EmbeddingError(RuntimeError):
    """embedding 调用重试耗尽后抛出。"""


def embed_texts(texts: list[str]) -> list[list[float]]:
    """按 EMBED_BATCH_SIZE 分批调 API,返回与输入等长的向量列表。"""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), config.EMBED_BATCH_SIZE):
        vectors.extend(_embed_batch(texts[start : start + config.EMBED_BATCH_SIZE]))
    return vectors


def _embed_batch(texts: list[str]) -> list[list[float]]:
    if not config.SILICONFLOW_API_KEY:
        raise EmbeddingError("缺少 SILICONFLOW_API_KEY,请在 .env 或环境变量中配置")

    headers = {"Authorization": f"Bearer {config.SILICONFLOW_API_KEY}"}
    for attempt in range(config.EMBED_MAX_RETRIES):
        try:
            resp = httpx.post(
                config.EMBED_BASE_URL,
                json={"model": config.EMBED_MODEL, "input": texts},
                headers=headers,
                timeout=60.0,
            )
            if resp.status_code == 429:
                delay = 2**attempt * 2
                print(
                    f"  触发限速(429),{delay}s 后重试"
                    f"({attempt + 1}/{config.EMBED_MAX_RETRIES})"
                )
                time.sleep(delay)
                continue
            resp.raise_for_status()
            # 按 index 排序,保证返回顺序与输入一致
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in data]
        except httpx.HTTPError as e:
            print(
                f"  请求失败:{e},重试({attempt + 1}/{config.EMBED_MAX_RETRIES})"
            )
            time.sleep(2**attempt)

    raise EmbeddingError(f"embedding 连续 {config.EMBED_MAX_RETRIES} 次失败,请检查网络与 API key")
