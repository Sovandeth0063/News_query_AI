import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    BASE_DIR: Path = BASE_DIR
    
    # Gemini API & Models (Strictly Gemini 3+)
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY", "").strip() or None
    MODEL_CLASSIFIER: str = os.getenv("MODEL_CLASSIFIER", "gemini-3.5-flash-lite")
    MODEL_DIGEST: str = os.getenv("MODEL_DIGEST", "gemini-3.5-flash")
    MODEL_CHAT_PRIMARY: str = os.getenv("MODEL_CHAT_PRIMARY", "gemini-3.5-flash-lite")
    MODEL_CHAT_ESCALATE: str = os.getenv("MODEL_CHAT_ESCALATE", "gemini-3.5-flash")

    # Storage paths
    DB_PATH: Path = BASE_DIR / os.getenv("DB_PATH", "./data/news.db")
    CHROMA_PATH: Path = BASE_DIR / os.getenv("CHROMA_PATH", "./data/chroma")
    SOURCES_FILE: Path = BASE_DIR / "sources.yaml"
    
    # Ingestion & Ranking Parameters
    INGEST_INTERVAL_HOURS: int = int(os.getenv("INGEST_INTERVAL_HOURS", "24"))
    DISPLAY_TZ: str = os.getenv("DISPLAY_TZ", "UTC")
    DEDUP_SIM_THRESHOLD: float = float(os.getenv("DEDUP_SIM_THRESHOLD", "0.85"))
    RANK_HALF_LIFE_HOURS: float = float(os.getenv("RANK_HALF_LIFE_HOURS", "36.0"))
    RETENTION_DAYS: int = int(os.getenv("RETENTION_DAYS", "90"))
    
    # Embeddings (Runs locally)
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # Fallback LLM (Local / Ollama)
    FALLBACK_BASE_URL: str = os.getenv("FALLBACK_BASE_URL", "http://localhost:11434/v1")
    FALLBACK_API_KEY: str = os.getenv("FALLBACK_API_KEY", "ollama")
    FALLBACK_MODEL: str = os.getenv("FALLBACK_MODEL", "qwen3:8b")
    FALLBACK_TIMEOUT_SECONDS: int = int(os.getenv("FALLBACK_TIMEOUT_SECONDS", "120"))

    # Model Radar & Entity Extraction Parameters
    RADAR_BASELINE_DAYS: int = int(os.getenv("RADAR_BASELINE_DAYS", "3"))
    EMERGING_WINDOW_HOURS: int = int(os.getenv("EMERGING_WINDOW_HOURS", "48"))
    EMERGING_MIN_SOURCES: int = int(os.getenv("EMERGING_MIN_SOURCES", "2"))
    EMERGING_TTL_HOURS: int = int(os.getenv("EMERGING_TTL_HOURS", "168"))
    EXTRACTION_BATCH_SIZE: int = int(os.getenv("EXTRACTION_BATCH_SIZE", "8"))
    EXTRACTION_MAX_CALLS_PER_RUN: int = int(os.getenv("EXTRACTION_MAX_CALLS_PER_RUN", "20"))
    ENTITY_MIN_CONFIDENCE: float = float(os.getenv("ENTITY_MIN_CONFIDENCE", "0.5"))
    EXTRACTION_PREFILTER_ENABLED: bool = os.getenv("EXTRACTION_PREFILTER_ENABLED", "true").lower() in ("true", "1", "yes")
    EXTRACTION_PREFILTER_REGEX: str = os.getenv("EXTRACTION_PREFILTER_REGEX", r"launch|releas|introduc|unveil|announc|open-source|open-weight|benchmark|stealth|raises|funding|model|version|update")

    def ensure_directories(self):
        """Ensure data directories exist."""
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.CHROMA_PATH.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_directories()
