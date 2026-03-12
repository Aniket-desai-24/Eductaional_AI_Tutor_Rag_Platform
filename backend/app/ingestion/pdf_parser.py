"""
PDF Parser — extracts text, images, tables, and equations from textbook PDFs.
Uses PyMuPDF for layout-aware extraction and Camelot for table detection.
"""
from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class ParsedImage:
    page_number: int
    image_index: int
    image_bytes: bytes
    extension: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    caption: Optional[str] = None            # filled in later by vision LLM


@dataclass
class ParsedTable:
    page_number: int
    raw_text: str
    structured_data: list[list[str]]
    caption: Optional[str] = None


@dataclass
class ParsedPage:
    page_number: int
    raw_text: str
    cleaned_text: str
    images: list[ParsedImage] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    has_equations: bool = False
    chapter: Optional[int] = None
    section: Optional[str] = None


@dataclass
class ParsedDocument:
    total_pages: int
    pages: list[ParsedPage]
    title: Optional[str] = None
    author: Optional[str] = None


# ── Heading / chapter detection patterns ─────────────────────────────────────
_CHAPTER_RE = re.compile(r"^(chapter|ch\.?)\s+(\d+)", re.IGNORECASE)
_SECTION_RE = re.compile(r"^(\d+\.\d+\.?\s+.{3,60})$", re.MULTILINE)
_EQUATION_MARKERS = [r"\\frac", r"\\sum", r"\\int", r"\$", r"=\s*\d", r"≤", r"≥", r"∑", r"∫"]


def _looks_like_equation(text: str) -> bool:
    return any(re.search(p, text) for p in _EQUATION_MARKERS)


def _clean_text(raw: str) -> str:
    """Remove common PDF artefacts: ligatures, soft-hyphens, repeated spaces."""
    text = raw
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")   # fi, fl ligatures
    text = text.replace("\xad", "")                                # soft hyphen
    text = re.sub(r"-\n([a-z])", r"\1", text)                      # re-join hyphenated words
    text = re.sub(r"[ \t]+", " ", text)                            # collapse spaces
    text = re.sub(r"\n{3,}", "\n\n", text)                        # collapse blank lines
    return text.strip()


def _detect_chapter(text: str) -> Optional[int]:
    m = _CHAPTER_RE.search(text[:200])
    if m:
        try:
            return int(m.group(2))
        except ValueError:
            return None
    return None


def _detect_section(text: str) -> Optional[str]:
    m = _SECTION_RE.search(text[:500])
    return m.group(1).strip() if m else None


def _extract_tables_from_page(page: fitz.Page) -> list[ParsedTable]:
    """Use PyMuPDF's built-in table finder."""
    tables = []
    try:
        tab_finder = page.find_tables()
        for tab in tab_finder.tables:
            try:
                data = tab.extract()
                rows = [[str(cell) if cell else "" for cell in row] for row in data]
                raw = "\n".join(" | ".join(row) for row in rows)
                tables.append(ParsedTable(
                    page_number=page.number + 1,
                    raw_text=raw,
                    structured_data=rows,
                ))
            except Exception as e:
                logger.warning(f"Table extraction error on page {page.number}: {e}")
    except Exception:
        pass   # older PyMuPDF without find_tables
    return tables


def _extract_images_from_page(doc: fitz.Document, page: fitz.Page, min_size: int = 100) -> list[ParsedImage]:
    """Extract embedded raster images from a page."""
    images = []
    image_list = page.get_images(full=True)
    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]
        try:
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            ext = base_image["ext"]
            # Filter tiny decorative images
            pil = Image.open(io.BytesIO(img_bytes))
            w, h = pil.size
            if w < min_size or h < min_size:
                continue
            # Get bounding box from page
            rects = page.get_image_rects(xref)
            bbox = rects[0] if rects else (0, 0, 0, 0)
            images.append(ParsedImage(
                page_number=page.number + 1,
                image_index=img_idx,
                image_bytes=img_bytes,
                extension=ext,
                bbox=tuple(bbox),
            ))
        except Exception as e:
            logger.warning(f"Image extraction failed xref={xref}: {e}")
    return images


def parse_pdf(file_path: str | Path) -> ParsedDocument:
    """
    Main entry point — parse a PDF textbook into structured pages.

    Args:
        file_path: Path to the PDF file.

    Returns:
        ParsedDocument with per-page text, images, and tables.
    """
    file_path = Path(file_path)
    logger.info(f"Parsing PDF: {file_path.name}")

    doc = fitz.open(str(file_path))
    meta = doc.metadata

    parsed_pages: list[ParsedPage] = []
    current_chapter: Optional[int] = None
    current_section: Optional[str] = None

    for page_obj in doc:
        page_num = page_obj.number + 1
        raw_text = page_obj.get_text("text")
        cleaned = _clean_text(raw_text)

        # Update chapter/section if detected
        ch = _detect_chapter(cleaned)
        if ch is not None:
            current_chapter = ch
        sec = _detect_section(cleaned)
        if sec:
            current_section = sec

        images = _extract_images_from_page(doc, page_obj)
        tables = _extract_tables_from_page(page_obj)
        has_eq = _looks_like_equation(cleaned)

        parsed_pages.append(ParsedPage(
            page_number=page_num,
            raw_text=raw_text,
            cleaned_text=cleaned,
            images=images,
            tables=tables,
            has_equations=has_eq,
            chapter=current_chapter,
            section=current_section,
        ))

    doc.close()
    logger.info(f"Parsed {len(parsed_pages)} pages from {file_path.name}")

    return ParsedDocument(
        total_pages=len(parsed_pages),
        pages=parsed_pages,
        title=meta.get("title") or file_path.stem,
        author=meta.get("author"),
    )
