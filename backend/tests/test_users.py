import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import app
from app.core.security import get_current_user
from app.db.mongodb import get_mongo_db

client = TestClient(app)

# Mock user data
MOCK_UID = "test-uid-123"
MOCK_USER = {
    "uid": MOCK_UID,
    "email": "test@example.com",
    "name": "Test User",
    "email_verified": True
}

# Override auth dependency
async def override_get_current_user():
    return MOCK_USER

app.dependency_overrides[get_current_user] = override_get_current_user

@pytest.fixture
def mock_db():
    mock_db = MagicMock()
    mock_db.users = AsyncMock()
    mock_db.user_activities = AsyncMock()
    return mock_db

@pytest.fixture
def override_db(mock_db):
    def _override_get_mongo_db():
        return mock_db
    
    # Store old db override if any
    app.dependency_overrides[get_mongo_db] = _override_get_mongo_db
    yield
    app.dependency_overrides.pop(get_mongo_db, None)

def test_sync_user_new(override_db, mock_db):
    response = client.post("/api/v1/users/sync")
    
    assert response.status_code == 200
    assert response.json() == {"message": "User synchronized successfully"}
    mock_db.users.update_one.assert_called_once()
    mock_db.user_activities.insert_one.assert_called_once() # Called via log_user_activity

def test_sync_user_missing_email(override_db, mock_db):
    async def override_get_current_user_no_email():
        return {"uid": "phone-uid-123", "phone_number": "+1234567890", "email": None}
    
    app.dependency_overrides[get_current_user] = override_get_current_user_no_email
    
    response = client.post("/api/v1/users/sync")
    
    assert response.status_code == 200
    mock_db.users.update_one.assert_called_once()
    
    # Check the call arguments for update_one
    args, kwargs = mock_db.users.update_one.call_args
    assert args[0] == {"_id": "phone-uid-123"}
    assert args[1]["$setOnInsert"]["display_name"] == "Anonymous"
    assert args[1]["$setOnInsert"]["phone_number"] == "+1234567890"

    # Restore original override
    app.dependency_overrides[get_current_user] = override_get_current_user

def test_sync_user_db_failure(override_db, mock_db):
    # Make the update_one raise an Exception
    mock_db.users.update_one.side_effect = Exception("MongoDB connection refused")
    
    response = client.post("/api/v1/users/sync")
    
    # We should get 500 error but with the custom format
    assert response.status_code == 500
    json_resp = response.json()
    assert json_resp["success"] is False
    assert json_resp["error"]["code"] == "SYNC_DB_ERROR"

def test_get_my_profile_existing(override_db, mock_db):
    mock_db.users.find_one.return_value = {
        "_id": MOCK_UID,
        "display_name": "Test User",
        "role": "farmer"
    }
    
    response = client.get("/api/v1/users/me")
    
    assert response.status_code == 200
    assert response.json()["display_name"] == "Test User"
    assert response.json()["id"] == MOCK_UID

def test_update_my_profile(override_db, mock_db):
    payload = {
        "display_name": "Updated Name",
        "avatar_url": "https://example.com/avatar.jpg"
    }
    
    response = client.post("/api/v1/users/me", json=payload)
    
    assert response.status_code == 200
    assert "updated_at" in response.json()
    mock_db.users.update_one.assert_called_once()
    mock_db.user_activities.insert_one.assert_called_once()

@patch("app.api.routers.users.auth.revoke_refresh_tokens")
def test_logout(mock_revoke, override_db, mock_db):
    response = client.post("/api/v1/users/logout")
    
    assert response.status_code == 200
    mock_revoke.assert_called_once_with(MOCK_UID)
    mock_db.user_activities.insert_one.assert_called_once()

@patch("app.services.user_service.auth.revoke_refresh_tokens")
def test_deactivate_account(mock_revoke, override_db, mock_db):
    response = client.post("/api/v1/users/deactivate")
    
    assert response.status_code == 200
    mock_db.users.update_one.assert_called_once()
    mock_revoke.assert_called_once_with(MOCK_UID)

@patch("app.services.user_service.auth.delete_user")
def test_delete_account(mock_delete, override_db, mock_db):
    response = client.delete("/api/v1/users/me")
    
    assert response.status_code == 200
    mock_delete.assert_called_once_with(MOCK_UID)
    mock_db.users.delete_one.assert_called_once_with({"_id": MOCK_UID})
    mock_db.user_activities.delete_many.assert_called_once_with({"user_id": MOCK_UID})

def test_get_activities(override_db, mock_db):
    mock_cursor = AsyncMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    
    mock_cursor.to_list.return_value = [
        {"_id": "act1", "action": "LOGIN"},
        {"_id": "act2", "action": "LOGOUT"}
    ]
    mock_db.user_activities.find.return_value = mock_cursor
    
    response = client.get("/api/v1/users/activities")
    
    assert response.status_code == 200
    activities = response.json()["activities"]
    assert len(activities) == 2
    assert activities[0]["id"] == "act1"
