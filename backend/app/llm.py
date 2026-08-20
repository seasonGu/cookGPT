"""DeepSeek V4 调用:非流式 complete(解析/审核节点用)与流式 stream(生成节点用)。"""

import json

import httpx

from backend.app import config


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.LLM_API_KEY}"}


def complete(messages: list[dict], max_tokens: int = 800, timeout: float = 30.0) -> str:
    """非流式调用,返回完整回复文本。

    关闭 thinking:解析/审核这类结构化任务不需要推理,
    否则推理 token 会挤占 max_tokens 导致 content 为空。
    """
    resp = httpx.post(
        config.LLM_BASE_URL,
        json={
            "model": config.LLM_MODEL,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
            "thinking": {"type": "disabled"},
        },
        headers=_headers(),
        timeout=httpx.Timeout(timeout, connect=10.0),
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


def stream(messages: list[dict], max_tokens: int = 2048):
    """流式调用,逐段 yield 文本增量。

    同样关闭 thinking:保证首个可见 token 不被推理延迟拖慢。
    """
    with httpx.stream(
        "POST",
        config.LLM_BASE_URL,
        json={
            "model": config.LLM_MODEL,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "thinking": {"type": "disabled"},
        },
        headers=_headers(),
        timeout=httpx.Timeout(120.0, connect=10.0),
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = data["choices"][0]["delta"].get("content")
            if delta:
                yield delta
