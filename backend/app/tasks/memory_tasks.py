"""Celery tasks — long-term memory profile updates."""
import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.memory_tasks.update_user_profile_task",
    bind=True,
    max_retries=1,
)
def update_user_profile_task(self, user_id: str, session_turns: list):
    async def _run():
        from app.memory.long_term import update_profile_from_session
        from app.db.models import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            try:
                await update_profile_from_session(user_id, session_turns, db)
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.warning(f"Profile update failed for {user_id[:8]}: {e}")

    asyncio.run(_run())


def schedule_profile_update(user_id: str, turns: list):
    """Fire-and-forget profile update task."""
    try:
        update_user_profile_task.delay(user_id, turns)
    except Exception as e:
        logger.warning(f"Could not schedule profile update: {e}")
