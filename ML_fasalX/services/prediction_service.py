import logging
from typing import Any

from ML_fasalX.core.config import settings
from ML_fasalX.core.exceptions import MLServiceError, PredictionError
from ML_fasalX.core.model_registry import ModelArtifact, model_registry
from ML_fasalX.utils.preprocessing import preprocess_image

logger = logging.getLogger(__name__)


class PredictionService:
    def list_models(self) -> list[dict[str, Any]]:
        return model_registry.list_available_models()

    def warm_up_models(self) -> dict[str, Any]:
        if not settings.WARMUP_ON_STARTUP:
            return {"warmed": [], "failed": {}, "skipped": True}

        result = model_registry.warm_up(
            crop_names=settings.warmup_model_names,
            warm_all=settings.WARMUP_ALL_MODELS,
        )
        logger.info(
            "model_warmup_complete",
            extra={
                "warmed_count": len(result["warmed"]),
                "failed_count": len(result["failed"]),
            },
        )
        return result

    def predict_disease(self, crop_name: str, image_bytes: bytes) -> dict[str, Any]:
        crop_name = crop_name.strip()
        if not crop_name:
            return self._failure("Crop name is required.")

        try:
            artifact = model_registry.load_crop_model(crop_name)
            return self._predict_with_artifact(artifact, image_bytes)
        except MLServiceError as exc:
            logger.warning(
                "prediction_rejected",
                extra={"crop_name": crop_name, "code": exc.code, "error": exc.message},
            )
            return self._failure(exc.message)
        except Exception as exc:
            logger.exception("prediction_failed", extra={"crop_name": crop_name})
            return self._failure(f"Prediction failed: {exc}")

    def _predict_with_artifact(self, artifact: ModelArtifact, image_bytes: bytes) -> dict[str, Any]:
        image_size = self._model_image_size(artifact.model)
        image_array = preprocess_image(image_bytes, image_size, raw_input=artifact.raw_input)

        try:
            predictions = artifact.model.predict(image_array, verbose=0)[0]
        except Exception as exc:
            raise PredictionError(str(exc)) from exc

        if len(predictions) != len(artifact.labels):
            return self._failure(
                f"Model output size ({len(predictions)}) does not match labels ({len(artifact.labels)})."
            )

        import numpy as np

        top_index = int(np.argmax(predictions))
        top_confidence = float(predictions[top_index]) * 100
        top3_indices = np.argsort(predictions)[::-1][:3]
        top3 = [
            {
                "disease": artifact.labels[index],
                "confidence": round(float(predictions[index]) * 100, 1),
            }
            for index in top3_indices
        ]

        return {
            "success": True,
            "disease": artifact.labels[top_index],
            "confidence": round(top_confidence, 1),
            "top3": top3,
            "error": None,
        }

    @staticmethod
    def _model_image_size(model: Any) -> tuple[int, int]:
        try:
            input_shape = model.input_shape
            height = input_shape[1]
            width = input_shape[2]
            if height and width and height > 0 and width > 0:
                return int(height), int(width)
        except Exception:
            pass
        return settings.IMAGE_SIZE, settings.IMAGE_SIZE

    @staticmethod
    def _failure(message: str) -> dict[str, Any]:
        return {
            "success": False,
            "disease": None,
            "confidence": 0,
            "top3": [],
            "error": message,
        }


prediction_service = PredictionService()
