from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.main import app

client = TestClient(app)


async def _fake_auth():
    return {
        "uid": "test-farmer-uid-001",
        "email": "farmer@fasalx.com",
        "name": "Test Farmer",
    }


@pytest.fixture(autouse=True)
def disease_test_setup():
    old_auth_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = _fake_auth
    yield
    if old_auth_override is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = old_auth_override


@patch(
    "app.api.routers.disease.predict_crop_disease",
    new_callable=AsyncMock,
    return_value={
        "success": True,
        "disease": "leaf_spot",
        "confidence": 91.2,
        "top3": [{"disease": "leaf_spot", "confidence": 91.2}],
        "error": None,
    },
)
@patch(
    "app.api.routers.disease.get_supported_disease_crops",
    new_callable=AsyncMock,
    return_value={"tomato"},
)
@patch("app.api.routers.disease.get_gemini_disease_advisory", new_callable=AsyncMock)
def test_supported_crop_with_image_uses_ml(mock_gemini, mock_models, mock_predict):
    response = client.post(
        "/api/v1/disease/predict",
        data={"crop_name": "tomato", "issue_text": "Yellow spots on leaves"},
        files={"image": ("leaf.jpg", b"fake-image", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["source"] == "ml"
    mock_predict.assert_awaited_once()
    mock_gemini.assert_not_called()


@patch(
    "app.api.routers.disease.get_gemini_disease_advisory",
    new_callable=AsyncMock,
    return_value={
        "success": True,
        "disease": None,
        "confidence": 0,
        "top3": [],
        "error": None,
        "source": "gemini",
        "model_supported": False,
        "crop_name": "dragon fruit",
        "advisory": {
            "issue_summary": "Spots reported on dragon fruit.",
            "possible_causes": ["fungal infection"],
            "risk_level": "medium",
            "recommended_actions": ["Remove badly affected tissue"],
            "prevention_tips": ["Improve airflow"],
            "when_to_seek_expert_help": "If spreading continues.",
            "confidence_note": "Advisory only.",
        },
    },
)
@patch(
    "app.api.routers.disease.get_supported_disease_crops",
    new_callable=AsyncMock,
    return_value={"tomato", "potato"},
)
@patch("app.api.routers.disease.predict_crop_disease", new_callable=AsyncMock)
def test_unsupported_crop_uses_gemini_fallback(mock_predict, mock_models, mock_gemini):
    response = client.post(
        "/api/v1/disease/predict",
        data={"crop_name": "dragon fruit", "issue_text": "Brown spots on stem"},
        files={"image": ("stem.jpg", b"fake-image", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "gemini"
    assert body["model_supported"] is False
    assert body["advisory"]["risk_level"] == "medium"
    mock_gemini.assert_awaited_once()
    mock_predict.assert_not_called()


@patch(
    "app.api.routers.disease.get_gemini_disease_advisory",
    new_callable=AsyncMock,
    return_value={
        "success": True,
        "disease": None,
        "confidence": 0,
        "top3": [],
        "error": None,
        "source": "gemini",
        "model_supported": False,
        "crop_name": "tomato",
        "advisory": {"issue_summary": "Text-only advisory.", "recommended_actions": []},
    },
)
@patch(
    "app.api.routers.disease.get_supported_disease_crops",
    new_callable=AsyncMock,
    return_value={"tomato"},
)
@patch("app.api.routers.disease.predict_crop_disease", new_callable=AsyncMock)
def test_text_only_issue_uses_gemini_even_for_supported_crop(mock_predict, mock_models, mock_gemini):
    response = client.post(
        "/api/v1/disease/predict",
        data={"crop_name": "tomato", "issue_text": "Leaves are curling upward."},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "gemini"
    mock_gemini.assert_awaited_once()
    mock_predict.assert_not_called()


@patch(
    "app.api.routers.disease.get_gemini_disease_advisory",
    new_callable=AsyncMock,
    return_value={
        "success": True,
        "disease": None,
        "confidence": 0,
        "top3": [],
        "error": None,
        "source": "gemini",
        "model_supported": False,
        "crop_name": "tomato",
        "advisory": {"issue_summary": "Text issue alias advisory.", "recommended_actions": []},
    },
)
@patch(
    "app.api.routers.disease.get_supported_disease_crops",
    new_callable=AsyncMock,
    return_value={"tomato"},
)
@patch("app.api.routers.disease.predict_crop_disease", new_callable=AsyncMock)
def test_text_issue_alias_is_accepted(mock_predict, mock_models, mock_gemini):
    response = client.post(
        "/api/v1/disease/predict",
        data={"crop_name": "tomato", "text_issue": "Leaves have black patches."},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "gemini"
    mock_gemini.assert_awaited_once()
    mock_predict.assert_not_called()


@patch(
    "app.api.routers.disease.get_gemini_disease_advisory",
    new_callable=AsyncMock,
    return_value={
        "success": True,
        "disease": None,
        "confidence": 0,
        "top3": [],
        "error": None,
        "source": "gemini",
        "model_supported": False,
        "crop_name": "dragon fruit",
        "advisory": {"issue_summary": "Legacy path advisory.", "recommended_actions": []},
    },
)
@patch(
    "app.api.routers.disease.get_supported_disease_crops",
    new_callable=AsyncMock,
    return_value={"tomato"},
)
@patch("app.api.routers.disease.predict_crop_disease", new_callable=AsyncMock)
def test_legacy_agronomy_disease_path_uses_new_fallback(mock_predict, mock_models, mock_gemini):
    response = client.post(
        "/api/v1/agronomy/disease/predict",
        data={"crop_name": "dragon fruit", "issue_text": "Stem rot near base."},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "gemini"
    mock_gemini.assert_awaited_once()
    mock_predict.assert_not_called()


def test_disease_predict_requires_image_or_issue_text():
    response = client.post("/api/v1/disease/predict", data={"crop_name": "tomato"})

    assert response.status_code == 400
    assert response.json()["error"] == "Provide either a crop image or a text description of the issue."
