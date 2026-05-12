from ML_fasalX.core.model_registry import model_registry
from ML_fasalX.services.prediction_service import prediction_service
from ML_fasalX.utils.preprocessing import preprocess_image


def load_crop_model(crop_name: str):
    try:
        artifact = model_registry.load_crop_model(crop_name)
        return artifact.model, artifact.labels, None
    except Exception as exc:
        return None, None, str(exc)


def predict_disease(crop_name: str, image_bytes: bytes) -> dict:
    return prediction_service.predict_disease(crop_name, image_bytes)


def list_available_models() -> list:
    return [
        model["model_file"]
        for model in model_registry.list_available_models()
    ]
