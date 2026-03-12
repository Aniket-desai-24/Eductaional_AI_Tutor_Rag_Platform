"""
Query API — the main RAG endpoint.
Supports streaming via Server-Sent Events (SSE).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Optional, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.auth.utils import get_current_user
from app.db.models import User, QueryLog, CourseEnrollment, Document, get_db
from app.memory.short_term import get_full_context, append_turn, clear_session
from app.memory.long_term import (
    get_profile_context, get_relevant_past_interactions
)
from app.retrieval.retriever import retrieve
from app.llm.providers import stream_response
from app.llm.prompt_builder import build_prompt, format_citations
from app.tasks.memory_tasks import schedule_profile_update

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/query", tags=["query"])

# Per-user semaphore to limit concurrent LLM calls
_user_semaphores: dict[str, asyncio.Semaphore] = {}


def _get_user_semaphore(user_id: str) -> asyncio.Semaphore:
    if user_id not in _user_semaphores:
        _user_semaphores[user_id] = asyncio.Semaphore(settings.MAX_CONCURRENT_LLM_CALLS_PER_USER)
    return _user_semaphores[user_id]


async def _get_user_namespaces(user: User, db: AsyncSession) -> list[str]:
    """Get all Pinecone namespaces the user is enrolled in."""
    result = await db.execute(
        select(CourseEnrollment).where(CourseEnrollment.user_id == user.id)
    )
    enrollments = result.scalars().all()
    if not enrollments:
        # Fallback: return all namespaces (public access)
        result = await db.execute(select(Document.namespace).distinct())
        return [r[0] for r in result.all() if r[0]]

    course_ids = [e.course_id for e in enrollments]
    result = await db.execute(
        select(Document.namespace)
        .where(Document.course_id.in_(course_ids))
        .distinct()
    )
    return [r[0] for r in result.all() if r[0]]


# ── Schemas ───────────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str
    session_id: str
    namespace: Optional[str] = None   # explicit namespace override


class FeedbackRequest(BaseModel):
    query_log_id: str
    feedback: int   # 1 = helpful, -1 = not helpful


class ConversationHistoryResponse(BaseModel):
    session_id: str
    turns: list[dict]


# ── Streaming generator ───────────────────────────────────────────────────────
async def _sse_stream(
    question: str,
    session_id: str,
    user: User,
    db: AsyncSession,
    namespace_override: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Core RAG pipeline wrapped in an SSE generator.
    Yields SSE-formatted strings.
    """
    start_ms = int(time.time() * 1000)

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    # ── Retrieve namespaces ───────────────────────────────────────────────────
    if namespace_override:
        namespaces = [namespace_override]
    else:
        namespaces = await _get_user_namespaces(user, db)

    if not namespaces:
        yield sse("error", {"message": "You are not enrolled in any courses with content."})
        return

    # ── Load memory ───────────────────────────────────────────────────────────
    st_summary, st_turns = await get_full_context(session_id)
    lt_profile = await get_profile_context(user.id, db)
    past_interactions = await get_relevant_past_interactions(user.id, question, db)

    # ── Retrieve chunks ───────────────────────────────────────────────────────
    yield sse("status", {"message": "Searching knowledge base..."})
    chunks = await retrieve(
        question=question,
        namespaces=namespaces,
        db=db,
        course_hint=lt_profile,
    )

    if not chunks:
        yield sse("status", {"message": "No relevant content found."})
        yield sse("token", {"content": "I couldn't find relevant information in the textbook. Please try rephrasing your question."})
        yield sse("done", {"citations": []})
        return

    citations = format_citations(chunks)
    yield sse("status", {"message": "Generating answer..."})
    yield sse("citations", {"citations": citations})

    # ── Build prompt ──────────────────────────────────────────────────────────
    messages = build_prompt(
        question=question,
        retrieved_chunks=chunks,
        short_term_summary=st_summary,
        short_term_turns=st_turns,
        long_term_profile=lt_profile,
        past_interactions=past_interactions,
    )

    # ── Stream LLM response ───────────────────────────────────────────────────
    sem = _get_user_semaphore(user.id)
    full_answer = []

    async with sem:
        async for token in stream_response(messages, max_tokens=1200):
            full_answer.append(token)
            yield sse("token", {"content": token})

    answer_text = "".join(full_answer)
    latency = int(time.time() * 1000) - start_ms

    # ── Persist to memory & DB ────────────────────────────────────────────────
    await append_turn(session_id, "user", question)
    await append_turn(session_id, "assistant", answer_text)

    log = QueryLog(
        id=str(uuid.uuid4()),
        user_id=user.id,
        session_id=session_id,
        question=question,
        answer=answer_text,
        namespace=namespaces[0] if namespaces else None,
        retrieved_chunks=[{"id": c["id"], "score": c.get("rerank_score", 0)} for c in chunks],
        latency_ms=latency,
    )
    db.add(log)
    await db.flush()

    # ── Trigger async profile update every N turns ────────────────────────────
    _, turns = await get_full_context(session_id)
    if len(turns) % (settings.MEMORY_SUMMARY_EVERY_N_TURNS * 2) == 0:
        schedule_profile_update(user.id, turns)

    yield sse("done", {"query_log_id": log.id, "latency_ms": latency, "citations": citations})


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("")
async def query(
    payload: QueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Stream a RAG answer to a question via Server-Sent Events.

    Frontend connects with EventSource and listens for events:
    - status: processing status update
    - citations: chunk citations metadata
    - token: partial answer text
    - done: completion with latency and query_log_id
    - error: error message
    """
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if len(payload.question) > 2000:
        raise HTTPException(status_code=400, detail="Question too long (max 2000 chars)")

    async def event_generator():
        async for chunk in _sse_stream(
            question=payload.question,
            session_id=payload.session_id,
            user=user,
            db=db,
            namespace_override=payload.namespace,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/history", response_model=ConversationHistoryResponse)
async def get_history(
    session_id: str = Query(...),
    user: User = Depends(get_current_user),
):
    """Retrieve conversation history for the current session."""
    _, turns = await get_full_context(session_id)
    return ConversationHistoryResponse(session_id=session_id, turns=turns)


@router.delete("/history")
async def clear_history(
    session_id: str = Query(...),
    user: User = Depends(get_current_user),
):
    """Clear conversation history for a session."""
    await clear_session(session_id)
    return {"message": "Conversation cleared"}


@router.post("/feedback")
async def submit_feedback(
    payload: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit thumbs-up/down feedback on a response."""
    result = await db.execute(
        select(QueryLog).where(QueryLog.id == payload.query_log_id, QueryLog.user_id == user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Query log not found")
    if payload.feedback not in (1, -1):
        raise HTTPException(status_code=400, detail="Feedback must be 1 or -1")
    log.feedback = payload.feedback
    await db.flush()
    return {"message": "Feedback recorded"}
