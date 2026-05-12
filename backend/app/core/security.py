from fastapi import Depends
from app.core.exceptions import AuthError, AuthorizationError
from app.db.mongodb import get_mongo_db
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

security = HTTPBearer()

ADMIN_ROLES = {"admin", "super_admin"}
ADMIN_PERMISSIONS = {
    "users:read",
    "users:write",
    "users:deactivate",
    "fields:read",
    "fields:write",
    "telemetry:read",
    "agronomy:read",
    "agronomy:write",
    "reports:read",
    "audit:read",
    "dashboard:manage",
}
SUPER_ADMIN_PERMISSIONS = ADMIN_PERMISSIONS | {
    "admins:manage",
    "system:manage",
}

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verifies the Firebase JWT token and returns the decoded token payload.
    The payload includes the user's uid.
    """
    token = credentials.credentials
    try:
        # check_revoked=True ensures that logged out or disabled users are rejected immediately
        decoded_token = auth.verify_id_token(token, check_revoked=True)
        return decoded_token
    except auth.RevokedIdTokenError:
        logger.error("Token has been revoked.")
        raise AuthError(
            message="Token has been revoked. Please reauthenticate.",
            code="TOKEN_REVOKED",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.ExpiredIdTokenError:
        logger.error("Token has expired.")
        raise AuthError(
            message="Token has expired. Please reauthenticate.",
            code="TOKEN_EXPIRED",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.InvalidIdTokenError:
        logger.error("Invalid token.")
        raise AuthError(
            message="Invalid token.",
            code="TOKEN_INVALID",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Error verifying Firebase ID token: {e}")
        raise AuthError(
            message="Invalid authentication credentials",
            code="AUTH_CREDENTIALS_INVALID",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _extract_admin_access(decoded_token: dict) -> tuple[str | None, set[str]]:
    roles = {role.lower() for role in _as_list(decoded_token.get("roles"))}
    roles.update(role.lower() for role in _as_list(decoded_token.get("role")))

    if decoded_token.get("admin") is True:
        roles.add("admin")
    if decoded_token.get("super_admin") is True:
        roles.add("super_admin")

    if "super_admin" in roles:
        role = "super_admin"
        permissions = set(SUPER_ADMIN_PERMISSIONS)
    elif "admin" in roles:
        role = "admin"
        permissions = set(ADMIN_PERMISSIONS)
    else:
        return None, set()

    permissions.update(_as_list(decoded_token.get("permissions")))
    permissions.update(_as_list(decoded_token.get("admin_permissions")))
    return role, permissions


async def get_current_admin(current_user: dict = Depends(get_current_user)):
    """
    Verifies that the Firebase token carries trusted admin custom claims.
    MongoDB profile data can disable an account, but it is not trusted as the
    source of admin privilege.
    """
    role, permissions = _extract_admin_access(current_user)
    if role not in ADMIN_ROLES:
        raise AuthorizationError(
            message="Admin privileges are required for this endpoint.",
            code="ADMIN_ACCESS_REQUIRED",
        )

    uid = current_user.get("uid")
    if not uid:
        raise AuthError(
            message="Authenticated token is missing a user id.",
            code="TOKEN_UID_MISSING",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db = get_mongo_db()
    profile = None
    if db is not None and uid:
        profile = await db.users.find_one({"_id": uid})
        if profile and profile.get("is_active") is False:
            raise AuthorizationError(
                message="Admin account is inactive.",
                code="ADMIN_ACCOUNT_INACTIVE",
            )

    return {
        "uid": uid,
        "email": current_user.get("email"),
        "name": current_user.get("name"),
        "role": role,
        "permissions": sorted(permissions),
        "profile": profile,
    }


def require_admin_permission(permission: str) -> Callable:
    async def _dependency(current_admin: dict = Depends(get_current_admin)):
        permissions = set(current_admin.get("permissions", []))
        if "*" not in permissions and permission not in permissions:
            raise AuthorizationError(
                message=f"Admin permission '{permission}' is required.",
                code="ADMIN_PERMISSION_REQUIRED",
            )
        return current_admin

    return _dependency
