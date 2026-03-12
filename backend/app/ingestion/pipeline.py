"""
Ingestion Pipeline Orchestrator
Ties together: PDF parsing → chunking → captioning → embedding → indexing → DB persistence.
"""
from __future__ import annotations

import logging
import re
import uuid
import shutil
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Document, DocumentChunk, DocumentStatus, ContentType
from app.ingestion.pdf_parser import parse_pdf
from app.ingestion.chunker import chunk_document, Chunk
from app.ingestion.embedder import embed_chunks, caption_image_chunks
from app.ingestion.indexer import upsert_chunks, delete_namespace, ensure_index_exists

logger = logging.getLogger(__name__)


# ── S3 helper ─────────────────────────────────────────────────────────────────
def _s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )


def upload_image_to_s3(image_bytes: bytes, doc_id: str, chunk_id: str, ext: str) -> str:
    """Upload extracted image to S3 and return a public URL."""
    s3 = _s3_client()
    key = f"images/{doc_id}/{chunk_id}.{ext}"
    try:
        s3.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=image_bytes,
            ContentType=f"image/{ext}",
        )
        return f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
    except ClientError as e:
        logger.warning(f"S3 upload failed for {key}: {e}")
        return ""


def download_from_s3(s3_key: str, local_path: str):
    """Download a file from S3 to a local path."""
    s3 = _s3_client()
    s3.download_file(settings.AWS_S3_BUCKET, s3_key, local_path)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", text.lower())[:60]


# ── Main pipeline ─────────────────────────────────────────────────────────────
async def run_ingestion_pipeline(
    document_id: str,
    s3_key: str,
    namespace: str,
    db: AsyncSession,
) -> dict:
    """
    Full ingestion pipeline for a single document.

    Steps:
      1. Download PDF from S3 (or use local uploaded file path)
      2. Parse PDF (text + images + tables)
      3. Chunk document (parent + child strategy)
      4. Caption images via GPT-4V
      5. Upload images to S3 and attach URLs
      6. Embed all chunks
      7. Upsert to Pinecone
      8. Persist chunks to PostgreSQL
      9. Mark document as completed

    Returns:
        Summary dict with counts.
    """
    # ── 0. Mark as processing ─────────────────────────────────────────────────
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc_record: Document = result.scalar_one_or_none()
    if not doc_record:
        raise ValueError(f"Document {document_id} not found in DB")

    doc_record.status = DocumentStatus.processing
    await db.flush()

    local_path = f"/tmp/{document_id}.pdf"

    try:
        # ── 1. Download from S3 ───────────────────────────────────────────────
        source_path = Path(s3_key)
        if source_path.exists():
            logger.info(f"[{document_id}] Using local uploaded file: {s3_key}")
            shutil.copyfile(source_path, local_path)
        else:
            logger.info(f"[{document_id}] Downloading from S3: {s3_key}")
            download_from_s3(s3_key, local_path)

        # ── 2. Parse PDF ──────────────────────────────────────────────────────
        logger.info(f"[{document_id}] Parsing PDF")
        parsed_doc = parse_pdf(local_path)
        doc_record.total_pages = parsed_doc.total_pages

        # ── 3. Chunk ──────────────────────────────────────────────────────────
        logger.info(f"[{document_id}] Chunking")
        chunks: list[Chunk] = chunk_document(parsed_doc, document_id)
        logger.info(f"[{document_id}] Created {len(chunks)} chunks")

        # ── 4. Caption images ─────────────────────────────────────────────────
        logger.info(f"[{document_id}] Captioning images")
        chunks = await caption_image_chunks(chunks)

        # ── 5. Upload images to S3 ────────────────────────────────────────────
        logger.info(f"[{document_id}] Uploading images to S3")
        for chunk in chunks:
            if chunk.image_bytes and settings.AWS_ACCESS_KEY_ID:
                ext = chunk.metadata.get("image_extension", "png")
                url = upload_image_to_s3(chunk.image_bytes, document_id, chunk.chunk_id, ext)
                chunk.image_url = url
            chunk.image_bytes = None   # free memory

        # ── 6. Embed ──────────────────────────────────────────────────────────
        logger.info(f"[{document_id}] Embedding chunks")
        vectors = await embed_chunks(chunks)

        # ── 7. Upsert to Pinecone ─────────────────────────────────────────────
        logger.info(f"[{document_id}] Upserting to Pinecone namespace: {namespace}")
        ensure_index_exists()
        upserted_count = upsert_chunks(chunks, vectors, namespace)

        # ── 8. Persist to DB ──────────────────────────────────────────────────
        logger.info(f"[{document_id}] Persisting {len(chunks)} chunks to DB")
        for chunk in chunks:
            ct_map = {
                "text": ContentType.text,
                "image_caption": ContentType.image_caption,
                "table": ContentType.table,
                "equation": ContentType.equation,
                "heading": ContentType.heading,
            }
            db_chunk = DocumentChunk(
                id=chunk.chunk_id,
                document_id=document_id,
                parent_chunk_id=chunk.parent_chunk_id,
                content=chunk.content,
                content_type=ct_map.get(chunk.content_type, ContentType.text),
                chapter=chunk.chapter,
                section=chunk.section,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                image_url=chunk.image_url,
                chunk_metadata=chunk.metadata,
                vector_id=chunk.chunk_id if chunk.chunk_id in vectors else None,
            )
            db.add(db_chunk)

        # ── 9. Finalise ───────────────────────────────────────────────────────
        from datetime import datetime, timezone
        doc_record.status = DocumentStatus.completed
        doc_record.total_chunks = len(chunks)
        doc_record.completed_at = datetime.now(timezone.utc)
        await db.flush()

        logger.info(f"[{document_id}] Ingestion complete. {upserted_count} vectors indexed.")
        return {
            "document_id": document_id,
            "total_pages": parsed_doc.total_pages,
            "total_chunks": len(chunks),
            "vectors_upserted": upserted_count,
            "namespace": namespace,
        }

    except Exception as e:
        logger.error(f"[{document_id}] Ingestion failed: {e}", exc_info=True)
        doc_record.status = DocumentStatus.failed
        doc_record.error_message = str(e)
        await db.flush()
        raise

    finally:
        # Clean up temp file
        Path(local_path).unlink(missing_ok=True)
