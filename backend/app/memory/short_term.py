"""
Short-term memory — per-session conversation history in Redis.
Uses a sliding window with LLM-based compression when the window fills.

[NOTE] Previous OpenAI implementation preserved below for reference.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings
from app.llm.groq_http import chat_completion_text

logger = logging.getLogger(__name__)

# [DEPRECATED] OpenAI client
# import openai
# _client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

_redis_pool: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _redis_pool


def _key(session_id: str) -> str:
    return f"session:{session_id}:memory"


def _summary_key(session_id: str) -> str:
    return f"session:{session_id}:summary"


# ── Read / Write ──────────────────────────────────────────────────────────────
async def get_conversation_history(session_id: str) -> list[dict]:
    """
    Retrieve conversation turns for a session.
    Returns list of {role: str, content: str}.
    """
    redis = await get_redis()
    raw = await redis.get(_key(session_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


async def append_turn(session_id: str, role: str, content: str):
    """Append a single conversation turn and refresh TTL."""
    redis = await get_redis()
    history = await get_conversation_history(session_id)
    history.append({"role": role, "content": content})

    # Compress if over limit
    if len(history) > settings.MAX_CONVERSATION_TURNS * 2:
        history = await _compress_history(session_id, history)

    await redis.set(_key(session_id), json.dumps(history), ex=settings.SHORT_TERM_TTL_SECONDS)


async def get_summary(session_id: str) -> Optional[str]:
    """Retrieve the compressed summary of older turns."""
    redis = await get_redis()
    return await redis.get(_summary_key(session_id))


async def clear_session(session_id: str):
    """Delete all memory for a session."""
    redis = await get_redis()
    await redis.delete(_key(session_id), _summary_key(session_id))


async def get_full_context(session_id: str) -> tuple[Optional[str], list[dict]]:
    """
    Return (summary_of_older_turns, recent_turns).
    Callers inject summary as a system message and recent_turns as conversation history.
    """
    redis = await get_redis()
    summary = await redis.get(_summary_key(session_id))
    history = await get_conversation_history(session_id)
    # Keep only last N turns for the context window
    recent = history[-settings.MAX_CONVERSATION_TURNS:]
    return summary, recent


# ── Compression ───────────────────────────────────────────────────────────────
async def _compress_history(session_id: str, history: list[dict]) -> list[dict]:
    """
    When history exceeds the window, summarise older turns and keep recent ones.
    Stores summary in Redis; returns trimmed history.
    """
    older = history[:-settings.MAX_CONVERSATION_TURNS]
    recent = history[-settings.MAX_CONVERSATION_TURNS:]

    summary_text = await _summarise_turns(older)

    redis = await get_redis()
    await redis.set(_summary_key(session_id), summary_text, ex=settings.SHORT_TERM_TTL_SECONDS)

    logger.info(f"Compressed {len(older)} older turns for session {session_id[:8]}")
    return recent


async def _summarise_turns(turns: list[dict]) -> str:
    """
    Use Groq Llama to create a concise summary of conversation turns.
    """
    transcript = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in turns)
    try:
        response_text = await chat_completion_text(
            messages=[
                {
                    "role": "system",
                    "content": "Summarise the following conversation between a student and an AI tutor. "
                               "Capture the topics discussed and key points covered. Be concise (3-5 sentences).",
                },
                {"role": "user", "content": transcript},
            ],
            model=settings.LLM_MODEL,
            max_tokens=300,
        )
        return response_text.strip()
    except Exception as e:
        logger.warning(f"History compression failed: {e}")
        return "Previous conversation covered various educational topics."


# [DEPRECATED] OpenAI implementation
# async def _summarise_turns(turns: list[dict]) -> str:
#     """Use the LLM to create a concise summary of conversation turns."""
#     transcript = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in turns)
#     client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
#     try:
#         resp = await client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {
#                     "role": "system",
#                     "content": "Summarise the following conversation between a student and an AI tutor. "
#                                "Capture the topics discussed and key points covered. Be concise (3-5 sentences).",
#                 },
#                 {"role": "user", "content": transcript},
#             ],
#             max_tokens=300,
#         )
#         return resp.choices[0].message.content.strip()
#     except Exception as e:
#         logger.warning(f"History compression failed: {e}")
#         return "Previous conversation covered various educational topics."

