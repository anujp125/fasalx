"""
Timeline Service – Timeline endpoint tests
Tests: POST /, GET /{user_id}, POST /sync-iot, PATCH /recalibrate
Hardpoints bypassed:
  - verify_token (JWT via Redis-cached inter-service call)  → dependency override
  - MongoDB                                                 → mock_db_factory
  - Arq Redis pool (enqueue_job)                            → patch
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

# timeline_service is inserted into sys.path by conftest.py
from app.main import app
from app.core.security import verify_token
from app.db.mongodb import get_mongo_db

from tests.fixtures.test_data import (
    MOCK_DECODED_TOKEN, FARMER_UID, CROP_ID,
    TIMELINE_DOC, TIMELINE_DOC_ADVANCED,
)

# ─── Auth override ────────────────────────────────────────────────────────────
async def _fake_verify_token():
    return MOCK_DECODED_TOKEN

app.dependency_overrides[verify_token] = _fake_verify_token

client = TestClient(app)


from app.db.mongodb import db_instance

def _set_db(mock_db):
    db_instance.db = mock_db

def _clear_overrides():
    db_instance.db = None


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/timeline/   – Create timeline
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateTimeline:

    def test_create_new_timeline(self, mock_db_factory):
        """Fresh timeline → inserted, 201 returned with model."""
        db = mock_db_factory(timelines=None)   # no existing timeline
        _set_db(db)
        resp = client.post("/api/v1/timeline/", json=TIMELINE_DOC)
        _clear_overrides()

        assert resp.status_code == 201
        db.user_crop_timelines.insert_one.assert_called_once()

    def test_create_duplicate_timeline_rejected(self, mock_db_factory):
        """Existing timeline for same user+crop → 409 Conflict."""
        db = mock_db_factory(timelines=TIMELINE_DOC.copy())
        _set_db(db)
        resp = client.post("/api/v1/timeline/", json=TIMELINE_DOC)
        _clear_overrides()

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()

    def test_create_forbidden_other_user(self, mock_db_factory):
        """user_id mismatch (auth uid vs payload uid) → 403."""
        wrong_timeline = {
            **TIMELINE_DOC,
            "user_metadata": {**TIMELINE_DOC["user_metadata"], "user_id": "other-user-xyz"},
        }
        db = mock_db_factory(timelines=None)
        _set_db(db)
        resp = client.post("/api/v1/timeline/", json=wrong_timeline)
        _clear_overrides()

        assert resp.status_code == 403

    def test_create_missing_milestones_rejected(self, mock_db_factory):
        """milestone_map is required → 422."""
        bad_doc = {k: v for k, v in TIMELINE_DOC.items() if k != "milestone_map"}
        db = mock_db_factory(timelines=None)
        _set_db(db)
        resp = client.post("/api/v1/timeline/", json=bad_doc)
        _clear_overrides()

        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/timeline/{user_id}  – Fetch timeline
# ─────────────────────────────────────────────────────────────────────────────

class TestGetTimeline:

    def test_get_existing_timeline(self, mock_db_factory):
        """Timeline exists → 200, model returned."""
        db = mock_db_factory(timelines=TIMELINE_DOC.copy())
        _set_db(db)
        resp = client.get(f"/api/v1/timeline/{FARMER_UID}")
        _clear_overrides()

        assert resp.status_code == 200
        body = resp.json()
        assert body["user_metadata"]["user_id"] == FARMER_UID
        assert body["user_metadata"]["crop_id"] == CROP_ID

    def test_get_not_found(self, mock_db_factory):
        """No timeline in DB → 404."""
        db = mock_db_factory(timelines=None)
        _set_db(db)
        resp = client.get(f"/api/v1/timeline/{FARMER_UID}")
        _clear_overrides()

        assert resp.status_code == 404

    def test_get_forbidden_other_user(self, mock_db_factory):
        """Trying to get another user's timeline → 403."""
        db = mock_db_factory(timelines=TIMELINE_DOC.copy())
        _set_db(db)
        resp = client.get("/api/v1/timeline/some-other-user-id")
        _clear_overrides()

        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/timeline/sync-iot   – IoT webhook
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncIot:

    @patch("app.api.routers.timeline.create_pool")
    def test_sync_iot_enqueues_job(self, mock_create_pool, mock_db_factory):
        """IoT data received → DB updated, background job enqueued via Arq."""
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock()
        mock_create_pool.return_value = mock_pool

        db = mock_db_factory()
        _set_db(db)
        resp = client.post(
            "/api/v1/timeline/sync-iot",
            params={"user_id": FARMER_UID, "t_max": 32.0, "t_min": 18.0, "soil_moisture": 45.0}
        )
        _clear_overrides()

        assert resp.status_code == 200
        db.user_crop_timelines.update_one.assert_called_once()
        mock_pool.enqueue_job.assert_called_once_with("recalculate_timeline_gdd", FARMER_UID)

    @patch("app.api.routers.timeline.create_pool")
    def test_sync_iot_boundary_temperatures(self, mock_create_pool, mock_db_factory):
        """Extreme but valid temperatures → 200."""
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock()
        mock_create_pool.return_value = mock_pool

        db = mock_db_factory()
        _set_db(db)
        resp = client.post(
            "/api/v1/timeline/sync-iot",
            params={"user_id": FARMER_UID, "t_max": 59.9, "t_min": -49.9, "soil_moisture": 0.0}
        )
        _clear_overrides()

        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /api/v1/timeline/recalibrate  – Manual override
# ─────────────────────────────────────────────────────────────────────────────

class TestRecalibrate:

    def test_recalibrate_success(self, mock_db_factory):
        """Valid milestone name → update_one called, 200 returned."""
        db = mock_db_factory()
        db.user_crop_timelines.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1)
        )
        _set_db(db)
        resp = client.patch(
            "/api/v1/timeline/recalibrate",
            params={"user_id": FARMER_UID, "milestone_name": "Germination"}
        )
        _clear_overrides()

        assert resp.status_code == 200
        assert "manually marked as completed" in resp.json()["message"]

    def test_recalibrate_not_found(self, mock_db_factory):
        """Milestone not found / already complete → 400."""
        db = mock_db_factory()
        db.user_crop_timelines.update_one = AsyncMock(
            return_value=MagicMock(modified_count=0)
        )
        _set_db(db)
        resp = client.patch(
            "/api/v1/timeline/recalibrate",
            params={"user_id": FARMER_UID, "milestone_name": "NonExistentMilestone"}
        )
        _clear_overrides()

        assert resp.status_code == 400

    def test_recalibrate_forbidden(self, mock_db_factory):
        """auth uid ≠ user_id param → 403."""
        db = mock_db_factory()
        _set_db(db)
        resp = client.patch(
            "/api/v1/timeline/recalibrate",
            params={"user_id": "attacker-uid", "milestone_name": "Germination"}
        )
        _clear_overrides()

        assert resp.status_code == 403
