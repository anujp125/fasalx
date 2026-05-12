import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from app.models.fields import FieldRegistrationRequest, FieldResponse, FarmOverviewResponse
from app.core.security import get_current_user
from app.services.field_service import create_field, get_user_fields, get_farm_overview

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", response_model=dict)
async def register_field(
    request: FieldRegistrationRequest,
    current_user: dict = Depends(get_current_user)
):
    """Register a new field plot for the user."""
    user_id = current_user.get("uid")
    try:
        field_id = await create_field(user_id, request)
        return {"status": "success", "field_id": field_id}
    except Exception as e:
        logger.error(f"Failed to register field: {e}")
        raise HTTPException(status_code=500, detail="Could not register field")

@router.get("/", response_model=List[FieldResponse])
async def list_fields(current_user: dict = Depends(get_current_user)):
    """List all registered fields for the current user."""
    user_id = current_user.get("uid")
    fields = await get_user_fields(user_id)
    return fields

@router.get("/summary", response_model=FarmOverviewResponse)
async def farm_overview(current_user: dict = Depends(get_current_user)):
    """Get aggregated profit/cost overview of all active fields."""
    user_id = current_user.get("uid")
    overview = await get_farm_overview(user_id)
    return overview
