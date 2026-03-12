"""
Re-ranker — scores query-chunk pairs using a cross-encoder for higher precision.
Uses Groq Llama to score relevance when a dedicated cross-encoder is unavailable.
Falls back to original vector scores if re-ranking fails.

[NOTE] Previous OpenAI implementation preserved below for reference.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

# [DEPRECATED] OpenAI - Using Groq instead
# import openai

import groq

from app.config import settings

logger = logging.getLogger(__name__)

# Groq client for re-ranking
_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not configured for reranker")
        _groq_client = groq.AsyncClient(api_key=settings.GROQ_API_KEY)
    return _groq_client


# [DEPRECATED] OpenAI client
# _client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

RERANK_CONCURRENCY = 5


async def _score_pair(question: str, chunk_text: str) -> float:
    """
    Ask the LLM to rate the relevance of a chunk to a question on a 0-10 scale.
    Returns a float 0.0–1.0.
    Uses Groq Llama for scoring.
    """
    prompt = (
        f"Question: {question}\n\n"
        f"Passage: {chunk_text[:600]}\n\n"
        "Rate how relevant this passage is to answering the question. "
        "Respond with a single integer from 0 (not relevant) to 10 (perfectly relevant)."
    )
    try:
        client = _get_groq_client()
        resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        score = float(raw.split()[0]) / 10.0
        return min(max(score, 0.0), 1.0)
    except Exception as e:
        logger.debug(f"Re-rank score failed: {e}")
        return 0.5


# [DEPRECATED] OpenAI implementation
# async def _score_pair(question: str, chunk_text: str) -> float:
#     """Ask the LLM to rate the relevance of a chunk to a question on a 0-10 scale."""
#     prompt = (...)
#     try:
#         resp = await _client.chat.completions.create(
#             model="gpt-4o-mini",   # cheaper model for scoring
#             messages=[{"role": "user", "content": prompt}],
#             max_tokens=5,
#             temperature=0,
#         )
#         raw = resp.choices[0].message.content.strip()
#         score = float(raw.split()[0]) / 10.0
#         return min(max(score, 0.0), 1.0)
#     except Exception as e:
#         logger.debug(f"Re-rank score failed: {e}")
#         return 0.5


async def rerank(
    question: str,
    candidates: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """
    Re-rank a list of retrieved chunk candidates.

    Args:
        question: The user's question.
        candidates: List of {id, score, metadata} from vector search.
        top_k: Number of results to return after re-ranking.

    Returns:
        Top-k candidates sorted by re-rank score, with 'rerank_score' field added.
    """
    if not candidates:
        return []

    if len(candidates) <= top_k:
        return candidates   # no need to re-rank

    sem = asyncio.Semaphore(RERANK_CONCURRENCY)

    async def score_one(candidate: dict) -> dict:
        async with sem:
            chunk_text = candidate["metadata"].get("content", "")
            score = await _score_pair(question, chunk_text)
            return {**candidate, "rerank_score": score}

    scored = await asyncio.gather(*[score_one(c) for c in candidates])
    ranked = sorted(scored, key=lambda x: x["rerank_score"], reverse=True)
    return ranked[:top_k]


def mmr_deduplication(
    candidates: list[dict],
    top_k: int = 5,
    diversity_threshold: float = 0.85,
) -> list[dict]:
    """
    Max Marginal Relevance — remove near-duplicate chunks.
    Two chunks are near-duplicates if their first 200 chars overlap > threshold.
    """
    if len(candidates) <= top_k:
        return candidates

    selected: list[dict] = []
    for candidate in candidates:
        content = candidate["metadata"].get("content", "")
        is_duplicate = False
        for kept in selected:
            kept_content = kept["metadata"].get("content", "")
            # Simple Jaccard similarity on word sets (fast, no vectors needed)
            set_a = set(content[:300].lower().split())
            set_b = set(kept_content[:300].lower().split())
            if set_a and set_b:
                overlap = len(set_a & set_b) / len(set_a | set_b)
                if overlap > diversity_threshold:
                    is_duplicate = True
                    break
        if not is_duplicate:
            selected.append(candidate)
        if len(selected) >= top_k:
            break

    return selected

