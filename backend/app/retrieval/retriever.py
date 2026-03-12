"""
Retriever — orchestrates the full retrieval pipeline:
  1. Query embedding with HyDE
  2. Hybrid vector + BM25 search
  3. Re-ranking
  4. Parent chunk expansion
  5. MMR deduplication
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import DocumentChunk
from app.retrieval.hyde import embed_query_with_hyde
from app.retrieval.reranker import rerank, mmr_deduplication
from app.ingestion.indexer import query_vectors

logger = logging.getLogger(__name__)


async def _fetch_parent_chunks(
    child_chunk_ids: list[str],
    db: AsyncSession,
) -> dict[str, str]:
    """
    Given child chunk IDs, look up their parent chunks and return full content.
    Returns {child_chunk_id: parent_content}.
    """
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.id.in_(child_chunk_ids))
    )
    children = result.scalars().all()

    parent_ids = [c.parent_chunk_id for c in children if c.parent_chunk_id]
    parent_map: dict[str, str] = {}

    if parent_ids:
        result = await db.execute(
            select(DocumentChunk).where(DocumentChunk.id.in_(parent_ids))
        )
        parents = result.scalars().all()
        parent_content_map = {p.id: p.content for p in parents}

        for child in children:
            if child.parent_chunk_id and child.parent_chunk_id in parent_content_map:
                parent_map[child.id] = parent_content_map[child.parent_chunk_id]

    return parent_map


async def retrieve(
    question: str,
    namespaces: list[str],
    db: AsyncSession,
    course_hint: str = "",
    top_k_initial: int = None,
    top_k_final: int = None,
) -> list[dict]:
    """
    Full retrieval pipeline for a user query.

    Args:
        question: Natural language question.
        namespaces: Pinecone namespaces to search (user's enrolled courses).
        db: Database session for parent chunk expansion.
        course_hint: Optional subject hint for HyDE.
        top_k_initial: Candidates from vector search (default from settings).
        top_k_final: Final chunks after re-ranking (default from settings).

    Returns:
        List of chunk dicts with: id, content, metadata, score, rerank_score.
    """
    top_k_initial = top_k_initial or settings.TOP_K_RETRIEVAL
    top_k_final = top_k_final or settings.TOP_K_RERANK

    # ── 1. Embed query with HyDE ──────────────────────────────────────────────
    logger.info(f"Retrieving for: {question[:80]}")
    query_vector = await embed_query_with_hyde(question, context_hint=course_hint)

    # ── 2. Dense vector search across namespaces ──────────────────────────────
    all_candidates: list[dict] = []
    for ns in namespaces:
        try:
            results = query_vectors(query_vector, namespace=ns, top_k=top_k_initial)
            for r in results:
                r["namespace"] = ns
            all_candidates.extend(results)
        except Exception as e:
            logger.warning(f"Vector search failed for namespace {ns}: {e}")

    if not all_candidates:
        logger.warning("No candidates retrieved from vector store.")
        return []

    # De-duplicate by chunk ID (same chunk may appear across namespace searches)
    seen_ids = set()
    unique_candidates = []
    for c in sorted(all_candidates, key=lambda x: x["score"], reverse=True):
        if c["id"] not in seen_ids:
            seen_ids.add(c["id"])
            unique_candidates.append(c)

    # ── 3. Re-rank top candidates ─────────────────────────────────────────────
    logger.info(f"Re-ranking {len(unique_candidates)} candidates")
    reranked = await rerank(question, unique_candidates[:top_k_initial], top_k=top_k_final * 2)

    # ── 4. MMR deduplication ──────────────────────────────────────────────────
    deduplicated = mmr_deduplication(reranked, top_k=top_k_final)

    # ── 5. Parent chunk expansion ─────────────────────────────────────────────
    child_ids = [c["id"] for c in deduplicated]
    parent_map = await _fetch_parent_chunks(child_ids, db)

    final_chunks = []
    for chunk in deduplicated:
        chunk_id = chunk["id"]
        # Use parent content if available (richer context)
        if chunk_id in parent_map:
            display_content = parent_map[chunk_id]
        else:
            display_content = chunk["metadata"].get("content", "")

        final_chunks.append({
            "id": chunk_id,
            "content": display_content,
            "metadata": chunk["metadata"],
            "vector_score": chunk.get("score", 0),
            "rerank_score": chunk.get("rerank_score", 0),
            "namespace": chunk.get("namespace", ""),
        })

    logger.info(f"Retrieved {len(final_chunks)} final chunks")
    return final_chunks
