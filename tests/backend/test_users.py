"""
Backend – User endpoint tests
Tests: /sync, /me (GET & POST), /logout, /deactivate, /me (DELETE), /activities
Hardpoints bypassed: Firebase auth.verify_id_token, MongoDB, firebase_admin.auth calls
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

import app.api.routers.users as users_router_mod
import app.services.user_service as user_service_mod

from app.main import app
from app.core.security import get_current_user

from tests.fixtures.test_data import (
    FARMER_UID, MOCK_DECODED_TOKEN, FARMER_PROFILE_DOC,
    FARMER_PROFILE_UPDATE_PAYLOAD, MOCK_ACTIVITIES,
)

# ─── Auth override ────────────────────────────────────────────────────────────
async def _fake_auth():
    return MOCK_DECODED_TOKEN

app.dependency_overrides[get_current_user] = _fake_auth

client = TestClient(app)


# ─── Helpers ─────────────────────────────────────────────────────────────────
from app.db.mongodb import db_instance

def _db_override(mock_db):
    db_instance.db = mock_db
    return mock_db

def _clear_db_override():
    db_instance.db = None


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/users/sync
# ─────────────────────────────────────────────────────────────────────────────

class TestUserSync:
    def test_sync_creates_new_user(self, mock_db_factory):
        """New user → insert_one called, 200 returned."""
        db = mock_db_factory(users_doc=None)          # no existing doc
        _db_override(db)
        resp = client.post("/api/v1/users/sync")
        _clear_db_override()

        assert resp.status_code == 200
        assert resp.json()["message"] == "User synchronized successfully"
        db.users.insert_one.assert_called_once()

    def test_sync_existing_user_skips_insert(self, mock_db_factory):
        """Existing user → insert_one NOT called."""
        db = mock_db_factory(users_doc=FARMER_PROFILE_DOC.copy())
        _db_override(db)
        resp = client.post("/api/v1/users/sync")
        _clear_db_override()

        assert resp.status_code == 200
        db.users.insert_one.assert_not_called()

    def test_sync_logs_login_activity(self, mock_db_factory):
        """Activity log (insert_one on user_activities) is always called."""
        db = mock_db_factory(users_doc=None)
        _db_override(db)
        client.post("/api/v1/users/sync")
        _clear_db_override()

        db.user_activities.insert_one.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/users/me
# ─────────────────────────────────────────────────────────────────────────────

class TestGetProfile:
    def test_get_existing_profile(self, mock_db_factory):
        db = mock_db_factory(users_doc=FARMER_PROFILE_DOC.copy())
        _db_override(db)
        resp = client.get("/api/v1/users/me")
        _clear_db_override()

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == FARMER_UID
        assert body["display_name"] == "Ramesh Kumar"

    def test_get_non_existing_profile(self, mock_db_factory):
        """User not found in DB → fallback skeleton response."""
        db = mock_db_factory(users_doc=None)
        _db_override(db)
        resp = client.get("/api/v1/users/me")
        _clear_db_override()

        assert resp.status_code == 200
        assert "Profile not completed" in resp.json()["message"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/users/me  (profile update)
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateProfile:
    def test_update_profile_success(self, mock_db_factory):
        db = mock_db_factory(users_doc=FARMER_PROFILE_DOC.copy())
        _db_override(db)
        resp = client.post("/api/v1/users/me", json=FARMER_PROFILE_UPDATE_PAYLOAD)
        _clear_db_override()

        assert resp.status_code == 200
        assert "updated_at" in resp.json()
        db.users.update_one.assert_called_once()
        db.user_activities.insert_one.assert_called_once()

    def test_update_profile_missing_required_field(self):
        """display_name is required by FarmerProfile → 422."""
        resp = client.post("/api/v1/users/me", json={"farm_size_acres": 10})
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/users/logout
# ─────────────────────────────────────────────────────────────────────────────

class TestLogout:
    @patch.object(users_router_mod.auth, "revoke_refresh_tokens")
    def test_logout_success(self, mock_revoke, mock_db_factory):
        db = mock_db_factory()
        _db_override(db)
        resp = client.post("/api/v1/users/logout")
        _clear_db_override()

        assert resp.status_code == 200
        mock_revoke.assert_called_once_with(FARMER_UID)

    @patch.object(users_router_mod.auth, "revoke_refresh_tokens", side_effect=Exception("Firebase offline"))
    def test_logout_firebase_failure(self, mock_revoke, mock_db_factory):
        db = mock_db_factory()
        _db_override(db)
        resp = client.post("/api/v1/users/logout")
        _clear_db_override()

        assert resp.status_code == 500
        assert "Failed to logout" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/users/deactivate
# ─────────────────────────────────────────────────────────────────────────────

class TestDeactivateAccount:
    @patch.object(user_service_mod.auth, "revoke_refresh_tokens")
    def test_deactivate_success(self, mock_revoke, mock_db_factory):
        db = mock_db_factory()
        _db_override(db)
        resp = client.post("/api/v1/users/deactivate")
        _clear_db_override()

        assert resp.status_code == 200
        db.users.update_one.assert_called_once()
        mock_revoke.assert_called_once_with(FARMER_UID)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/v1/users/me
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteAccount:
    @patch.object(user_service_mod.auth, "delete_user")
    def test_delete_success(self, mock_delete, mock_db_factory):
        db = mock_db_factory()
        _db_override(db)
        resp = client.delete("/api/v1/users/me")
        _clear_db_override()

        assert resp.status_code == 200
        mock_delete.assert_called_once_with(FARMER_UID)
        db.users.delete_one.assert_called_once()
        db.user_activities.delete_many.assert_called_once()

    @patch.object(user_service_mod.auth, "delete_user", side_effect=Exception("Firebase error"))
    def test_delete_firebase_failure(self, mock_delete, mock_db_factory):
        db = mock_db_factory()
        _db_override(db)
        resp = client.delete("/api/v1/users/me")
        _clear_db_override()

        assert resp.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/users/activities
# ─────────────────────────────────────────────────────────────────────────────

class TestGetActivities:
    def test_returns_activity_list(self, mock_db_factory):
        db = mock_db_factory(activities=MOCK_ACTIVITIES)
        _db_override(db)
        resp = client.get("/api/v1/users/activities")
        _clear_db_override()

        assert resp.status_code == 200
        acts = resp.json()["activities"]
        assert len(acts) == 3
        assert acts[0]["action"] == "LOGIN"
        # ObjectId should be converted to string 'id' key
        assert "id" in acts[0]
        assert "_id" not in acts[0]

    def test_empty_activities(self, mock_db_factory):
        db = mock_db_factory(activities=[])
        _db_override(db)
        resp = client.get("/api/v1/users/activities")
        _clear_db_override()

        assert resp.status_code == 200
        assert resp.json()["activities"] == []
