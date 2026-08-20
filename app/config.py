"""
app/config.py
=============
Central configuration for the Aegis Semantic DLP system.

All environment variables are loaded from `.env` (see `.env.example`).
All filesystem paths are derived relative to the project root so the
application works regardless of the current working directory.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ── Project root (two levels up from this file: app/config.py -> app/ -> /) ──
BASE_DIR: Path = Path(__file__).resolve().parent.parent

# Load .env from project root
load_dotenv(BASE_DIR / ".env")

# ── API Keys ─────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "dlp")

# ── Embedding Model ───────────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME: str = os.getenv(
    "EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"
)

# ── Detection Thresholds ──────────────────────────────────────────────────────
# Score >= HIGH_THRESHOLD  -> instant BLOCK (Stage 2)
# Score >= CHECK_FLOOR     -> invoke LLM auditor (Stage 3)
# Score <  CHECK_FLOOR     -> ALLOW (no meaningful vault overlap)
SIMILARITY_HIGH_THRESHOLD: float = float(
    os.getenv("SIMILARITY_HIGH_THRESHOLD", "0.86")
)
SIMILARITY_CHECK_FLOOR: float = float(
    os.getenv("SIMILARITY_CHECK_FLOOR", "0.35")
)

# ── Filesystem Paths (absolute, derived from BASE_DIR) ───────────────────────
VAULT_DIR: Path = BASE_DIR / "vault"
AUDIT_DB_PATH: Path = BASE_DIR / "audit_logs.db"
FRONTEND_DIR: Path = BASE_DIR / "frontend"

# ── API / CORS ────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins.
# e.g. "http://localhost:3000,https://app.example.com"
# Use "*" to allow all origins (development only).
_raw_origins = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS: list[str] = (
    ["*"] if _raw_origins.strip() == "*"
    else [o.strip() for o in _raw_origins.split(",") if o.strip()]
)

# ── Dual Cloud LLM Configuration ─────────────────────────────────────────────
# LLM 1: The Target Enterprise Assistant (Neutral, Unbiased)
AGENT_LLM_MODEL: str = os.getenv("AGENT_LLM_MODEL", "qwen/qwen3.6-27b")

# LLM 2: The Independent DLP Auditor (Specialized security judge for factual overlap)
AUDITOR_LLM_MODEL: str = os.getenv("AUDITOR_LLM_MODEL", "qwen/qwen3.6-27b")


# ── Validation (fail fast on startup if critical keys are missing) ────────────
def validate() -> None:
    """Raise EnvironmentError if required configuration is missing."""
    missing = []
    if not GROQ_API_KEY:
        missing.append("GROQ_API_KEY")
    if not PINECONE_API_KEY:
        missing.append("PINECONE_API_KEY")
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill in your credentials."
        )
