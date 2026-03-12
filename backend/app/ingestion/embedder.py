"""
Embedder — generates dense vector embeddings using Sentence Transformers (MiniLM).
Supports batching, retry with exponential backoff, and vision captioning for images.

[NOTE] Previous OpenAI implementation preserved below for reference.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Optional

# [DEPRECATED] OpenAI embeddings - Using Sentence Transformers instead
# import openai
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.ingestion.chunker import Chunk
from app.llm.groq_http import chat_completion_text

logger = logging.getLogger(__name__)

# Initialize Sentence Transformer model (MiniLM)
# This is a lightweight, fast model that produces 384-dimensional embeddings
_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedding_model


# [DEPRECATED] OpenAI client
# _client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

EMBED_BATCH_SIZE = 100
CAPTION_CONCURRENCY = 5  # simultaneous vision calls


# ── Retry decorator ───────────────────────────────────────────────────────────
_retry = retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)


@_retry
async def _embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of texts using Sentence Transformers.
    Returns list of embedding vectors (384 dimensions for MiniLM).
    """
    # Run in executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    model = _get_embedding_model()
    embeddings = await loop.run_in_executor(None, model.encode, texts)
    return embeddings.tolist()


# [DEPRECATED] OpenAI embedding implementation
# @_retry
# async def _embed_batch(texts: list[str]) -> list[list[float]]:
#     response = await _client.embeddings.create(
#         model=settings.EMBEDDING_MODEL,
#         input=texts,
#         dimensions=settings.EMBEDDING_DIMENSIONS,
#     )
#     return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


async def embed_chunks(chunks: list[Chunk]) -> dict[str, list[float]]:
    """
    Embed all chunks and return {chunk_id: vector} mapping.
    Only embeds text-bearing chunks (not image chunks without captions).
    """
    eligible = [c for c in chunks if c.content and len(c.content.strip()) > 10]
    logger.info(f"Embedding {len(eligible)} chunks in batches of {EMBED_BATCH_SIZE}")

    vectors: dict[str, list[float]] = {}
    batches = [eligible[i:i + EMBED_BATCH_SIZE] for i in range(0, len(eligible), EMBED_BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches):
        texts = [c.content for c in batch]
        try:
            embeddings = await _embed_batch(texts)
            for chunk, vec in zip(batch, embeddings):
                vectors[chunk.chunk_id] = vec
            logger.info(f"  Batch {batch_idx + 1}/{len(batches)} done")
        except Exception as e:
            logger.error(f"Embedding batch {batch_idx} failed: {e}")
            raise

    return vectors


# ── Vision captioning ─────────────────────────────────────────────────────────
# [DEPRECATED] OpenAI Vision implementation
# @_retry
# async def _caption_image(image_bytes: bytes, extension: str, context: str) -> str:
#     """Generate a semantic description of an image using GPT-4o Vision."""
#     b64 = base64.b64encode(image_bytes).decode()
#     mime = f"image/{'jpeg' if extension in ('jpg', 'jpeg') else extension}"
#     messages = [...]
#     response = await _client.chat.completions.create(
#         model=settings.VISION_MODEL,
#         messages=messages,
#         max_tokens=300,
#     )
#     return response.choices[0].message.content.strip()


@_retry
async def _caption_image(image_bytes: bytes, extension: str, context: str) -> str:
    """
    Generate a semantic description of an image using Groq Llama Vision.
    Note: Groq Llama 3.2 90B Vision is a vision-capable model.
    """
    b64 = base64.b64encode(image_bytes).decode()
    mime = f"image/{'jpeg' if extension in ('jpg', 'jpeg') else extension}"

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert educational content analyst. "
                "Describe the given image/diagram/graph in detail for a student. "
                "If it is a graph, describe axes, trends, and key data points. "
                "If it is a diagram, describe labels and relationships. "
                "Be concise but complete. Max 150 words."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                },
                {"type": "text", "text": f"Context: {context}\nDescribe this educational image."},
            ],
        },
    ]

    response_text = await chat_completion_text(
        messages=messages,
        model=settings.VISION_MODEL,
        max_tokens=300,
    )
    return response_text.strip()


async def caption_image_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """
    Generate captions for all image chunks using Groq Llama Vision.
    Mutates chunks in-place (updates content field).
    """
    image_chunks = [c for c in chunks if c.content_type == "image_caption" and c.image_bytes]
    logger.info(f"Captioning {len(image_chunks)} images")

    sem = asyncio.Semaphore(CAPTION_CONCURRENCY)

    async def caption_one(chunk: Chunk):
        async with sem:
            ctx = f"Chapter {chunk.chapter}, Page {chunk.page_start}" if chunk.chapter else f"Page {chunk.page_start}"
            try:
                caption = await _caption_image(
                    chunk.image_bytes,
                    chunk.metadata.get("image_extension", "png"),
                    ctx,
                )
                chunk.content = caption
                logger.debug(f"Captioned image chunk {chunk.chunk_id[:8]}")
            except Exception as e:
                logger.warning(f"Caption failed for chunk {chunk.chunk_id[:8]}: {e}")
                chunk.content = f"[Image on page {chunk.page_start} — captioning failed]"

    await asyncio.gather(*[caption_one(c) for c in image_chunks])
    return chunks
