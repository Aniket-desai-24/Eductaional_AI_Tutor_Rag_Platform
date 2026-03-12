"""
Indexer — stores chunk vectors in Pinecone with rich metadata.
Supports upsert, delete, and namespace management.
"""
from __future__ import annotations

import logging
from typing import Optional

from pinecone import Pinecone, ServerlessSpec

from app.config import settings
from app.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 100


def _get_pinecone() -> Pinecone:
    return Pinecone(api_key=settings.PINECONE_API_KEY)


def ensure_index_exists():
    """Create the Pinecone index if it doesn't already exist."""
    pc = _get_pinecone()
    existing = [idx.name for idx in pc.list_indexes()]
    if settings.PINECONE_INDEX_NAME not in existing:
        logger.info(f"Creating Pinecone index: {settings.PINECONE_INDEX_NAME}")
        pc.create_index(
            name=settings.PINECONE_INDEX_NAME,
            dimension=settings.EMBEDDING_DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        logger.info("Index created.")
    else:
        logger.info("Index already exists.")


def _build_pinecone_vector(chunk: Chunk, vector: list[float], namespace: str) -> dict:
    """Build a Pinecone upsert record."""
    return {
        "id": chunk.chunk_id,
        "values": vector,
        "metadata": {
            "content": chunk.content[:1000],          # Pinecone metadata limit
            "content_type": chunk.content_type,
            "namespace": namespace,
            "chapter": chunk.chapter or 0,
            "section": chunk.section or "",
            "page_start": chunk.page_start or 0,
            "page_end": chunk.page_end or 0,
            "image_url": chunk.image_url or "",
            "parent_chunk_id": chunk.parent_chunk_id or "",
            "is_parent": chunk.is_parent,
            "document_id": chunk.metadata.get("document_id", ""),
        },
    }


def upsert_chunks(
    chunks: list[Chunk],
    vectors: dict[str, list[float]],
    namespace: str,
) -> int:
    """
    Upsert all chunks that have vectors into Pinecone.

    Args:
        chunks: List of Chunk objects.
        vectors: Map of chunk_id -> embedding vector.
        namespace: Pinecone namespace (e.g. 'physics_grade10').

    Returns:
        Number of vectors upserted.
    """
    pc = _get_pinecone()
    index = pc.Index(settings.PINECONE_INDEX_NAME)

    records = []
    for chunk in chunks:
        if chunk.chunk_id in vectors:
            records.append(_build_pinecone_vector(chunk, vectors[chunk.chunk_id], namespace))

    if not records:
        logger.warning("No records to upsert.")
        return 0

    batches = [records[i:i + UPSERT_BATCH_SIZE] for i in range(0, len(records), UPSERT_BATCH_SIZE)]
    total = 0
    for batch_idx, batch in enumerate(batches):
        index.upsert(vectors=batch, namespace=namespace)
        total += len(batch)
        logger.info(f"  Upserted batch {batch_idx + 1}/{len(batches)} ({len(batch)} vectors)")

    logger.info(f"Total upserted: {total} vectors to namespace '{namespace}'")
    return total


def delete_namespace(namespace: str):
    """Delete all vectors in a namespace (for re-ingestion)."""
    pc = _get_pinecone()
    index = pc.Index(settings.PINECONE_INDEX_NAME)
    index.delete(delete_all=True, namespace=namespace)
    logger.info(f"Deleted all vectors in namespace: {namespace}")


def query_vectors(
    query_vector: list[float],
    namespace: str,
    top_k: int = 20,
    filter_dict: Optional[dict] = None,
) -> list[dict]:
    """
    Query the vector store for similar chunks.

    Returns list of {id, score, metadata} dicts.
    """
    pc = _get_pinecone()
    index = pc.Index(settings.PINECONE_INDEX_NAME)

    kwargs = {
        "vector": query_vector,
        "top_k": top_k,
        "namespace": namespace,
        "include_metadata": True,
    }
    if filter_dict:
        kwargs["filter"] = filter_dict

    result = index.query(**kwargs)
    return [
        {"id": m.id, "score": m.score, "metadata": m.metadata}
        for m in result.matches
    ]


def get_index_stats(namespace: Optional[str] = None) -> dict:
    """Return index statistics, optionally for a specific namespace."""
    pc = _get_pinecone()
    index = pc.Index(settings.PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()
    if namespace:
        ns_stats = stats.namespaces.get(namespace, {})
        return {"namespace": namespace, "vector_count": getattr(ns_stats, "vector_count", 0)}
    return {"total_vector_count": stats.total_vector_count, "namespaces": dict(stats.namespaces)}
