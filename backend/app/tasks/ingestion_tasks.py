"""Celery tasks — document ingestion."""
import asyncio
import logging

from app.tasks.celery_app import celery_app
from app.db.models import AsyncSessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.ingestion_tasks.ingest_document_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def ingest_document_task(self, document_id: str, s3_key: str, namespace: str):
    """Async ingestion pipeline wrapped for Celery."""
    async def _run():
        from app.ingestion.pipeline import run_ingestion_pipeline
        async with AsyncSessionLocal() as db:
            try:
                result = await run_ingestion_pipeline(document_id, s3_key, namespace, db)
                await db.commit()
                logger.info(f"Ingestion complete: {result}")
                return result
            except Exception as e:
                await db.rollback()
                logger.error(f"Ingestion task failed: {e}", exc_info=True)
                raise self.retry(exc=e)

    return asyncio.run(_run())
