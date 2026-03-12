# EDU-RAG

Production-style RAG platform for education with:
- FastAPI backend
- React frontend
- PostgreSQL + Redis
- Celery workers
- Pinecone vector store
- Groq LLM + vision models

This project supports textbook ingestion, cited answers, role-based auth, course enrollment, and short/long-term memory.

## Features

- JWT auth with roles: `student`, `teacher`, `admin`
- Admin dashboard:
  - create courses
  - enroll users to courses
  - upload and ingest PDF textbooks
  - view analytics
- Retrieval pipeline:
  - HyDE query expansion
  - vector search in Pinecone
  - reranking
  - citation formatting
- Memory:
  - short-term session memory in Redis
  - long-term learning profile in PostgreSQL
- Streaming responses via SSE

## Architecture

```text
Frontend (React + Vite)
  -> Backend API (FastAPI)
      -> PostgreSQL (users, docs, logs, profile)
      -> Redis (session memory, Celery broker/results)
      -> Pinecone (document vectors by namespace)
      -> Groq (LLM + vision)
  -> Celery workers (ingestion + memory updates)
```

## Tech Stack

- Backend: Python, FastAPI, SQLAlchemy, Celery
- Frontend: React, TypeScript, Zustand, Tailwind
- Infra: Docker Compose, Postgres, Redis
- AI: Groq, SentenceTransformers, Pinecone

## Project Structure

```text
backend/
  app/
    api/           # query, admin, memory endpoints
    auth/          # JWT auth and role checks
    db/            # SQLAlchemy models
    ingestion/     # parse, chunk, embed, index
    llm/           # provider + prompt builder
    memory/        # short/long-term memory
    retrieval/     # hyde, reranker, retriever
    tasks/         # celery app + jobs
frontend/
  src/
    api/           # typed client
    components/    # UI screens
    store/         # Zustand stores
docker-compose.yml
```

## Quick Start (Docker)

### 1) Clone

```bash
git clone <your-repo-url>
cd edu-rag
```

### 2) Create env file

```bash
cp .env.example .env
```

Fill required keys in `.env`:
- `GROQ_API_KEY`
- `PINECONE_API_KEY`
- `SECRET_KEY`

### 3) Start services

```bash
docker compose up -d --build
```

### 4) Open apps

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Flower: http://localhost:5555

### 5) Create admin account

Use the UI register form and set role to admin (or call API directly).

## Role Behavior (Current)

- `admin`:
  - full access to `/admin/*`
  - create courses, enroll users, ingest docs, analytics
- `student`, `teacher`:
  - chat/query + memory access
  - currently similar behavior in backend (teacher-specific restrictions not implemented yet)

## Course Workflow

1. Admin creates course (example: `Biology Class 9`)
2. Admin uploads textbook and selects that course in upload form
3. Admin enrolls students to that course
4. Enrolled students query and retrieve from course-linked namespaces

## Key API Endpoints

### Auth
- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`

### Query
- `POST /query` (SSE stream)
- `GET /query/history`
- `DELETE /query/history`
- `POST /query/feedback`

### Memory
- `GET /memory/profile`
- `DELETE /memory/profile`

### Admin
- `POST /admin/courses`
- `GET /admin/courses`
- `POST /admin/courses/{course_id}/enroll/{user_id}`
- `POST /admin/ingest`
- `GET /admin/documents`
- `GET /admin/analytics`
- `GET /admin/users`

## Local Ops

### Restart backend + workers after `.env` model changes

```bash
docker compose up -d --force-recreate backend celery_ingestion celery_memory
```

### Check Postgres data

```bash
docker compose exec postgres psql -U postgres -d edurag
\dt
```

### Check Redis session memory

```bash
docker compose exec redis redis-cli
KEYS "session:*"
```

### Delete vectors for a namespace

```bash
docker compose exec backend python -c "from app.ingestion.indexer import delete_namespace; delete_namespace('your_namespace')"
```

## Troubleshooting

- `model_not_found` on Groq:
  - verify `LLM_MODEL` and `VISION_MODEL` are valid and single values
  - avoid inline concatenation mistakes like `modelA#modelB`
- Documents stuck in `pending`:
  - check `celery_ingestion` logs
- No Redis keys:
  - ask at least one chat question first; keys are session-based and TTL-limited
- Old chat visible across users:
  - fixed in frontend by clearing messages on logout and regenerating session on login

## Public GitHub Checklist

Before pushing public:

1. Rotate all exposed API keys (Groq/Pinecone/OpenAI/etc.)
2. Keep `.env` out of git
3. Commit `.env.example` only
4. Verify app starts from fresh clone using only README steps

Suggested push flow:

```bash
git init
git add .
git commit -m "Initial public release"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

## License

Choose a license before public release (MIT/Apache-2.0 are common for portfolio projects).
