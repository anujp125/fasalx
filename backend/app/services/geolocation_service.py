import httpx
import logging
import json
from typing import Optional, Tuple
from fastapi import Request
from app.db.redis import get_redis
from app.db.mongodb import get_mongo_db

logger = logging.getLogger(__name__)

# Free IP Geolocation API
IP_API_URL = "http://ip-api.com/json/"

async def resolve_location(
    request: Request, 
    uid: str, 
    lat: Optional[float] = None, 
    lon: Optional[float] = None,
    state: Optional[str] = None,
    market: Optional[str] = None
) -> dict:
    """
    Resolves the user's location (lat/lon and state/city) handling conflicts through a strict hierarchy:
    1. Explicit Frontend GPS (Query Parameters)
    2. User's saved FarmerProfile in MongoDB
    3. IP-based Geolocation (Fallback)
    
    Returns a dict: {"lat": float, "lon": float, "state": str, "market": str}
    """
    result = {
        "lat": lat,
        "lon": lon,
        "state": state,
        "market": market,
        "source": "explicit"
    }
    
    # 1. If explicit frontend coordinates AND state/market are provided, trust them completely
    if lat is not None and lon is not None and state is not None and market is not None:
        return result
        
    # 2. Check MongoDB for saved profile location if anything is missing
    db = get_mongo_db()
    if db is not None:
        user_doc = await db.users.find_one({"_id": uid})
        if user_doc and user_doc.get("location"):
            loc = user_doc["location"]
            # Fill missing data from profile
            result["lat"] = result["lat"] or loc.get("latitude")
            result["lon"] = result["lon"] or loc.get("longitude")
            # We assume state/market might be saved in profile in the future, if not we proceed
            result["state"] = result["state"] or user_doc.get("state")
            result["market"] = result["market"] or user_doc.get("market")
            
            if result["source"] == "explicit":
                result["source"] = "profile_fallback"
                
    # If we have enough data now, return early
    if result["lat"] is not None and result["lon"] is not None and result["state"] is not None and result["market"] is not None:
        return result

    # 3. IP-based Fallback
    client_ip = request.client.host
    # If running locally, localhost IP won't work with external APIs, mock it to a random Indian IP for testing
    if client_ip == "127.0.0.1" or client_ip == "::1":
        client_ip = "103.45.x.x" # You would typically use a real IP or just skip if local
        # For our case, let's use a standard Delhi IP if localhost
        client_ip = "103.20.104.1" 
        
    redis_client = get_redis()
    cache_key = f"ip_geo:{client_ip}"
    
    ip_data = None
    
    # Check Redis Cache
    if redis_client:
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            ip_data = json.loads(cached_data)
            logger.info(f"IP Geo Cache hit for {client_ip}")

    # Fetch from API if not in cache
    if not ip_data:
        logger.info(f"Fetching IP Geo from API for {client_ip}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{IP_API_URL}{client_ip}", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        ip_data = data
                        if redis_client:
                            # Cache IP mapping for 24 hours
                            await redis_client.setex(cache_key, 86400, json.dumps(ip_data))
        except Exception as e:
            logger.error(f"IP Geolocation failed: {e}")
            
    # Fill remaining gaps with IP data
    if ip_data:
        result["lat"] = result["lat"] or ip_data.get("lat")
        result["lon"] = result["lon"] or ip_data.get("lon")
        result["state"] = result["state"] or ip_data.get("regionName")
        result["market"] = result["market"] or ip_data.get("city")
        result["source"] = "ip_fallback"
        
    # If we STILL don't have lat/lon, default to something (e.g., Delhi, India)
    if result["lat"] is None or result["lon"] is None:
        result["lat"] = 28.6139
        result["lon"] = 77.2090
        result["source"] = "absolute_default"
        
    if result["state"] is None:
        result["state"] = "Delhi"
    if result["market"] is None:
        result["market"] = "Delhi"

    return result
