from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from app.engine.ingestors.geo import reverse_geocode
from app.core.config import settings
import os

router = APIRouter()

class GeoRequest(BaseModel):
    lat: float = Field(..., description="Latitude of the location", ge=-90.0, le=90.0)
    lon: float = Field(..., description="Longitude of the location", ge=-180.0, le=180.0)

class Coordinates(BaseModel):
    lat: float
    lon: float

class AddressComponent(BaseModel):
    state: Optional[str]
    district: Optional[str]
    block: Optional[str]
    pincode: Optional[str]

class CodesComponent(BaseModel):
    state_lgd: Optional[int]
    district_lgd: Optional[int]

class GeoResponse(BaseModel):
    status: str
    message: Optional[str] = None
    coordinates: Optional[Coordinates] = None
    address: Optional[AddressComponent] = None
    codes: Optional[CodesComponent] = None

@router.post("/", response_model=GeoResponse)
async def get_geolocation(request: GeoRequest):
    """
    Reverse geocodes a latitude and longitude to get administrative data
    including state, district, block, pincode and LGD codes.
    """
    # Fetch User-Agent from environment variables (with a default fallback)
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "fasalx-backend/1.0 (anujpwr125@gmail.com)")
    
    result = await reverse_geocode(request.lat, request.lon, user_agent)
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
        
    return result
