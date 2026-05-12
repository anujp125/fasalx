from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_models_dir() -> Path:
    package_root = Path(__file__).resolve().parents[1]
    nested_dir = package_root / "models" / "models"
    flat_dir = package_root / "models"
    return nested_dir if nested_dir.exists() else flat_dir


class Settings(BaseSettings):
    SERVICE_NAME: str = "FasalX ML Service"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    MODELS_DIR: Path = Field(default_factory=_default_models_dir)
    IMAGE_SIZE: int = 224
    MAX_UPLOAD_BYTES: int = 8 * 1024 * 1024
    ALLOWED_CONTENT_TYPES: str = "image/jpeg,image/png,image/webp"

    WARMUP_ON_STARTUP: bool = True
    WARMUP_ALL_MODELS: bool = False
    WARMUP_MODELS: str = ""

    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ML_",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def allowed_content_types(self) -> set[str]:
        return {
            content_type.strip().lower()
            for content_type in self.ALLOWED_CONTENT_TYPES.split(",")
            if content_type.strip()
        }

    @property
    def warmup_model_names(self) -> list[str]:
        return [
            model_name.strip()
            for model_name in self.WARMUP_MODELS.split(",")
            if model_name.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

