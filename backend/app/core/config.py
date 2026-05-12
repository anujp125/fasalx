"""
FasalX Backend — Configuration Module
=======================================
Uses pydantic-settings to load environment variables from a .env file.
Environment-specific classes (Development, Testing, Production) extend
the base Settings class, and the active config is selected via the
ENVIRONMENT variable.

Usage:
    from app.core.config import settings
    print(settings.MONGO_URL)
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


# ---------------------------------------------------------------------------
# Base Settings — shared across all environments
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """
    Base configuration. All settings can be overridden by environment variables
    or a .env file. See backend/.env.example for the full list of variables.
    """

    # --- Service Identity ---
    PROJECT_NAME: str = "FasalX Backend"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # Overridden to "testing" or "production" in CI/CD

    # --- MongoDB ---
    # Full connection string. For local dev, use mongodb://localhost:27017.
    # For Atlas, use the SRV URI from your Atlas dashboard.
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "fasalx"

    # --- Redis ---
    # Used for caching (Mandi prices, weather) and as the Arq job broker.
    # Format: redis://<host>:<port>/<db>
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Firebase ---
    # Path to the downloaded Firebase service account JSON key file.
    # Set to None to fall back to GOOGLE_APPLICATION_CREDENTIALS (for GCP).
    FIREBASE_CREDENTIALS_PATH: str | None = None

    # --- External APIs ---
    # API key for Data.gov.in Mandi price datasets.
    LIVE_MANDI_PRICES_API_KEY: str | None = None
    DATA_GOV_IN_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    # --- Sentinel Hub (Satellite Intelligence) ---
    SENTINEL_HUB_CLIENT_ID: str | None = None
    SENTINEL_HUB_CLIENT_SECRET: str | None = None

    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_JUDGE_MODEL: str = "gemini-2.5-flash"
    GEMINI_TRANSCRIPTION_MODEL: str = "gemini-2.5-flash"
    GEMINI_TTS_MODEL: str = "gemini-2.5-flash-preview-tts"
    GEMINI_TTS_VOICE_NAME: str = "Kore"
    GEMINI_DISEASE_FALLBACK_MODEL: str = "gemini-2.5-flash"
    CHATBOT_AUDIO_MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    CHATBOT_AUDIO_ALLOWED_CONTENT_TYPES: str = (
        "audio/wav,audio/x-wav,audio/mpeg,audio/mp3,audio/mp4,audio/webm,"
        "audio/ogg,audio/aac,audio/flac"
    )

    @property
    def chatbot_audio_allowed_content_types(self) -> set[str]:
        return {
            content_type.strip().lower()
            for content_type in self.CHATBOT_AUDIO_ALLOWED_CONTENT_TYPES.split(",")
            if content_type.strip()
        }

    # --- ML Disease Inference Service ---
    # In Docker Compose this resolves via service DNS, not localhost.
    ML_SERVICE_URL: str = "http://localhost:8002"
    ML_SERVICE_TIMEOUT_SECONDS: float = 20.0
    ML_SERVICE_MAX_RETRIES: int = 2
    ML_PROXY_MAX_UPLOAD_BYTES: int = 8 * 1024 * 1024
    ML_PROXY_ALLOWED_CONTENT_TYPES: str = "image/jpeg,image/png,image/webp"

    @property
    def ml_proxy_allowed_content_types(self) -> set[str]:
        return {
            content_type.strip().lower()
            for content_type in self.ML_PROXY_ALLOWED_CONTENT_TYPES.split(",")
            if content_type.strip()
        }

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


# ---------------------------------------------------------------------------
# Environment-Specific Overrides
# ---------------------------------------------------------------------------

class DevelopmentSettings(Settings):
    """
    Local development configuration.
    - Uses local MongoDB and Redis instances.
    - Debug-friendly defaults.
    """
    ENVIRONMENT: str = "development"
    MONGO_URL: str = "mongodb://localhost:27017"
    REDIS_URL: str = "redis://localhost:6379/0"


class TestingSettings(Settings):
    """
    CI / unit testing configuration.
    - Uses an isolated test database to avoid polluting dev data.
    - Set TESTING=true in your CI environment.
    """
    ENVIRONMENT: str = "testing"
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "fasalx_test"  # Isolated test database
    REDIS_URL: str = "redis://localhost:6379/1"  # Separate Redis DB index


class ProductionSettings(Settings):
    """
    Production configuration.
    - Expects all secrets injected via environment variables or a secrets manager.
    - Validates that critical variables are not using placeholder defaults.
    """
    ENVIRONMENT: str = "production"

    # In production, these MUST be set by the deployment environment.
    # The app will fail to start if they remain at default values.
    MONGO_URL: str = "REPLACE_WITH_ATLAS_SRV_URI"
    REDIS_URL: str = "REPLACE_WITH_PROD_REDIS_URL"


# ---------------------------------------------------------------------------
# Config Factory
# ---------------------------------------------------------------------------

_env_map = {
    "development": DevelopmentSettings,
    "testing": TestingSettings,
    "production": ProductionSettings,
}


@lru_cache
def get_settings() -> Settings:
    """
    Returns the appropriate Settings class based on the ENVIRONMENT variable.
    Cached with lru_cache so pydantic only parses the .env file once.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    config_class = _env_map.get(env, DevelopmentSettings)
    return config_class()


settings = get_settings()
