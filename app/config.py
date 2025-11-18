from pathlib import Path
from pydantic_settings import BaseSettings


# Compute absolute path to project root and .env
BASE_DIR = Path(__file__).resolve().parent.parent  # .../solar-project-backend
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    # Google / Gemini
    GOOGLE_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBED_MODEL: str = "models/embedding-001"

    # App-level settings
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    CHROMA_DIR: str = "chroma_db"
    UPLOAD_DIR: str = "uploads"
    DATABASE_URL: str = "sqlite:///./app.db"

    class Config:
        env_file = str(ENV_PATH)
        env_file_encoding = "utf-8"
        extra = "ignore"   # ✅ ignore extra env vars


settings = Settings()
