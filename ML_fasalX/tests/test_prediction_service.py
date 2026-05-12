import pytest

np = pytest.importorskip("numpy")

from ML_fasalX.core.model_registry import ModelArtifact
from ML_fasalX.services import prediction_service as service_module
from ML_fasalX.services.prediction_service import PredictionService


class FakeModel:
    input_shape = (None, 224, 224, 3)
    layers = []

    def predict(self, image_array, verbose=0):
        return np.asarray([[0.05, 0.90, 0.05]], dtype=np.float32)


@pytest.fixture
def png_bytes():
    pillow = pytest.importorskip("PIL.Image")
    import io

    image = pillow.new("RGB", (16, 16), color=(20, 120, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_predict_disease_returns_contract(monkeypatch, tmp_path, png_bytes):
    artifact = ModelArtifact(
        crop_name="tomato",
        model_path=tmp_path / "tomato.keras",
        label_path=tmp_path / "tomato_classes.json",
        model=FakeModel(),
        labels=["healthy", "leaf_spot", "rust"],
        raw_input=True,
    )

    monkeypatch.setattr(
        service_module.model_registry,
        "load_crop_model",
        lambda crop_name: artifact,
    )

    result = PredictionService().predict_disease("tomato", png_bytes)

    assert result == {
        "success": True,
        "disease": "leaf_spot",
        "confidence": 90.0,
        "top3": [
            {"disease": "leaf_spot", "confidence": 90.0},
            {"disease": "rust", "confidence": 5.0},
            {"disease": "healthy", "confidence": 5.0},
        ],
        "error": None,
    }


def test_predict_disease_handles_invalid_image(monkeypatch, tmp_path):
    artifact = ModelArtifact(
        crop_name="tomato",
        model_path=tmp_path / "tomato.keras",
        label_path=tmp_path / "tomato_classes.json",
        model=FakeModel(),
        labels=["healthy", "leaf_spot", "rust"],
        raw_input=True,
    )

    monkeypatch.setattr(
        service_module.model_registry,
        "load_crop_model",
        lambda crop_name: artifact,
    )

    result = PredictionService().predict_disease("tomato", b"not-an-image")

    assert result["success"] is False
    assert result["disease"] is None
    assert "valid image" in result["error"]
