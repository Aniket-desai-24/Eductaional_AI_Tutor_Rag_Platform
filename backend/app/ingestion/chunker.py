"""
Chunker — parent-child semantic chunking strategy for educational content.
Parent chunks (1024 tokens) are stored for generation context.
Child chunks (256 tokens) are used for precise retrieval.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

import tiktoken

from app.config import settings
from app.db.models import ContentType
from app.ingestion.pdf_parser import ParsedDocument, ParsedPage


# ── Tokenizer ────────────────────────────────────────────────────────────────
_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    tokens = _enc.encode(text)
    return _enc.decode(tokens[:max_tokens])


# ── Chunk dataclass ───────────────────────────────────────────────────────────
@dataclass
class Chunk:
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_chunk_id: Optional[str] = None
    content: str = ""
    content_type: str = "text"
    chapter: Optional[int] = None
    section: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    image_url: Optional[str] = None        # populated after S3 upload
    image_bytes: Optional[bytes] = None    # temporary, used for captioning
    metadata: dict = field(default_factory=dict)
    is_parent: bool = False


# ── Sentence splitter ─────────────────────────────────────────────────────────
_SENTENCE_ENDS = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving abbreviations heuristically."""
    sentences = _SENTENCE_ENDS.split(text)
    return [s.strip() for s in sentences if s.strip()]


# ── Text chunking ─────────────────────────────────────────────────────────────
def _split_text_into_chunks(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Split text into overlapping token-aware chunks."""
    sentences = split_sentences(text)
    chunks: list[str] = []
    current_tokens: list[str] = []
    current_count = 0

    for sentence in sentences:
        sent_tokens = _enc.encode(sentence + " ")
        if current_count + len(sent_tokens) > chunk_size and current_tokens:
            chunk_text = _enc.decode(current_tokens).strip()
            if chunk_text:
                chunks.append(chunk_text)
            # Keep overlap
            overlap_tokens = current_tokens[-overlap:] if overlap > 0 else []
            current_tokens = overlap_tokens + list(sent_tokens)
            current_count = len(current_tokens)
        else:
            current_tokens.extend(sent_tokens)
            current_count += len(sent_tokens)

    if current_tokens:
        chunk_text = _enc.decode(current_tokens).strip()
        if chunk_text:
            chunks.append(chunk_text)

    return chunks


# ── Main Chunker ──────────────────────────────────────────────────────────────
def chunk_document(doc: ParsedDocument, document_id: str) -> list[Chunk]:
    """
    Convert a ParsedDocument into a list of Chunks using parent-child strategy.

    Returns all chunks (parents + children) together.
    Children reference their parent via parent_chunk_id.
    """
    all_chunks: list[Chunk] = []

    for page in doc.pages:
        # ── Text chunks ──────────────────────────────────────────────────────
        if page.cleaned_text.strip():
            text_to_chunk = page.cleaned_text
            # Add section context prefix
            prefix = ""
            if page.chapter:
                prefix += f"Chapter {page.chapter}. "
            if page.section:
                prefix += f"Section: {page.section}. "

            parent_texts = _split_text_into_chunks(
                text_to_chunk,
                chunk_size=settings.PARENT_CHUNK_SIZE,
                overlap=0,
            )

            for parent_text in parent_texts:
                parent_id = str(uuid.uuid4())
                parent_content = (prefix + parent_text).strip()

                parent_chunk = Chunk(
                    chunk_id=parent_id,
                    content=parent_content,
                    content_type=ContentType.text.value,
                    chapter=page.chapter,
                    section=page.section,
                    page_start=page.page_number,
                    page_end=page.page_number,
                    is_parent=True,
                    metadata={
                        "document_id": document_id,
                        "has_equations": page.has_equations,
                    }
                )
                all_chunks.append(parent_chunk)

                # Create child chunks from this parent
                child_texts = _split_text_into_chunks(
                    parent_content,
                    chunk_size=settings.CHUNK_SIZE,
                    overlap=settings.CHUNK_OVERLAP,
                )
                for child_text in child_texts:
                    child_chunk = Chunk(
                        parent_chunk_id=parent_id,
                        content=child_text,
                        content_type=ContentType.text.value,
                        chapter=page.chapter,
                        section=page.section,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        is_parent=False,
                        metadata={"document_id": document_id}
                    )
                    all_chunks.append(child_chunk)

        # ── Image chunks (captions added later) ──────────────────────────────
        for img in page.images:
            img_chunk = Chunk(
                content=f"[Image on page {page.page_number} — caption pending]",
                content_type=ContentType.image_caption.value,
                chapter=page.chapter,
                section=page.section,
                page_start=page.page_number,
                page_end=page.page_number,
                image_bytes=img.image_bytes,
                is_parent=False,
                metadata={
                    "document_id": document_id,
                    "image_extension": img.extension,
                }
            )
            all_chunks.append(img_chunk)

        # ── Table chunks ─────────────────────────────────────────────────────
        for table in page.tables:
            table_content = f"Table on page {page.page_number}:\n{table.raw_text}"
            table_chunk = Chunk(
                content=table_content,
                content_type=ContentType.table.value,
                chapter=page.chapter,
                section=page.section,
                page_start=page.page_number,
                page_end=page.page_number,
                is_parent=False,
                metadata={
                    "document_id": document_id,
                    "structured_data": table.structured_data,
                }
            )
            all_chunks.append(table_chunk)

    return all_chunks
