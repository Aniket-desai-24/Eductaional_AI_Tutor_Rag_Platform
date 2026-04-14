from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from typing import Any

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def _empty_usage() -> dict[str, Any]:
    return {
        "llm_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "by_tag": {},
    }


_usage_ctx: ContextVar[dict[str, Any]] = ContextVar("token_usage", default=_empty_usage())


def reset_token_usage() -> None:
    _usage_ctx.set(_empty_usage())


def _count_text_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_enc.encode(text))


def count_message_tokens(messages: list[dict]) -> int:
    # Approximation compatible with chat-style prompts.
    total = 0
    for m in messages:
        total += 4
        total += _count_text_tokens(str(m.get("role", "")))
        total += _count_text_tokens(str(m.get("content", "")))
    total += 2
    return total


def count_text_tokens(text: str) -> int:
    return _count_text_tokens(text)


def add_usage(prompt_tokens: int, completion_tokens: int, tag: str = "general") -> None:
    usage = deepcopy(_usage_ctx.get())
    usage["llm_calls"] += 1
    usage["prompt_tokens"] += max(prompt_tokens, 0)
    usage["completion_tokens"] += max(completion_tokens, 0)
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

    if tag not in usage["by_tag"]:
        usage["by_tag"][tag] = {
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    usage["by_tag"][tag]["llm_calls"] += 1
    usage["by_tag"][tag]["prompt_tokens"] += max(prompt_tokens, 0)
    usage["by_tag"][tag]["completion_tokens"] += max(completion_tokens, 0)
    usage["by_tag"][tag]["total_tokens"] = (
        usage["by_tag"][tag]["prompt_tokens"] + usage["by_tag"][tag]["completion_tokens"]
    )
    _usage_ctx.set(usage)


def get_token_usage() -> dict[str, Any]:
    return deepcopy(_usage_ctx.get())

