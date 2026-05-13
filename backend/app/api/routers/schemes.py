from fastapi import APIRouter, HTTPException
from app.db.mongodb import get_mongo_db

router = APIRouter()

@router.get("/")
async def get_schemes():
    """Fetch all active government schemes for the user."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    schemes = await db.schemes.find({"is_active": {"$ne": False}}).sort("created_at", -1).to_list(500)
    for s in schemes:
        s["id"] = str(s.pop("_id"))
    return {"schemes": schemes}
