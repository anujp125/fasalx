from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import get_current_user
from app.db.mongodb import get_mongo_db
from app.models.user import FarmerProfile
from app.services.user_service import log_user_activity, deactivate_user_account, delete_user_account
from app.core.exceptions import DatabaseError, ValidationError, AuthError
from datetime import datetime, timezone
from firebase_admin import auth

router = APIRouter()

@router.post("/sync", status_code=status.HTTP_200_OK)
async def sync_user(current_user: dict = Depends(get_current_user)):
    """
    Called by the client immediately after a successful Firebase login.
    Ensures the user document exists in MongoDB and logs the login activity.
    """
    import traceback
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        uid = current_user.get("uid")
        db = get_mongo_db()
        if db is None:
            raise DatabaseError(message="Database not initialized", code="DB_NOT_INITIALIZED")
        
        # Initialize basic profile using data from Firebase token if available
        email = current_user.get("email")
        phone = current_user.get("phone_number")
        
        name = current_user.get("name")
        if not name:
            if email:
                name = email.split("@")[0]
            else:
                name = "Anonymous"
        
        initial_data = {
            "display_name": name,
            "role": "farmer",
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        if phone:
            initial_data["phone_number"] = phone
            
        # Use atomic upsert to avoid race conditions (find_one + insert_one)
        try:
            await db.users.update_one(
                {"_id": uid},
                {"$setOnInsert": initial_data},
                upsert=True
            )
            logger.info(f"User {uid} synchronized successfully in database.")
        except Exception as db_e:
            logger.error(f"MongoDB error in sync_user for uid {uid}: {db_e}")
            raise DatabaseError(message="Failed to synchronize user data", code="SYNC_DB_ERROR")
            
        await log_user_activity(uid, "LOGIN", metadata={"email_verified": current_user.get("email_verified", False)})
        return {"message": "User synchronized successfully"}
    except (DatabaseError, ValidationError, AuthError):
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"sync_user FAILED: {e}\n{tb}")
        raise DatabaseError(message=f"Sync failed unexpectedly", code="SYNC_UNEXPECTED_ERROR")

@router.get("/me")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """
    Get the currently logged-in user's profile from MongoDB.
    Includes an `updated_at` field for offline syncing.
    """
    uid = current_user.get("uid")
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    user_doc = await db.users.find_one({"_id": uid})
    
    if user_doc:
        user_doc["id"] = user_doc.pop("_id")
        return user_doc
    
    return {"id": uid, "message": "Profile not completed"}

@router.post("/me")
async def update_my_profile(profile_data: FarmerProfile, current_user: dict = Depends(get_current_user)):
    """
    Update the user's profile in MongoDB with strict validation.
    Sets `updated_at` to facilitate Flutter offline cache invalidation.
    """
    uid = current_user.get("uid")
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    update_data = profile_data.model_dump(exclude_unset=True)
    for protected_field in ("role", "is_active"):
        update_data.pop(protected_field, None)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.users.update_one(
        {"_id": uid},
        {"$set": update_data},
        upsert=True
    )
    
    await log_user_activity(uid, "PROFILE_UPDATE", metadata={"fields_updated": list(update_data.keys())})
    return {"message": "Profile updated successfully", "updated_at": update_data["updated_at"]}

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user: dict = Depends(get_current_user)):
    """
    Revokes the user's refresh tokens, forcing them to re-authenticate on all devices.
    """
    uid = current_user.get("uid")
    try:
        auth.revoke_refresh_tokens(uid)
        await log_user_activity(uid, "LOGOUT")
        return {"message": "Successfully logged out from all devices"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to logout: {str(e)}")

@router.post("/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_account(current_user: dict = Depends(get_current_user)):
    """
    Soft deletes the account.
    """
    uid = current_user.get("uid")
    try:
        await deactivate_user_account(uid)
        return {"message": "Account deactivated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate account: {str(e)}")

@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_account(current_user: dict = Depends(get_current_user)):
    """
    Hard deletes the account from Firebase and MongoDB.
    """
    uid = current_user.get("uid")
    try:
        await delete_user_account(uid)
        return {"message": "Account deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")

@router.get("/activities")
async def get_my_activities(limit: int = 20, offset: int = 0, current_user: dict = Depends(get_current_user)):
    """
    Get the user's activity history.
    """
    uid = current_user.get("uid")
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    cursor = db.user_activities.find({"user_id": uid}).sort("timestamp", -1).skip(offset).limit(limit)
    activities = await cursor.to_list(length=limit)
    
    # Convert ObjectIds to strings for JSON serialization
    for activity in activities:
        activity["id"] = str(activity.pop("_id"))
        
    return {"activities": activities}
