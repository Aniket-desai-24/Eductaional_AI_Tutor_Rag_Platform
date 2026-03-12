"""
HyDE — Hypothetical Document Embeddings
Generates a hypothetical answer to a question, embeds it, and merges with the
original query embedding to improve retrieval recall for short/ambiguous questions.

[NOTE] Previous OpenAI implementation preserved below for reference.
"""
from __future__ import annotations

import asyncio
import logging

# [DEPRECATED] OpenAI - Using Groq instead
# import openai
import groq
import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)

# Groq client for HyDE LLM generation
_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not configured for HyDE")
        _groq_client = groq.AsyncClient(api_key=settings.GROQ_API_KEY)
    return _groq_client


# [DEPRECATED] OpenAI client
# _client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# Initialize Sentence Transformer for embeddings
_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Loading embedding model for HyDE: {settings.EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedding_model


async def _generate_hypothetical_answer(question: str, context_hint: str = "") -> str:
    """
    Ask the LLM to write a short hypothetical passage that would answer the question.
    Uses Groq Llama for generation.
    """
    system = (
        "You are an expert educational assistant. "
        "Given a student's question, write a short, factual passage (2-4 sentences) "
        "that would appear in a textbook and directly answer the question. "
        "Do NOT say 'I think' or 'perhaps'. Write as if it is a factual textbook excerpt."
    )
    user = question
    if context_hint:
        user = f"Subject: {context_hint}\nQuestion: {question}"

    try:
        client = _get_groq_client()
        resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=200,
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"HyDE generation failed: {e}")
        return question   # fallback to original question


# [DEPRECATED] OpenAI implementation
# async def _generate_hypothetical_answer(question: str, context_hint: str = "") -> str:
#     """Ask the LLM to write a short hypothetical passage that would answer the question."""
#     system = (...)
#     user = question
#     if context_hint:
#         user = f"Subject: {context_hint}\nQuestion: {question}"
#     try:
#         resp = await _client.chat.completions.create(
#             model=settings.LLM_MODEL,
#             messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
#             max_tokens=200,
#             temperature=0.1,
#         )
#         return resp.choices[0].message.content.strip()
#     except Exception as e:
#         logger.warning(f"HyDE generation failed: {e}")
#         return question


async def _embed_text(text: str) -> list[float]:
    """
    Embed text using Sentence Transformers.
    """
    loop = asyncio.get_event_loop()
    model = _get_embedding_model()
    embedding = await loop.run_in_executor(None, model.encode, text)
    return embedding.tolist()


# [DEPRECATED] OpenAI embedding implementation
# async def _embed_text(text: str) -> list[float]:
#     resp = await _client.embeddings.create(
#         model=settings.EMBEDDING_MODEL,
#         input=[text],
#         dimensions=settings.EMBEDDING_DIMENSIONS,
#     )
#     return resp.data[0].embedding


def _merge_vectors(v1: list[float], v2: list[float], alpha: float = 0.5) -> list[float]:
    """Weighted merge: alpha * v1 + (1-alpha) * v2, then re-normalise."""
    arr = alpha * np.array(v1) + (1 - alpha) * np.array(v2)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


async def embed_query_with_hyde(
    question: str,
    context_hint: str = "",
    hyde_weight: float = 0.4,
) -> list[float]:
    """
    Embed the query using HyDE:
    1. Embed original question.
    2. Generate hypothetical answer.
    3. Embed hypothetical answer.
    4. Return weighted merge.

    Args:
        question: User's natural language question.
        context_hint: Optional subject/course hint for better HyDE generation.
        hyde_weight: Weight for hypothetical answer embedding (0 = query only, 1 = HyDE only).
    """
    query_vec_task = _embed_text(question)
    hypo_task = _generate_hypothetical_answer(question, context_hint)

    query_vec, hypo_answer = await asyncio.gather(query_vec_task, hypo_task)

    logger.debug(f"HyDE answer: {hypo_answer[:100]}...")

    if hypo_answer == question:
        return query_vec  # HyDE failed, use original

    hypo_vec = await _embed_text(hypo_answer)
    merged = _merge_vectors(query_vec, hypo_vec, alpha=1 - hyde_weight)
    return merged

