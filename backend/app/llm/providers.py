"""
LLM Providers — Groq (Llama) primary.
Provides a unified streaming interface using Groq-hosted Llama models.

[NOTE] Previous OpenAI/Anthropic implementation preserved below for reference.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

# [DEPRECATED] OpenAI - Using Groq instead
# import openai
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import groq
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings

logger = logging.getLogger(__name__)

# Groq client setup
_groq_client = None

def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not configured")
        _groq_client = groq.AsyncClient(api_key=settings.GROQ_API_KEY)
    return _groq_client

# [DEPRECATED] Lazy import Anthropic to avoid hard dependency
# _anthropic = None
# def _get_anthropic():
#     global _anthropic
#     if _anthropic is None and settings.ANTHROPIC_API_KEY:
#         import anthropic
#         _anthropic = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
#     return _anthropic


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((groq.RateLimitError, groq.APITimeoutError)),
    reraise=True,
)
async def _stream_groq(messages: list[dict], max_tokens: int = 1000) -> AsyncIterator[str]:
    """Stream LLM response using Groq (Llama)."""
    client = _get_groq_client()
    stream = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


# [DEPRECATED] OpenAI streaming implementation
# @retry(
#     stop=stop_after_attempt(2),
#     wait=wait_exponential(multiplier=1, min=2, max=10),
#     retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
#     reraise=True,
# )
# async def _stream_openai(messages: list[dict], max_tokens: int = 1000) -> AsyncIterator[str]:
#     _openai = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
#     stream = await _openai.chat.completions.create(
#         model=settings.LLM_MODEL,
#         messages=messages,
#         max_tokens=max_tokens,
#         temperature=0.1,
#         stream=True,
#     )
#     async for chunk in stream:
#         delta = chunk.choices[0].delta
#         if delta.content:
#             yield delta.content


# [DEPRECATED] Anthropic streaming implementation
# async def _stream_anthropic(messages: list[dict], max_tokens: int = 1000) -> AsyncIterator[str]:
#     client = _get_anthropic()
#     if not client:
#         raise RuntimeError("Anthropic client not configured")
#     system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
#     conv_messages = [m for m in messages if m["role"] != "system"]
#     async with client.messages.stream(
#         model=settings.ANTHROPIC_MODEL,
#         system=system_msg,
#         messages=conv_messages,
#         max_tokens=max_tokens,
#     ) as stream:
#         async for text in stream.text_stream:
#             yield text


async def stream_response(
    messages: list[dict],
    max_tokens: int = 1000,
) -> AsyncIterator[str]:
    """
    Stream LLM response using Groq (Llama).

    Yields:
        Token strings as they stream.
    """
    try:
        async for token in _stream_groq(messages, max_tokens):
            yield token
    except Exception as e:
        logger.error(f"Groq failed ({type(e).__name__}): {e}")
        yield "I'm sorry, I'm temporarily unable to answer. Please try again in a moment."


# [DEPRECATED] OpenAI with Anthropic fallback
# async def stream_response(
#     messages: list[dict],
#     max_tokens: int = 1000,
# ) -> AsyncIterator[str]:
#     """Stream LLM response with automatic fallback from OpenAI to Anthropic."""
#     try:
#         async for token in _stream_openai(messages, max_tokens):
#             yield token
#     except (openai.RateLimitError, openai.APIError, Exception) as e:
#         logger.warning(f"OpenAI failed ({type(e).__name__}), trying Anthropic fallback")
#         try:
#             async for token in _stream_anthropic(messages, max_tokens):
#                 yield token
#         except Exception as fallback_err:
#             logger.error(f"Both LLM providers failed: {fallback_err}")
#             yield "I'm sorry, I'm temporarily unable to answer. Please try again in a moment."


async def complete(messages: list[dict], max_tokens: int = 1000) -> str:
    """Non-streaming completion. Collects all tokens and returns full string."""
    parts = []
    async for token in stream_response(messages, max_tokens):
        parts.append(token)
    return "".join(parts)
