import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.db.mongodb import get_mongo_db
from app.models.user import UserActivity
from firebase_admin import auth

logger = logging.getLogger(__name__)

async def log_user_activity(user_id: str, action: str, metadata: Optional[Dict[str, Any]] = None):
    """
    Logs a user action to the 'user_activities' MongoDB collection.
    """
    db = get_mongo_db()
    if db is None:
        logger.error("Failed to log activity: Database not initialized.")
        return

    activity = UserActivity(
        user_id=user_id,
        action=action,
        metadata=metadata,
        timestamp=datetime.now(timezone.utc)
    )
    
    try:
        await db.user_activities.insert_one(activity.model_dump())
    except Exception as e:
        logger.error(f"Failed to log user activity {action} for {user_id}: {e}")

async def deactivate_user_account(user_id: str):
    """
    Soft deletes the user account by setting is_active = False.
    """
    db = get_mongo_db()
    if db is None:
        raise Exception("Database not initialized")
        
    await db.users.update_one(
        {"_id": user_id},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    # Optionally revoke current tokens so they are forced out
    try:
        auth.revoke_refresh_tokens(user_id)
    except Exception as e:
        logger.error(f"Error revoking tokens during deactivation for {user_id}: {e}")
        
    await log_user_activity(user_id, "ACCOUNT_DEACTIVATED")

async def delete_user_account(user_id: str):
    """
    Hard deletes the user account from MongoDB and Firebase Auth.
    """
    db = get_mongo_db()
    if db is None:
        raise Exception("Database not initialized")
        
    # 1. Delete from Firebase Auth
    try:
        auth.delete_user(user_id)
    except auth.UserNotFoundError:
        logger.warning(f"User {user_id} not found in Firebase during deletion.")
    except Exception as e:
        logger.error(f"Failed to delete user {user_id} from Firebase: {e}")
        raise
        
    # 2. Delete from MongoDB
    try:
        # We might want to just delete the profile or all related data.
        # For now, delete the main user document.
        await db.users.delete_one({"_id": user_id})
        
        # We can also choose to delete their activities, or leave them anonymized.
        await db.user_activities.delete_many({"user_id": user_id})
    except Exception as e:
        logger.error(f"Failed to delete user {user_id} data from MongoDB: {e}")
        raise
