"""
Prompt Builder — assembles the full RAG prompt with:
  - System instructions
  - Long-term user profile
  - Short-term conversation history
  - Retrieved chunks (with source labels)
  - Current question
"""
from __future__ import annotations

from typing import Optional


SYSTEM_PROMPT = """You are EDU-RAG, an expert AI tutor for educational institutions. \
Your answers are grounded exclusively in the provided textbook passages below.

RULES:
1. Answer ONLY using information from the provided [Chunk-N] passages.
2. Cite your sources inline as [Chunk-1], [Chunk-2], etc.
3. If the answer cannot be found in the passages, say: "I couldn't find this in the available textbook content. Please consult your teacher."
4. Adjust your explanation to the student's level (provided in their profile).
5. Be clear, educational, and encouraging. Use examples where helpful.
6. For mathematical content, use plain language descriptions.
7. Never hallucinate facts not present in the passages.
"""


def build_prompt(
    question: str,
    retrieved_chunks: list[dict],
    short_term_summary: Optional[str],
    short_term_turns: list[dict],
    long_term_profile: Optional[str],
    past_interactions: Optional[list[dict]] = None,
) -> list[dict]:
    """
    Build the full message list for the LLM.

    Args:
        question: Current user question.
        retrieved_chunks: [{id, content, metadata}] from retrieval.
        short_term_summary: Compressed summary of older turns (may be None).
        short_term_turns: Recent conversation turns [{role, content}].
        long_term_profile: User profile string (may be None).
        past_interactions: Relevant past Q&A pairs (may be None).

    Returns:
        List of OpenAI-format message dicts.
    """
    messages: list[dict] = []

    # ── System ────────────────────────────────────────────────────────────────
    system_content = SYSTEM_PROMPT

    if long_term_profile:
        system_content += f"\n\nSTUDENT PROFILE:\n{long_term_profile}"

    if short_term_summary:
        system_content += f"\n\nEARLIER IN THIS SESSION (summary):\n{short_term_summary}"

    if past_interactions:
        past_str = "\n".join(
            f"Q: {p['question']}\nA (summary): {p['answer_summary']}"
            for p in past_interactions
        )
        system_content += f"\n\nRELEVANT PAST INTERACTIONS:\n{past_str}"

    # ── Retrieved chunks ──────────────────────────────────────────────────────
    if retrieved_chunks:
        context_parts = []
        for i, chunk in enumerate(retrieved_chunks, 1):
            meta = chunk["metadata"]
            source_info = []
            if meta.get("chapter"):
                source_info.append(f"Chapter {meta['chapter']}")
            if meta.get("section"):
                source_info.append(meta["section"])
            if meta.get("page_start"):
                source_info.append(f"Page {meta['page_start']}")

            source_label = " | ".join(source_info) if source_info else "Textbook"
            content = chunk.get("content", meta.get("content", ""))
            context_parts.append(f"[Chunk-{i}] ({source_label}):\n{content}")

        context_block = "\n\n---\n\n".join(context_parts)
        system_content += f"\n\nTEXTBOOK PASSAGES:\n\n{context_block}"

    messages.append({"role": "system", "content": system_content})

    # ── Recent conversation history ───────────────────────────────────────────
    for turn in short_term_turns:
        messages.append({"role": turn["role"], "content": turn["content"]})

    # ── Current question ──────────────────────────────────────────────────────
    # Only add if it's not already the last user turn
    if not short_term_turns or short_term_turns[-1].get("content") != question:
        messages.append({"role": "user", "content": question})

    return messages


def format_citations(retrieved_chunks: list[dict]) -> list[dict]:
    """
    Build the citations payload returned to the frontend.
    Each citation links to source chunk metadata for display.
    """
    citations = []
    for i, chunk in enumerate(retrieved_chunks, 1):
        meta = chunk["metadata"]
        citations.append({
            "label": f"Chunk-{i}",
            "chunk_id": chunk["id"],
            "chapter": meta.get("chapter"),
            "section": meta.get("section", ""),
            "page_start": meta.get("page_start"),
            "page_end": meta.get("page_end"),
            "content_type": meta.get("content_type", "text"),
            "image_url": meta.get("image_url", ""),
            "snippet": meta.get("content", "")[:200],
            "score": round(chunk.get("rerank_score", chunk.get("vector_score", 0)), 3),
        })
    return citations
