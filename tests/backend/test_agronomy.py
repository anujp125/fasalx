"""
Backend – Agronomy endpoint tests
Tests: GET /weather, GET /mandi, POST /templates, GET /templates
Hardpoints bypassed:
  - Firebase auth.verify_id_token         → fake_auth dependency override
  - Open-Meteo HTTP call (weather)         → httpx.AsyncClient mock
  - data.gov.in HTTP call (mandi)          → httpx.AsyncClient mock
  - ip-api.com IP geolocation call        → httpx.AsyncClient mock
  - Redis caching                          → AsyncMock (cache-miss path)
  - MongoDB                                → mock_db_factory
"""
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.weather_service as weather_service_mod
import app.services.mandi_prices as mandi_prices_mod
import app.services.geolocation_service as geo_service_mod
import app.api.routers.agronomy as agronomy_router_mod

from app.main import app
from app.core.security import get_current_user
from app.db.mongodb import get_mongo_db
from app.db.redis import get_redis

from tests.fixtures.test_data import (
    MOCK_DECODED_TOKEN, FARMER_UID, FARMER_PROFILE_DOC,
    MOCK_OPEN_METEO_RESPONSE, MOCK_OPEN_METEO_RAINY,
    MOCK_MANDI_API_RESPONSE, MOCK_IP_GEO_RESPONSE,
    CROP_TEMPLATE_WHEAT, CROP_TEMPLATE_RICE,
)

async def _fake_auth():
    return MOCK_DECODED_TOKEN

app.dependency_overrides[get_current_user] = _fake_auth

client = TestClient(app)


from app.db.mongodb import db_instance
import app.db.redis as redis_mod

def _set_db(mock_db):
    db_instance.db = mock_db

def _set_redis(mock_redis):
    redis_mod.redis_client = mock_redis

def _clear_overrides():
    db_instance.db = None
    redis_mod.redis_client = None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a fake httpx response
# ─────────────────────────────────────────────────────────────────────────────
def _fake_httpx_response(data: dict, status_code: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/agronomy/weather
# ─────────────────────────────────────────────────────────────────────────────

class TestWeatherEndpoint:

    @patch.object(weather_service_mod.httpx, "AsyncClient")
    def test_weather_explicit_coords(self, mock_httpx, mock_db_factory, mock_redis):
        """Explicit lat/lon → Open-Meteo called → WeatherResponse returned."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get        = AsyncMock(return_value=_fake_httpx_response(MOCK_OPEN_METEO_RESPONSE))
        mock_httpx.return_value = mock_client

        db = mock_db_factory(users_doc=FARMER_PROFILE_DOC.copy())
        _set_db(db)
        _set_redis(mock_redis)

        resp = client.get("/api/v1/agronomy/weather?lat=28.6139&lon=77.2090")
        _clear_overrides()

        assert resp.status_code == 200
        body = resp.json()
        assert "temperature" in body
        assert body["temperature"] == 24.5
        assert "explicit" in body["description"].lower() or "location source" in body["description"].lower()

    @patch.object(weather_service_mod.httpx, "AsyncClient")
    def test_weather_rainy_description(self, mock_httpx, mock_db_factory, mock_redis):
        """Weather code != 0 → description is 'Cloudy/Rainy'."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get        = AsyncMock(return_value=_fake_httpx_response(MOCK_OPEN_METEO_RAINY))
        mock_httpx.return_value = mock_client

        db = mock_db_factory(users_doc=FARMER_PROFILE_DOC.copy())
        _set_db(db)
        _set_redis(mock_redis)

        resp = client.get("/api/v1/agronomy/weather?lat=28.6139&lon=77.2090")
        _clear_overrides()

        assert resp.status_code == 200
        assert "Cloudy/Rainy" in resp.json()["description"]

    @patch.object(weather_service_mod.httpx, "AsyncClient")
    def test_weather_redis_cache_hit(self, mock_httpx, mock_db_factory):
        """If Redis returns cached data, httpx.get should NOT be called."""
        cached_weather = {
            "temperature": 25.0, "humidity": 60.0,
            "precipitation": 0.0, "description": "Clear (cached)"
        }
        mock_redis = AsyncMock()
        mock_redis.get  = AsyncMock(return_value=json.dumps(cached_weather))
        mock_redis.setex = AsyncMock()

        db = mock_db_factory(users_doc=FARMER_PROFILE_DOC.copy())
        _set_db(db)
        _set_redis(mock_redis)

        resp = client.get("/api/v1/agronomy/weather?lat=28.6139&lon=77.2090")
        _clear_overrides()

        assert resp.status_code == 200
        mock_httpx.assert_not_called()
        assert resp.json()["temperature"] == 25.0


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/agronomy/mandi
# ─────────────────────────────────────────────────────────────────────────────

class TestMandiEndpoint:
    @pytest.fixture(autouse=True)
    def setup_api_key(self):
        mandi_prices_mod.settings.DATA_GOV_IN_API_KEY = "fake_test_key"
        yield
        mandi_prices_mod.settings.DATA_GOV_IN_API_KEY = None

    @patch.object(mandi_prices_mod.httpx, "AsyncClient")
    def test_mandi_explicit_state_market(self, mock_httpx, mock_db_factory, mock_redis):
        """Explicit state & market → data.gov.in called, commodities returned."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get        = AsyncMock(return_value=_fake_httpx_response(MOCK_MANDI_API_RESPONSE))
        mock_httpx.return_value = mock_client

        db = mock_db_factory(users_doc=FARMER_PROFILE_DOC.copy())
        _set_db(db)
        _set_redis(mock_redis)

        resp = client.get("/api/v1/agronomy/mandi?state=Delhi&market=Azadpur")
        _clear_overrides()

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["commodities"]) == 2
        assert body["commodities"][0]["commodity"] == "Wheat"

    @patch.object(mandi_prices_mod.httpx, "AsyncClient")
    def test_mandi_redis_cache_hit(self, mock_httpx, mock_db_factory):
        """Cache hit → no HTTP call, returns cached commodities."""
        cached = json.dumps({
            "state": "Delhi", "market": "Azadpur",
            "commodities": [{"commodity": "Wheat (cached)"}]
        })
        mock_redis = AsyncMock()
        mock_redis.get  = AsyncMock(return_value=cached)
        mock_redis.setex = AsyncMock()

        db = mock_db_factory(users_doc=FARMER_PROFILE_DOC.copy())
        _set_db(db)
        _set_redis(mock_redis)

        resp = client.get("/api/v1/agronomy/mandi?state=Delhi&market=Azadpur")
        _clear_overrides()

        assert resp.status_code == 200
        mock_httpx.assert_not_called()

    @patch.object(geo_service_mod.httpx, "AsyncClient")
    @patch.object(mandi_prices_mod.httpx, "AsyncClient")
    def test_mandi_ip_fallback(self, mock_mandi_httpx, mock_ip_httpx, mock_db_factory, mock_redis):
        """No explicit state/market + no profile → IP fallback resolves location."""
        # IP geolocation mock
        mock_ip_client = AsyncMock()
        mock_ip_client.__aenter__ = AsyncMock(return_value=mock_ip_client)
        mock_ip_client.__aexit__  = AsyncMock(return_value=False)
        mock_ip_client.get        = AsyncMock(return_value=_fake_httpx_response(MOCK_IP_GEO_RESPONSE))
        mock_ip_httpx.return_value = mock_ip_client

        # Mandi API mock
        mock_mandi_client = AsyncMock()
        mock_mandi_client.__aenter__ = AsyncMock(return_value=mock_mandi_client)
        mock_mandi_client.__aexit__  = AsyncMock(return_value=False)
        mock_mandi_client.get        = AsyncMock(return_value=_fake_httpx_response(MOCK_MANDI_API_RESPONSE))
        mock_mandi_httpx.return_value = mock_mandi_client

        # No user doc so profile fallback is skipped; IP fallback triggers
        db = mock_db_factory(users_doc=None)
        _set_db(db)
        _set_redis(mock_redis)

        resp = client.get("/api/v1/agronomy/mandi", headers={"x-forwarded-for": "1.2.3.4"})
        _clear_overrides()

        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/agronomy/templates
# ─────────────────────────────────────────────────────────────────────────────

class TestCropTemplates:

    def test_create_template(self, mock_db_factory):
        db = mock_db_factory()
        _set_db(db)
        resp = client.post("/api/v1/agronomy/templates", json=CROP_TEMPLATE_WHEAT)
        _clear_overrides()

        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert body["message"] == "Crop template created successfully"
        db.crop_templates.insert_one.assert_called_once()

    def test_create_template_missing_required_fields(self):
        """crop_name required → 422."""
        payload = {k: v for k, v in CROP_TEMPLATE_WHEAT.items() if k != "crop_name"}
        resp = client.post("/api/v1/agronomy/templates", json=payload)
        assert resp.status_code == 422

    def test_get_templates_empty(self, mock_db_factory):
        db = mock_db_factory(crop_templates=[])
        _set_db(db)
        resp = client.get("/api/v1/agronomy/templates")
        _clear_overrides()

        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_templates_with_data(self, mock_db_factory):
        """Async cursor yields template dicts → they appear in response."""
        doc = {**CROP_TEMPLATE_WHEAT, "_id": "tmpl-001"}
        # Motor async-for requires a proper async iterator
        async def _aiter(self=None):
            yield doc

        db = mock_db_factory()
        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = _aiter
        db.crop_templates.find.return_value = mock_cursor

        _set_db(db)
        resp = client.get("/api/v1/agronomy/templates")
        _clear_overrides()

        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
