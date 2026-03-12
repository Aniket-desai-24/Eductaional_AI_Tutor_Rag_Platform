from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "EDU-RAG"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    ALGORITHM: str = "HS256"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/edurag"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Vector Store (Pinecone) ───────────────────────────────────────────────
    PINECONE_API_KEY: str = ""
    PINECONE_ENVIRONMENT: str = "us-east-1-aws"
    PINECONE_INDEX_NAME: str = "edu-rag"

    # ── OpenAI ────────────────────────────────────────────────────────────────
    # [DEPRECATED] Using Groq instead
    # OPENAI_API_KEY: str = ""
    # EMBEDDING_MODEL: str = "text-embedding-3-large"
    # EMBEDDING_DIMENSIONS: int = 3072
    # LLM_MODEL: str = "gpt-4o"
    # VISION_MODEL: str = "gpt-4o"

    # ── Groq (Llama) ───────────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    LLM_MODEL: str = "meta-llama/llama-4-maverick-17b-128e-instruct"      # Groq Maverick
    VISION_MODEL: str = "meta-llama/llama-4-maverick-17b-128e-instruct"  # Groq Maverick (vision-capable)

    # ── Embeddings (Sentence Transformers) ─────────────────────────────────────
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"       # Sentence Transformers MiniLM
    EMBEDDING_DIMENSIONS: int = 384                 # MiniLM output dimensions

    # ── Anthropic (fallback LLM) ──────────────────────────────────────────────
    # [DEPRECATED] Using Groq instead
    # ANTHROPIC_API_KEY: Optional[str] = None
    # ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"

    # ── AWS S3 ────────────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET: str = "edu-rag-documents"
    AWS_REGION: str = "us-east-1"

    # ── Memory ────────────────────────────────────────────────────────────────
    SHORT_TERM_TTL_SECONDS: int = 1800          # 30 minutes
    MAX_CONVERSATION_TURNS: int = 10
    MEMORY_SUMMARY_EVERY_N_TURNS: int = 5

    # ── Retrieval ─────────────────────────────────────────────────────────────
    TOP_K_RETRIEVAL: int = 20
    TOP_K_RERANK: int = 5
    CHUNK_SIZE: int = 256
    PARENT_CHUNK_SIZE: int = 1024
    CHUNK_OVERLAP: int = 32

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 30
    MAX_CONCURRENT_LLM_CALLS_PER_USER: int = 3

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    model_config = {"env_file": ".env", "case_sensitive": True}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()