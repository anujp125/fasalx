from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from firebase_admin import auth

from app.core.exceptions import DatabaseError
from app.core.security import get_current_admin
from app.db.mongodb import get_mongo_db
from app.models.admin import AdminAccess, AdminAuthResponse, AdminLogoutResponse, AdminSyncResponse
from app.services.user_service import log_user_activity

router = APIRouter()


def _build_admin_response(current_admin: dict) -> AdminAuthResponse:
    profile = current_admin.get("profile") or {}
    uid = current_admin.get("uid")
    return AdminAuthResponse(
        uid=uid,
        email=current_admin.get("email") or profile.get("email"),
        display_name=profile.get("display_name") or current_admin.get("name") or "FasalX Admin",
        is_active=profile.get("is_active", True),
        access=AdminAccess(
            role=current_admin["role"],
            permissions=current_admin.get("permissions", []),
        ),
    )


@router.get("/me", response_model=AdminAuthResponse)
async def get_admin_session(current_admin: dict = Depends(get_current_admin)):
    """
    Returns the current admin identity and effective access.
    Access is based on verified Firebase custom claims, not mutable profile data.
    """
    return _build_admin_response(current_admin)


@router.post("/sync", response_model=AdminSyncResponse, status_code=status.HTTP_200_OK)
async def sync_admin(current_admin: dict = Depends(get_current_admin)):
    """
    Creates or updates the admin profile after Firebase login.
    The stored role mirrors trusted Firebase custom claims for UI display only.
    """
    db = get_mongo_db()
    if db is None:
        raise DatabaseError(message="Database not initialized", code="DB_NOT_INITIALIZED")

    now = datetime.now(timezone.utc).isoformat()
    uid = current_admin["uid"]
    update_data = {
        "display_name": current_admin.get("name") or "FasalX Admin",
        "email": current_admin.get("email"),
        "role": current_admin["role"],
        "is_active": True,
        "admin_access": {
            "source": "firebase_custom_claims",
            "permissions": current_admin.get("permissions", []),
            "synced_at": now,
        },
        "updated_at": now,
    }

    await db.users.update_one(
        {"_id": uid},
        {"$set": update_data, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await log_user_activity(
        uid,
        "ADMIN_SYNC",
        metadata={"role": current_admin["role"], "permissions": current_admin.get("permissions", [])},
    )

    current_admin["profile"] = {**(current_admin.get("profile") or {}), **update_data}
    return AdminSyncResponse(
        message="Admin synchronized successfully",
        admin=_build_admin_response(current_admin),
    )


@router.post("/logout", response_model=AdminLogoutResponse, status_code=status.HTTP_200_OK)
async def logout_admin(current_admin: dict = Depends(get_current_admin)):
    """
    Revokes admin refresh tokens, forcing reauthentication on all devices.
    """
    uid = current_admin["uid"]
    auth.revoke_refresh_tokens(uid)
    await log_user_activity(uid, "ADMIN_LOGOUT")
    return AdminLogoutResponse(message="Admin logged out successfully")
