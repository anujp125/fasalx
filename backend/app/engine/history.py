import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from bson import ObjectId
from app.db.mongodb import get_mongo_db
from app.engine.models.recommendation import RecommendationResponse

logger = logging.getLogger(__name__)

async def get_previous_crop(user_id: str, field_id: str) -> Optional[str]:
    """
    Finds the most recently selected crop for a given user and specific field.
    """
    db = get_mongo_db()
    if db is None:
        return None
        
    try:
        # Find the most recent document for this user where a crop was selected
        # and coordinates are within the radius.
        cursor = db.recommendations.find({
            "user_id": user_id,
            "field_id": field_id,
            "selected_crop": {"$ne": None}
        }).sort("created_at", -1).limit(1)
        
        async for doc in cursor:
            return doc.get("selected_crop")
            
        return None
    except Exception as e:
        logger.error(f"Error querying previous crop history: {e}")
        return None

async def save_recommendation_session(
    user_id: str, 
    field_id: str,
    lat: float, 
    lon: float, 
    intelligence: Dict[str, Any], 
    recommendations: Dict[str, Any] # Now supports dict of lists (dual-track)
) -> str:
    """
    Saves a recommendation session to MongoDB.
    Returns the inserted document ID as a string.
    """
    db = get_mongo_db()
    if db is None:
        logger.warning("MongoDB not initialized, skipping save_recommendation_session")
        return ""
        
    doc = {
        "user_id": user_id,
        "field_id": field_id,
        "coordinates": {"lat": lat, "lon": lon},
        "intelligence": intelligence,
        "recommendations": recommendations,
        "selected_crop": None,
        "created_at": datetime.now(timezone.utc)
    }
    
    try:
        result = await db.recommendations.insert_one(doc)
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to save recommendation session: {e}")
        return ""

async def mark_crop_selected(user_id: str, field_id: str, recommendation_id: str, crop_name: str) -> bool:
    """
    Updates the recommendation document to mark a specific crop as selected.
    Also updates the actual field document to track active crop.
    """
    db = get_mongo_db()
    if db is None:
        return False
        
    try:
        # Update recommendation session
        res1 = await db.recommendations.update_one(
            {"_id": ObjectId(recommendation_id), "user_id": user_id, "field_id": field_id},
            {"$set": {"selected_crop": crop_name, "updated_at": datetime.now(timezone.utc)}}
        )
        
        # Update Field directly
        from app.services.field_service import update_field_crop
        await update_field_crop(user_id, field_id, crop_name)
        
        return res1.modified_count > 0
    except Exception as e:
        logger.error(f"Error marking crop selected: {e}")
        return False
