"""Memory API — user profile and GDPR endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import get_current_user
from app.db.models import User, get_db
from app.memory.long_term import get_or_create_profile, delete_user_memory
from app.memory.short_term import clear_session

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's long-term learning profile."""
    profile = await get_or_create_profile(user.id, db)
    return {
        "user_id": user.id,
        "learning_level": profile.learning_level,
        "subject_mastery": profile.subject_mastery,
        "weak_areas": profile.weak_areas,
        "strong_areas": profile.strong_areas,
        "frequently_asked_topics": profile.frequently_asked_topics,
        "total_queries": profile.total_queries,
        "last_active": profile.last_active.isoformat() if profile.last_active else None,
    }


@router.delete("/profile")
async def delete_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR: permanently delete all long-term memory for this user."""
    await delete_user_memory(user.id, db)
    return {"message": "Long-term memory deleted successfully"}
