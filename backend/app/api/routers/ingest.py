import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.engine.models.ingestion import FieldIntelligence, WeatherData, SoilData, MarketData
from app.engine.ingestors.weather import get_weather_data
from app.engine.ingestors.soil import fetch_soil_data
from app.engine.ingestors.market import get_market_data
from app.engine.ingestors.geo import reverse_geocode
import os

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/", response_model=FieldIntelligence)
async def get_field_intelligence(
    lat: float = Query(..., description="Latitude", ge=-90.0, le=90.0),
    lon: float = Query(..., description="Longitude", ge=-180.0, le=180.0),
    commodity: Optional[str] = Query(None, description="Optional crop name for market filtering")
):
    """
    Fetches comprehensive field intelligence (Weather, Soil, Market Data) 
    in parallel for the given coordinates to power the recommendation engine.
    """
    # First, reverse geocode to get LGD codes, state, and district
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "fasalx-backend/1.0")
    geo_data = await reverse_geocode(lat, lon, user_agent)
    
    if geo_data.get("status") == "error":
        raise HTTPException(status_code=400, detail=geo_data.get("message"))
        
    address = geo_data.get("address", {})
    codes = geo_data.get("codes", {})
    
    state = address.get("state")
    district = address.get("district")
    lgd_code = codes.get("district_lgd")
    market = district # Usually Mandi API takes district names as market parameter
    
    errors = {}
    weather: Optional[WeatherData] = None
    soil: Optional[SoilData] = None
    market_data: Optional[MarketData] = None
    
    # Define wrapper functions to catch errors and prevent them from failing the whole gather block
    async def safe_weather():
        try:
            return await get_weather_data(lat, lon)
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            errors["weather"] = str(e)
            return None
            
    async def safe_soil():
        try:
            return await fetch_soil_data(lat=lat, lon=lon, lgd_code=lgd_code, state=state, district=district)
        except Exception as e:
            logger.error(f"Soil fetch failed: {e}")
            errors["soil"] = str(e)
            return None
            
    async def safe_market():
        try:
            return await get_market_data(state=state, market=market, commodity=commodity)
        except Exception as e:
            logger.error(f"Market fetch failed: {e}")
            errors["market"] = str(e)
            return None

    # Fetch all data concurrently
    weather, soil, market_data = await asyncio.gather(
        safe_weather(),
        safe_soil(),
        safe_market()
    )
    
    return FieldIntelligence(
        coordinates={"lat": lat, "lon": lon},
        weather=weather,
        soil=soil,
        market=market_data,
        errors=errors
    )
