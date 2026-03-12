"""Admin API — document ingestion, course management, analytics."""
from __future__ import annotations

import re
import uuid
from typing import Optional

import boto3
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import get_current_user, require_admin
from app.config import settings
from app.db.models import User, Document, DocumentStatus, Course, CourseEnrollment, QueryLog, get_db
from app.tasks.ingestion_tasks import ingest_document_task

router = APIRouter(prefix="/admin", tags=["admin"])


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", text.lower())[:60]


# ── Course management ─────────────────────────────────────────────────────────
class CreateCourseRequest(BaseModel):
    name: str
    description: Optional[str] = None


@router.post("/courses", status_code=201)
async def create_course(
    payload: CreateCourseRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    course = Course(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        created_by=admin.id,
    )
    db.add(course)
    await db.flush()
    return {"id": course.id, "name": course.name}


@router.get("/courses")
async def list_courses(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course))
    courses = result.scalars().all()
    return [{"id": c.id, "name": c.name, "description": c.description} for c in courses]


@router.post("/courses/{course_id}/enroll/{user_id}")
async def enroll_user(
    course_id: str,
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    enrollment = CourseEnrollment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        course_id=course_id,
    )
    db.add(enrollment)
    await db.flush()
    return {"message": "User enrolled"}


# ── Document ingestion ────────────────────────────────────────────────────────
@router.post("/ingest", status_code=202)
async def ingest_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    course_id: Optional[str] = Form(None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a textbook PDF and trigger the async ingestion pipeline.

    Returns a document_id that can be polled for status.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # ── Upload to S3 ──────────────────────────────────────────────────────────
    doc_id = str(uuid.uuid4())
    s3_key = f"documents/{doc_id}/{file.filename}"
    namespace = _slug(title) + "_" + doc_id[:8]

    if settings.AWS_ACCESS_KEY_ID:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        file_bytes = await file.read()
        s3.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=s3_key,
            Body=file_bytes,
            ContentType="application/pdf",
        )
    # else:
    #     # Dev mode: save locally
    #     import os
    #     os.makedirs(f"/tmp/edu-rag-docs/{doc_id}", exist_ok=True)
    #     local_path = f"/tmp/edu-rag-docs/{doc_id}/{file.filename}"
    #     content = await file.read()
    #     with open(local_path, "wb") as f:
    #         f.write(content)
    #     s3_key = local_path   # use local path as key in dev

    else:
        # Dev mode: save locally under /app/uploads (owned by appuser)
        import os
        upload_dir = f"/app/uploads/{doc_id}"
        os.makedirs(upload_dir, exist_ok=True)
        local_path = f"{upload_dir}/{file.filename}"
        content = await file.read()
        with open(local_path, "wb") as fh:
            fh.write(content)
        s3_key = local_path   # use local path as key in dev

    # ── Persist document record ───────────────────────────────────────────────
    doc = Document(
        id=doc_id,
        title=title,
        course_id=course_id,
        s3_key=s3_key,
        namespace=namespace,
        file_size_bytes=file.size,
        status=DocumentStatus.pending,
        uploaded_by=admin.id,
    )
    db.add(doc)
    await db.flush()

    # ── Queue ingestion task ──────────────────────────────────────────────────
    ingest_document_task.delay(doc_id, s3_key, namespace)

    return {
        "document_id": doc_id,
        "title": title,
        "namespace": namespace,
        "status": "pending",
        "message": "Ingestion queued. Poll /admin/documents/{document_id} for status.",
    }


@router.get("/documents")
async def list_documents(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "namespace": d.namespace,
            "status": d.status.value,
            "total_pages": d.total_pages,
            "total_chunks": d.total_chunks,
            "created_at": d.created_at.isoformat(),
            "error_message": d.error_message,
        }
        for d in docs
    ]


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": doc.id,
        "title": doc.title,
        "namespace": doc.namespace,
        "status": doc.status.value,
        "total_pages": doc.total_pages,
        "total_chunks": doc.total_chunks,
        "created_at": doc.created_at.isoformat(),
        "completed_at": doc.completed_at.isoformat() if doc.completed_at else None,
        "error_message": doc.error_message,
    }


# ── Analytics ─────────────────────────────────────────────────────────────────
@router.get("/analytics")
async def get_analytics(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_queries = await db.scalar(select(func.count(QueryLog.id)))
    total_users = await db.scalar(select(func.count(User.id)))
    total_docs = await db.scalar(select(func.count(Document.id)).where(
        Document.status == DocumentStatus.completed
    ))
    avg_latency = await db.scalar(select(func.avg(QueryLog.latency_ms)))
    positive_feedback = await db.scalar(select(func.count(QueryLog.id)).where(QueryLog.feedback == 1))
    negative_feedback = await db.scalar(select(func.count(QueryLog.id)).where(QueryLog.feedback == -1))

    return {
        "total_queries": total_queries or 0,
        "total_users": total_users or 0,
        "total_documents": total_docs or 0,
        "avg_latency_ms": round(avg_latency or 0, 1),
        "positive_feedback": positive_feedback or 0,
        "negative_feedback": negative_feedback or 0,
    }


@router.get("/users")
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role.value, "is_active": u.is_active}
        for u in users
    ]
