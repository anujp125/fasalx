import httpx
import json
import logging
from typing import Optional, List, Dict, Any
from app.db.redis import get_redis
from app.core.config import settings
from app.engine.models.ingestion import MarketData, CommodityPrice

logger = logging.getLogger(__name__)

MANDI_API_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

DISTRICT_TO_MANDI = {
    "Delhi": "Azadpur",
    "New Delhi": "Azadpur",
    "Jaisalmer": "Jaisalmer",
    "Jalna": "Jalna",
    "Purnia": "Purnea",
    "Pune": "Pune",
    "Nashik": "Nasik",
    "Bengaluru Urban": "Bangalore",
    "Bengaluru Rural": "Bangalore",
    "Bangalore Urban": "Bangalore",
    "Bangalore Rural": "Bangalore",
    "Ahmednagar": "Ahmednagar",
    "Ahilyanagar": "Ahmednagar",
    "Mumbai City": "Mumbai",
    "Mumbai Suburban": "Mumbai",
    "Gautam Buddha Nagar": "Noida",
    "Gurugram": "Gurgaon",
}

CROP_MSP_ALIAS_MAP = {
    "arhar": "Arhar",
    "tur": "Arhar",
    "bajra": "Bajra",
    "barley": "Barley",
    "gram": "Gram",
    "chana": "Gram",
    "jowar": "Jowar (Hybrid)",
    "jowar hybrid": "Jowar (Hybrid)",
    "maize": "Maize",
    "masur": "Masur",
    "lentil": "Masur",
    "moong": "Moong",
    "paddy": "Paddy(Dhan)(Common)",
    "paddy (common)": "Paddy(Dhan)(Common)",
    "paddy(dhan)(common)": "Paddy(Dhan)(Common)",
    "rapeseed & mustard": "Mustard",
    "mustard": "Mustard",
    "soyabean": "Soyabean",
    "soyabean yellow": "Soyabean",
    "soybean": "Soyabean",
    "soybean yellow": "Soyabean",
    "wheat": "Wheat",
}

MSP_DATA = {
    "Paddy(Dhan)(Common)": {"msp": 2369, "marketing_season": "KMS 2025-26"},
    "Jowar (Hybrid)": {"msp": 3699, "marketing_season": "KMS 2025-26"},
    "Bajra": {"msp": 2775, "marketing_season": "KMS 2025-26"},
    "Maize": {"msp": 2400, "marketing_season": "KMS 2025-26"},
    "Arhar": {"msp": 8000, "marketing_season": "KMS 2025-26"},
    "Moong": {"msp": 8768, "marketing_season": "KMS 2025-26"},
    "Soyabean": {"msp": 5328, "marketing_season": "KMS 2025-26"},
    "Wheat": {"msp": 2585, "marketing_season": "RMS 2026-27"},
    "Barley": {"msp": 2150, "marketing_season": "RMS 2026-27"},
    "Gram": {"msp": 5875, "marketing_season": "RMS 2026-27"},
    "Masur": {"msp": 7000, "marketing_season": "RMS 2026-27"},
    "Mustard": {"msp": 6200, "marketing_season": "RMS 2026-27"},
}


def resolve_mandi_name(market: Optional[str]) -> Optional[str]:
    if not market:
        return market
    clean_market = market.replace(" District", "").strip()
    return DISTRICT_TO_MANDI.get(clean_market, clean_market)


def canonical_msp_crop_name(crop_name: str) -> str:
    normalized = str(crop_name or "").strip().lower()
    return CROP_MSP_ALIAS_MAP.get(normalized, str(crop_name or "").strip())

from app.db.mongodb import get_mongo_db

async def get_msp_trend(crop_name: str) -> Dict[str, Any]:
    db = get_mongo_db()
    if db is None:
        return {"current_msp": None, "growth_trend": None}

    canonical_name = canonical_msp_crop_name(crop_name)
    cursor = (
        db.crop_msp.find({"crop_name": canonical_name})
        .sort([("marketing_year", -1), ("year", -1)])
        .limit(4)
    )
    records = [doc async for doc in cursor]

    if not records:
        cursor = db.msp_history.find({"crop_name": canonical_name}).sort("year", -1).limit(4)
        records = [doc async for doc in cursor]
    
    if not records:
        return {"current_msp": None, "growth_trend": None}
        
    current_msp = records[0].get("msp_value") or records[0].get("msp")
    
    growth_trend = None
    if len(records) > 1:
        oldest_msp = records[-1].get("msp_value") or records[-1].get("msp")
        if oldest_msp and oldest_msp > 0:
            growth_trend = ((current_msp - oldest_msp) / oldest_msp) * 100
            
    return {
        "current_msp": current_msp,
        "growth_trend": round(growth_trend, 2) if growth_trend is not None else None
    }



def calculate_profitability_index(modal_price: float, msp: Optional[float]) -> Optional[float]:
    """
    Calculates the Profitability Index as a percentage: ((Mandi Price - MSP) / MSP) * 100
    """
    if msp and msp > 0 and modal_price:
        return round(((modal_price - msp) / msp) * 100, 2)
    return None

async def get_market_data(state: str, market: str, commodity: Optional[str] = None) -> MarketData:
    """
    Fetches Market Data using Data.gov.in Mandi prices.
    """
    return await get_data_gov_market_data(state=state, market=market, commodity=commodity)


async def get_data_gov_market_data(state: str, market: str, commodity: Optional[str] = None) -> MarketData:
    """
    Fetches Mandi prices from data.gov.in, calculates Profitability Index against MSP,
    and returns a structured MarketData object. Uses Redis caching.
    """
    redis_client = get_redis()
    
    # Normalize strings for cache key
    norm_state = state.lower().replace(" ", "") if state else ""
    resolved_market = resolve_mandi_name(market)
    norm_market = resolved_market.lower().replace(" ", "") if resolved_market else ""
    norm_commodity = commodity.lower().replace(" ", "") if commodity else ""
    cache_key = f"market_ingest:{norm_state}:{norm_market}:{norm_commodity}"
    
    # Try fetching from Redis Cache first
    if redis_client:
        try:
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for Market data at {state}, {market}")
                try:
                    return MarketData.model_validate_json(cached_data)
                except Exception:
                    legacy = json.loads(cached_data)
                    legacy["commodities"] = [
                        {
                            "modal_price": 0.0,
                            "msp": None,
                            **commodity,
                        }
                        for commodity in legacy.get("commodities", [])
                    ]
                    legacy.setdefault("source", "redis_legacy")
                    return MarketData.model_validate(legacy)
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")

    # Cache miss, fetch from Data.gov.in
    api_key = settings.LIVE_MANDI_PRICES_API_KEY or settings.DATA_GOV_IN_API_KEY
    if not api_key:
        raise ValueError("LIVE_MANDI_PRICES_API_KEY is not set in environment variables.")

    logger.info(f"Fetching Market data for {state}, {resolved_market}, {commodity} from data.gov.in")
    params = {
        "api-key": api_key,
        "format": "json"
    }
    
    if state:
        params["filters[state]"] = state
    if resolved_market:
        params["filters[market]"] = resolved_market
    if commodity:
        params["filters[commodity]"] = commodity
        
    commodities_list: List[CommodityPrice] = []
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(MANDI_API_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            records = data.get("records", [])
            
            for r in records:
                crop_name = r.get("commodity")
                # Try to parse modal_price safely
                try:
                    modal_price = float(r.get("modal_price", 0))
                except (ValueError, TypeError):
                    modal_price = 0.0
                    
                # Look up MSP
                msp_info = await get_msp_trend(crop_name)
                msp_value = msp_info["current_msp"]
                
                # Calculate profitability
                prof_index = calculate_profitability_index(modal_price, msp_value)
                
                commodities_list.append(CommodityPrice(
                    commodity=crop_name,
                    modal_price=modal_price,
                    msp=msp_value,
                    profitability_index=prof_index,
                    historical_trend_percent=msp_info["growth_trend"]
                ))
                
            market_response = MarketData(
                state=state,
                market=resolved_market or market,
                commodities=commodities_list,
                source="data_gov"
            )
            
            # Store in cache with 6-hour expiration
            if redis_client and len(records) > 0:
                await redis_client.setex(cache_key, 21600, market_response.model_dump_json())
                
            return market_response
            
    except Exception as e:
        logger.error(f"Failed to fetch Market data: {e}")
        raise e
