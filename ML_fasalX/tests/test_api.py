import pytest
from fastapi.testclient import TestClient

pytest.importorskip("multipart")

from ML_fasalX.main import app


def test_predict_endpoint_uses_prediction_contract(monkeypatch):
    monkeypatch.setattr(
        "ML_fasalX.main.prediction_service.warm_up_models",
        lambda: {"warmed": [], "failed": {}},
    )
    monkeypatch.setattr(
        "ML_fasalX.main.prediction_service.predict_disease",
        lambda crop_name, image_bytes: {
            "success": True,
            "disease": "leaf_spot",
            "confidence": 92.3,
            "top3": [{"disease": "leaf_spot", "confidence": 92.3}],
            "error": None,
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/predict",
            data={"crop_name": "tomato"},
            files={"image": ("leaf.png", b"fake-image-bytes", "image/png")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "disease": "leaf_spot",
        "confidence": 92.3,
        "top3": [{"disease": "leaf_spot", "confidence": 92.3}],
        "error": None,
    }


def test_predict_endpoint_rejects_unsupported_content_type(monkeypatch):
    monkeypatch.setattr(
        "ML_fasalX.main.prediction_service.warm_up_models",
        lambda: {"warmed": [], "failed": {}},
    )

    with TestClient(app) as client:
        response = client.post(
            "/predict",
            data={"crop_name": "tomato"},
            files={"image": ("leaf.txt", b"not-image", "text/plain")},
        )

    assert response.status_code == 415
    assert response.json()["success"] is False
    assert "Unsupported image content type" in response.json()["error"]
