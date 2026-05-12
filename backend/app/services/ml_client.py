import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _failure(message: str) -> dict[str, Any]:
    return {
        "success": False,
        "disease": None,
        "confidence": 0,
        "top3": [],
        "error": message,
    }


async def predict_crop_disease(
    crop_name: str,
    image_bytes: bytes,
    filename: str = "image.jpg",
    content_type: str = "image/jpeg",
) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.ML_SERVICE_TIMEOUT_SECONDS)
    url = f"{settings.ML_SERVICE_URL.rstrip('/')}/predict"
    max_attempts = max(1, settings.ML_SERVICE_MAX_RETRIES + 1)

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    data={"crop_name": crop_name},
                    files={
                        "image": (
                            filename,
                            image_bytes,
                            content_type,
                        )
                    },
                )

            if response.status_code >= 500 and attempt < max_attempts:
                await asyncio.sleep(0.2 * attempt)
                continue

            try:
                payload = response.json()
            except ValueError:
                logger.warning(
                    "ml_service_invalid_json",
                    extra={"status_code": response.status_code, "url": url},
                )
                return _failure("ML service returned an invalid response.")

            if response.is_error:
                return _failure(payload.get("error") or "ML service rejected the prediction request.")

            return payload

        except (httpx.TimeoutException, httpx.TransportError) as exc:
            logger.warning(
                "ml_service_request_failed",
                extra={"attempt": attempt, "max_attempts": max_attempts, "error": str(exc)},
            )
            if attempt == max_attempts:
                return _failure("ML service is temporarily unavailable.")
            await asyncio.sleep(0.2 * attempt)

    return _failure("ML service is temporarily unavailable.")


async def get_supported_disease_crops() -> set[str] | None:
    timeout = httpx.Timeout(settings.ML_SERVICE_TIMEOUT_SECONDS)
    url = f"{settings.ML_SERVICE_URL.rstrip('/')}/models"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("ml_service_models_request_failed", extra={"url": url, "error": str(exc)})
        return None

    models = payload.get("models", [])
    crops = {
        _normalize_crop_name(model.get("crop_name", ""))
        for model in models
        if isinstance(model, dict) and model.get("crop_name")
    }
    return crops


def is_crop_supported_by_models(crop_name: str, supported_crops: set[str] | None) -> bool | None:
    if supported_crops is None:
        return None

    normalized = _normalize_crop_name(crop_name)
    compact = _compact_crop_name(crop_name)
    return normalized in supported_crops or compact in {_compact_crop_name(crop) for crop in supported_crops}


def _normalize_crop_name(crop_name: str) -> str:
    return crop_name.strip().lower()


def _compact_crop_name(crop_name: str) -> str:
    return _normalize_crop_name(crop_name).replace("_", "").replace("-", "").replace(" ", "")
