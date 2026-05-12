"""
Backend – Telemetry endpoint tests
Tests: POST /api/v1/telemetry/data
Hardpoints bypassed: Firebase auth, MongoDB
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from app.core.security import get_current_user
from app.db.mongodb import get_mongo_db

from tests.fixtures.test_data import (
    MOCK_DECODED_TOKEN, FARMER_UID,
    IOT_PAYLOAD_VALID, IOT_PAYLOAD_NO_OPTIONALS,
    IOT_PAYLOAD_BOUNDARY_HIGH, IOT_PAYLOAD_INVALID_MOISTURE,
    IOT_PAYLOAD_INVALID_PH,
)

async def _fake_auth():
    return MOCK_DECODED_TOKEN

app.dependency_overrides[get_current_user] = _fake_auth

client = TestClient(app)

from app.db.mongodb import db_instance

def _db_override(mock_db):
    db_instance.db = mock_db

def _clear_db_override():
    db_instance.db = None


class TestTelemetryIngest:

    def test_valid_full_payload(self, mock_db_factory):
        """Complete IoT payload → 200, id returned, insert_one called."""
        db = mock_db_factory()
        _db_override(db)
        resp = client.post("/api/v1/telemetry/data", json=IOT_PAYLOAD_VALID)
        _clear_db_override()

        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert body["message"] == "Telemetry data ingested successfully"
        db.telemetry.insert_one.assert_called_once()

    def test_payload_without_optionals(self, mock_db_factory):
        """Payload with only required fields (no ph/NPK) → 200."""
        db = mock_db_factory()
        _db_override(db)
        resp = client.post("/api/v1/telemetry/data", json=IOT_PAYLOAD_NO_OPTIONALS)
        _clear_db_override()

        assert resp.status_code == 200

    def test_boundary_high_values(self, mock_db_factory):
        """Boundary-valid max values → 200."""
        db = mock_db_factory()
        _db_override(db)
        resp = client.post("/api/v1/telemetry/data", json=IOT_PAYLOAD_BOUNDARY_HIGH)
        _clear_db_override()

        assert resp.status_code == 200

    def test_invalid_moisture_rejected(self):
        """moisture > 100 → Pydantic 422."""
        resp = client.post("/api/v1/telemetry/data", json=IOT_PAYLOAD_INVALID_MOISTURE)
        assert resp.status_code == 422

    def test_invalid_ph_rejected(self):
        """ph < 0 → Pydantic 422."""
        resp = client.post("/api/v1/telemetry/data", json=IOT_PAYLOAD_INVALID_PH)
        assert resp.status_code == 422

    def test_user_id_attached(self, mock_db_factory):
        """Verify user_id from auth token is attached to the DB record."""
        db = mock_db_factory()
        _db_override(db)
        client.post("/api/v1/telemetry/data", json=IOT_PAYLOAD_VALID)
        _clear_db_override()

        call_args = db.telemetry.insert_one.call_args[0][0]
        assert call_args["user_id"] == FARMER_UID
        assert call_args["sync_status"] == "synced"

    def test_server_timestamp_injected(self, mock_db_factory):
        """Ensure server-side timestamp is added when payload omits it."""
        db = mock_db_factory()
        _db_override(db)
        client.post("/api/v1/telemetry/data", json=IOT_PAYLOAD_VALID)
        _clear_db_override()

        call_args = db.telemetry.insert_one.call_args[0][0]
        # timestamp comes from payload (it's None) so server fills it
        assert call_args["timestamp"] is not None

    def test_missing_device_id_rejected(self):
        """device_id is required → 422."""
        payload = {k: v for k, v in IOT_PAYLOAD_VALID.items() if k != "device_id"}
        resp = client.post("/api/v1/telemetry/data", json=payload)
        assert resp.status_code == 422

    def test_missing_moisture_rejected(self):
        """moisture is required → 422."""
        payload = {k: v for k, v in IOT_PAYLOAD_VALID.items() if k != "moisture"}
        resp = client.post("/api/v1/telemetry/data", json=payload)
        assert resp.status_code == 422
