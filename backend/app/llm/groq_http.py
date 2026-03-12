from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.config import settings

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not configured")
        _http_client = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            timeout=httpx.Timeout(60.0),
        )
    return _http_client


async def chat_completion_text(
    messages: list[dict],
    model: str,
    max_tokens: int = 1000,
    temperature: float = 0.1,
) -> str:
    client = _get_client()
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    response = await client.post("/chat/completions", json=payload)
    response.raise_for_status()
    body = response.json()
    return (body.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""


async def chat_completion_stream(
    messages: list[dict],
    model: str,
    max_tokens: int = 1000,
    temperature: float = 0.1,
) -> AsyncIterator[str]:
    client = _get_client()
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    async with client.stream("POST", "/chat/completions", json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = (chunk.get("choices", [{}])[0].get("delta", {}) or {}).get("content")
            if delta:
                yield delta
