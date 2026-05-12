from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends
from arq import create_pool
from arq.connections import RedisSettings
from app.core.config import settings
from app.db.mongodb import get_mongo_db
from app.models.timeline import UserCropTimeline, EnvironmentalSnapshot
from app.core.security import verify_token
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Dependency for Arq Redis Pool
async def get_redis_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))

@router.post("/", response_model=UserCropTimeline, status_code=201)
async def create_timeline(timeline_request: UserCropTimeline):
    """
    Initializes a new crop timeline for the user based on a template.
    (Auth temporarily bypassed for frontend development)
    """
    # if current_user.get("uid") != timeline_request.user_metadata.user_id:
    #     raise HTTPException(status_code=403, detail="Not authorized to create this timeline")
        
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    # Check if a timeline already exists for this crop
    existing = await db.user_crop_timelines.find_one({
        "user_metadata.user_id": timeline_request.user_metadata.user_id,
        "user_metadata.crop_id": timeline_request.user_metadata.crop_id
    })
    
    if existing:
        raise HTTPException(status_code=409, detail="Timeline already exists for this crop")
        
    # Set initial snapshot
    timeline_request.environmental_snapshot.last_updated = datetime.now(timezone.utc)
    
    new_timeline_data = timeline_request.model_dump(by_alias=True, exclude_unset=True)
    result = await db.user_crop_timelines.insert_one(new_timeline_data)
    
    new_timeline_data["_id"] = str(result.inserted_id)
    return UserCropTimeline(**new_timeline_data)

@router.get("/{user_id}", response_model=UserCropTimeline)
async def get_timeline(user_id: str):
    """
    Returns the complete visualized journey for the frontend.
    (Auth temporarily bypassed for frontend development)
    """
    # if current_user.get("uid") != user_id:
    #     raise HTTPException(status_code=403, detail="Not authorized to access this timeline")
        
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    doc = await db.user_crop_timelines.find_one({"user_metadata.user_id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Timeline not found")
        
    return UserCropTimeline(**doc)

@router.post("/sync-iot")
async def sync_iot_data(user_id: str, t_max: float, t_min: float, soil_moisture: float):
    """
    Webhook to receive MQTT-to-HTTP data from soil sensors.
    (In production, this would be authenticated via an IoT API key or basic auth, 
    but for now we leave it open as a webhook receiver)
    """
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    snapshot = EnvironmentalSnapshot(
        last_updated=datetime.now(timezone.utc),
        t_max=t_max,
        t_min=t_min,
        soil_moisture=soil_moisture,
        source="iot",
        weight=1.0 # Highest quality data
    )
    
    # 1. Update the snapshot in DB quickly
    await db.user_crop_timelines.update_one(
        {"user_metadata.user_id": user_id},
        {"$set": {"environmental_snapshot": snapshot.model_dump()}}
    )
    
    # 2. Queue the background task using Arq
    redis_pool = await get_redis_pool()
    await redis_pool.enqueue_job('recalculate_timeline_gdd', user_id)
    
    return {"message": "IoT data synced and background recalculation queued."}

@router.patch("/recalibrate")
async def manual_recalibrate(user_id: str, milestone_name: str):
    """
    Manual override if the farmer confirms a stage has been reached early.
    (Auth temporarily bypassed for frontend development)
    """
    # if current_user.get("uid") != user_id:
    #     raise HTTPException(status_code=403, detail="Not authorized to recalibrate this timeline")
        
    db = get_mongo_db()
    
    # Update a specific milestone status inside the array
    result = await db.user_crop_timelines.update_one(
        {
            "user_metadata.user_id": user_id, 
            "milestone_map.name": milestone_name
        },
        {
            "$set": {
                "milestone_map.$.status": "completed",
                "milestone_map.$.completed_date": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Milestone not found or already completed")
        
    return {"message": f"Milestone '{milestone_name}' manually marked as completed."}
