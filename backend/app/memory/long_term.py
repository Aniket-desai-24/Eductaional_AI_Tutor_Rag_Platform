"""
Long-term memory — persistent user learning profile stored in PostgreSQL.
Provides personalisation context for RAG prompt construction.

[NOTE] Previous OpenAI implementation preserved below for reference.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import UserMemoryProfile, PastInteraction
from app.llm.groq_http import chat_completion_text

logger = logging.getLogger(__name__)

# [DEPRECATED] OpenAI client
# _client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


# ── Profile CRUD ──────────────────────────────────────────────────────────────
async def get_or_create_profile(user_id: str, db: AsyncSession) -> UserMemoryProfile:
    result = await db.execute(
        select(UserMemoryProfile).where(UserMemoryProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserMemoryProfile(
            id=str(uuid.uuid4()),
            user_id=user_id,
            subject_mastery={},
            weak_areas=[],
            strong_areas=[],
            frequently_asked_topics=[],
            learning_level="intermediate",
            total_queries=0,
        )
        db.add(profile)
        await db.flush()
    return profile


async def get_profile_context(user_id: str, db: AsyncSession) -> str:
    """
    Build a short profile summary to inject into the LLM prompt.
    Returns an empty string if the user has no profile yet.
    """
    result = await db.execute(
        select(UserMemoryProfile).where(UserMemoryProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile or profile.total_queries == 0:
        return ""

    lines = [f"Student level: {profile.learning_level}."]
    if profile.strong_areas:
        lines.append(f"Strong in: {', '.join(profile.strong_areas[:3])}.")
    if profile.weak_areas:
        lines.append(f"Needs help with: {', '.join(profile.weak_areas[:3])}.")
    if profile.frequently_asked_topics:
        lines.append(f"Recently studied: {', '.join(profile.frequently_asked_topics[:3])}.")
    return " ".join(lines)


async def get_relevant_past_interactions(
    user_id: str,
    question: str,
    db: AsyncSession,
    top_k: int = 3,
) -> list[dict]:
    """
    Retrieve semantically relevant past Q&A pairs for this user.
    Currently uses keyword matching; can be upgraded to vector search.
    """
    result = await db.execute(
        select(UserMemoryProfile).where(UserMemoryProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return []

    # Load recent interactions and do simple keyword overlap ranking
    result = await db.execute(
        select(PastInteraction)
        .where(PastInteraction.profile_id == profile.id)
        .order_by(PastInteraction.created_at.desc())
        .limit(50)
    )
    interactions = result.scalars().all()

    q_words = set(question.lower().split())
    scored = []
    for interaction in interactions:
        i_words = set(interaction.question.lower().split())
        overlap = len(q_words & i_words) / max(len(q_words | i_words), 1)
        scored.append((overlap, interaction))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"question": i.question, "answer_summary": i.answer_summary}
        for _, i in scored[:top_k]
        if scored and scored[0][0] > 0.1  # only if reasonably relevant
    ]


# ── Profile updates (called asynchronously at session end) ────────────────────
async def update_profile_from_session(
    user_id: str,
    session_turns: list[dict],
    db: AsyncSession,
):
    """
    Analyse a completed session and update the user's long-term profile.
    Extracts: topics, weak areas, strong areas, mastery scores.
    Uses Groq Llama for analysis.
    """
    if not session_turns:
        return

    profile = await get_or_create_profile(user_id, db)

    # Summarise session with LLM
    transcript = "\n".join(f"{t['role'].upper()}: {t['content'][:300]}" for t in session_turns[:20])

    try:
        response_text = await chat_completion_text(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Analyse this tutoring session transcript. "
                        "Return JSON with keys: "
                        "topics (list of topics discussed), "
                        "weak_areas (topics the student struggled with), "
                        "strong_areas (topics they showed understanding of), "
                        "level (beginner/intermediate/advanced). "
                        "Be concise. Return ONLY valid JSON."
                    ),
                },
                {"role": "user", "content": transcript},
            ],
            model=settings.LLM_MODEL,
            max_tokens=400,
            temperature=0,
        )
        import json
        analysis = json.loads(response_text.strip())
    except Exception as e:
        logger.warning(f"Profile analysis failed: {e}")
        return

    # Update profile fields
    new_topics: list[str] = analysis.get("topics", [])
    new_weak: list[str] = analysis.get("weak_areas", [])
    new_strong: list[str] = analysis.get("strong_areas", [])
    new_level: str = analysis.get("level", profile.learning_level)

    profile.frequently_asked_topics = list(
        dict.fromkeys(new_topics + profile.frequently_asked_topics)
    )[:20]
    profile.weak_areas = list(dict.fromkeys(new_weak + profile.weak_areas))[:10]
    profile.strong_areas = list(dict.fromkeys(new_strong + profile.strong_areas))[:10]
    profile.learning_level = new_level
    profile.total_queries += len([t for t in session_turns if t["role"] == "user"])
    profile.last_active = datetime.now(timezone.utc)

    # Store last Q&A pair as a past interaction
    user_turns = [t for t in session_turns if t["role"] == "user"]
    assistant_turns = [t for t in session_turns if t["role"] == "assistant"]
    if user_turns and assistant_turns:
        last_q = user_turns[-1]["content"]
        last_a = assistant_turns[-1]["content"][:500]
        interaction = PastInteraction(
            id=str(uuid.uuid4()),
            profile_id=profile.id,
            question=last_q,
            answer_summary=last_a,
            topics=new_topics[:5],
        )
        db.add(interaction)

    await db.flush()
    logger.info(f"Updated long-term profile for user {user_id[:8]}")


# [DEPRECATED] OpenAI implementation
# async def update_profile_from_session(
#     user_id: str,
#     session_turns: list[dict],
#     db: AsyncSession,
# ):
#     """Analyse a completed session and update the user's long-term profile."""
#     if not session_turns:
#         return
#     profile = await get_or_create_profile(user_id, db)
#     transcript = "\n".join(f"{t['role'].upper()}: {t['content'][:300]}" for t in session_turns[:20])
#     try:
#         resp = await _client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[...],
#             max_tokens=400,
#             temperature=0,
#         )
#         analysis = json.loads(resp.choices[0].message.content.strip())
#     except Exception as e:
#         logger.warning(f"Profile analysis failed: {e}")
#         return
#     # Update profile fields...


async def delete_user_memory(user_id: str, db: AsyncSession):
    """GDPR: delete all long-term memory for a user."""
    result = await db.execute(
        select(UserMemoryProfile).where(UserMemoryProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile:
        await db.delete(profile)
        await db.flush()
        logger.info(f"Deleted memory profile for user {user_id[:8]}")

