import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.core.exceptions import AuthorizationError
from app.core.security import get_current_user, require_admin_permission
from app.db.mongodb import db_instance
from app.main import app

from tests.fixtures.test_data import ADMIN_UID, FARMER_UID

client = TestClient(app)


def _admin_token(**overrides):
    token = {
        "uid": ADMIN_UID,
        "email": "admin@fasalx.com",
        "name": "FasalX Admin",
        "email_verified": True,
        "admin": True,
    }
    token.update(overrides)
    return token


def _farmer_token():
    return {
        "uid": FARMER_UID,
        "email": "farmer@fasalx.com",
        "name": "FasalX Farmer",
        "email_verified": True,
    }


def _set_auth(token):
    async def _override():
        return token

    app.dependency_overrides[get_current_user] = _override


@pytest.fixture(autouse=True)
def cleanup_overrides():
    old_override = app.dependency_overrides.get(get_current_user)
    yield
    db_instance.db = None
    if old_override is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = old_override


def test_admin_me_requires_firebase_admin_claim(mock_db_factory):
    _set_auth(_farmer_token())
    db_instance.db = mock_db_factory(users_doc={"_id": FARMER_UID, "role": "admin", "is_active": True})

    response = client.get("/api/v1/admin/auth/me")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_ACCESS_REQUIRED"


def test_admin_me_returns_effective_access(mock_db_factory):
    _set_auth(_admin_token(admin_permissions=["users:export"]))
    db_instance.db = mock_db_factory(
        users_doc={
            "_id": ADMIN_UID,
            "display_name": "Ops Admin",
            "role": "farmer",
            "is_active": True,
        }
    )

    response = client.get("/api/v1/admin/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == ADMIN_UID
    assert body["display_name"] == "Ops Admin"
    assert body["access"]["role"] == "admin"
    assert "users:read" in body["access"]["permissions"]
    assert "users:export" in body["access"]["permissions"]


def test_inactive_admin_profile_is_denied(mock_db_factory):
    _set_auth(_admin_token())
    db_instance.db = mock_db_factory(users_doc={"_id": ADMIN_UID, "is_active": False})

    response = client.get("/api/v1/admin/auth/me")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_ACCOUNT_INACTIVE"


def test_admin_sync_upserts_profile_and_logs_activity(mock_db_factory):
    _set_auth(_admin_token(role="super_admin"))
    db = mock_db_factory(users_doc=None)
    db_instance.db = db

    response = client.post("/api/v1/admin/auth/sync")

    assert response.status_code == 200
    assert response.json()["message"] == "Admin synchronized successfully"
    db.users.update_one.assert_called_once()
    db.user_activities.insert_one.assert_called_once()

    _, update_doc = db.users.update_one.call_args.args[:2]
    assert update_doc["$set"]["role"] == "super_admin"
    assert update_doc["$set"]["admin_access"]["source"] == "firebase_custom_claims"
    assert "admins:manage" in update_doc["$set"]["admin_access"]["permissions"]


def test_user_profile_update_cannot_self_assign_admin(mock_db_factory):
    _set_auth(_farmer_token())
    db = mock_db_factory(users_doc={"_id": FARMER_UID, "role": "farmer", "is_active": True})
    db_instance.db = db

    response = client.post(
        "/api/v1/users/me",
        json={
            "display_name": "Escalation Attempt",
            "preferred_language": "en",
            "role": "admin",
            "is_active": False,
        },
    )

    assert response.status_code == 200
    update_doc = db.users.update_one.call_args.args[1]
    assert "role" not in update_doc["$set"]
    assert "is_active" not in update_doc["$set"]


@patch("app.api.routers.admin_auth.auth.revoke_refresh_tokens")
def test_admin_logout_revokes_tokens(mock_revoke, mock_db_factory):
    _set_auth(_admin_token())
    db_instance.db = mock_db_factory(users_doc={"_id": ADMIN_UID, "is_active": True})

    response = client.post("/api/v1/admin/auth/logout")

    assert response.status_code == 200
    mock_revoke.assert_called_once_with(ADMIN_UID)


@pytest.mark.asyncio
async def test_permission_dependency_rejects_missing_permission():
    dependency = require_admin_permission("system:manage")

    with pytest.raises(AuthorizationError):
        await dependency({"permissions": ["users:read"]})
