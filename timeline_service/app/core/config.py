"""
FasalX Timeline Service — Configuration Module
================================================
Uses pydantic-settings to load environment variables from a .env file.
Environment-specific classes (Development, Testing, Production) extend
the base Settings class, and the active config is selected via the
ENVIRONMENT variable.

Usage:
    from app.core.config import settings
    print(settings.REDIS_URL)
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


# ---------------------------------------------------------------------------
# Base Settings — shared across all environments
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """
    Base configuration for the Timeline Service.
    All settings can be overridden by environment variables or a .env file.
    See timeline_service/.env.example for the full list of variables.
    """

    # --- Service Identity ---
    PROJECT_NAME: str = "FasalX Timeline Service"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # --- MongoDB ---
    # Same Atlas cluster as the backend, but may point to a separate timeline DB.
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "fasalx"

    # --- Redis ---
    # Used by Arq for the background GDD job queue AND by the security module
    # to cache validated JWT tokens (5-minute TTL).
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Service Mesh ---
    # Internal URL of the fasalx-auth (backend) service.
    # In Docker Compose this is "http://fasalx-auth:8000".
    # In production (GKE/Cloud Run), resolved via the service name.
    AUTH_SERVICE_URL: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


# ---------------------------------------------------------------------------
# Environment-Specific Overrides
# ---------------------------------------------------------------------------

class DevelopmentSettings(Settings):
    """
    Local development. Connects to locally running MongoDB, Redis, and backend.
    Run the backend first so AUTH_SERVICE_URL resolves.
    """
    ENVIRONMENT: str = "development"
    MONGO_URL: str = "mongodb://localhost:27017"
    REDIS_URL: str = "redis://localhost:6379/0"
    AUTH_SERVICE_URL: str = "http://localhost:8000"


class TestingSettings(Settings):
    """
    CI / unit testing. Uses isolated test database and Redis index.
    The Auth service mesh is mocked in tests — AUTH_SERVICE_URL is unused.
    """
    ENVIRONMENT: str = "testing"
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "fasalx_test"
    REDIS_URL: str = "redis://localhost:6379/2"  # Separate index to avoid collision with backend tests
    AUTH_SERVICE_URL: str = "http://mock-auth:8000"


class ProductionSettings(Settings):
    """
    Production (GKE / Cloud Run).
    Expects all secrets injected via environment variables or a secrets manager.
    AUTH_SERVICE_URL must resolve within the service mesh (e.g., cluster DNS).
    """
    ENVIRONMENT: str = "production"
    MONGO_URL: str = "REPLACE_WITH_ATLAS_SRV_URI"
    REDIS_URL: str = "REPLACE_WITH_PROD_REDIS_URL"
    AUTH_SERVICE_URL: str = "http://fasalx-auth:8000"  # Resolved via K8s/Docker DNS


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
    Cached with lru_cache so pydantic only parses the .env file once per process.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    config_class = _env_map.get(env, DevelopmentSettings)
    return config_class()


settings = get_settings()
