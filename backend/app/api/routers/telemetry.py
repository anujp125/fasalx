from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.mongodb import get_mongo_db
from app.models.telemetry import IoTDevicePayload
from datetime import datetime, timezone

router = APIRouter()

@router.post("/data", response_model=dict)
async def ingest_telemetry(payload: IoTDevicePayload, current_user: dict = Depends(get_current_user)):
    """
    Ingest IoT sensor telemetry data (moisture, pH, NPK) into MongoDB.
    Validates data strictly via Pydantic.
    """
    uid = current_user.get("uid")
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    # Dump the validated model
    data = payload.model_dump()
    
    # Attach server-side timestamp and user_id
    if data.get("timestamp") is None:
        data["timestamp"] = datetime.now(timezone.utc)
        
    data["user_id"] = uid
    data["sync_status"] = "synced"
    
    # Write directly to telemetry collection. MongoDB handles high write throughput well.
    result = await db.telemetry.insert_one(data)
    
    return {
        "message": "Telemetry data ingested successfully",
        "id": str(result.inserted_id)
    }
