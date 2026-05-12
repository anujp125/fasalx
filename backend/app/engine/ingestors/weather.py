import httpx
import json
import logging
from datetime import datetime, timedelta
import asyncio
from app.db.redis import get_redis
from app.engine.models.ingestion import WeatherData
from app.models.agronomy import WeatherResponse

logger = logging.getLogger(__name__)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

async def get_weather_data(lat: float, lon: float) -> WeatherData:
    """
    Fetches hyper-local current weather and 12-month historical rainfall from Open-Meteo.
    Calculates Growing Degree Days (GDD) with a base temperature of 10°C.
    Uses Redis caching to avoid hitting rate limits.
    """
    redis_client = get_redis()
    cache_key = f"weather_ingest:{round(lat, 2)}:{round(lon, 2)}"
    
    # Try to fetch from cache first
    if redis_client:
        try:
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for weather at {lat}, {lon}")
                try:
                    return WeatherData.model_validate_json(cached_data)
                except Exception:
                    legacy = json.loads(cached_data)
                    if "temperature" in legacy:
                        temp = float(legacy.get("temperature") or 0.0)
                        return WeatherData(
                            temperature_min=temp,
                            temperature_max=temp,
                            humidity=float(legacy.get("humidity") or 0.0),
                            rainfall_current=float(legacy.get("precipitation") or 0.0),
                            rainfall_history_12m=0.0,
                            gdd=max(0.0, temp - 10.0),
                            description=legacy.get("description") or "Cached weather",
                        )
                    raise
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")

    logger.info(f"Fetching weather from Open-Meteo for {lat}, {lon}")
    
    # Calculate dates for 12-month historical data
    end_date = datetime.now() - timedelta(days=5) # Archive data usually has a few days lag
    start_date = end_date - timedelta(days=365)
    
    # Concurrent fetch for forecast and archive
    async def fetch_forecast():
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "precipitation", "weather_code"],
            "daily": ["temperature_2m_max", "temperature_2m_min"],
            "timezone": "auto"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(OPEN_METEO_FORECAST_URL, params=params, timeout=10.0)
            response.raise_for_status()
            return response.json()
            
    async def fetch_history():
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "daily": ["precipitation_sum"],
            "timezone": "auto"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=15.0)
            if response.status_code != 200:
                logger.warning(f"Archive API returned {response.status_code}: {response.text}")
                return {"daily": {"precipitation_sum": []}}
            return response.json()

    try:
        forecast_data, history_data = await asyncio.gather(fetch_forecast(), fetch_history())
    except Exception as e:
        logger.error(f"Failed to fetch weather data: {e}")
        raise e
        
    current = forecast_data.get("current", {})
    daily_forecast = forecast_data.get("daily", {})
    
    # Calculate historical rainfall sum
    hist_precip_list = history_data.get("daily", {}).get("precipitation_sum", [])
    # Filter out None values which can occur in Open-Meteo archive
    valid_precips = [p for p in hist_precip_list if p is not None]
    rainfall_12m = sum(valid_precips)
    
    # Calculate GDD for current day (Tmax + Tmin)/2 - Tbase (10)
    tmax = daily_forecast.get("temperature_2m_max", [current.get("temperature_2m", 0)])[0]
    tmin = daily_forecast.get("temperature_2m_min", [current.get("temperature_2m", 0)])[0]
    
    # Safely handle missing values
    tmax = tmax if tmax is not None else current.get("temperature_2m", 0.0)
    tmin = tmin if tmin is not None else current.get("temperature_2m", 0.0)
    
    tbase = 10.0
    gdd = max(0.0, ((tmax + tmin) / 2.0) - tbase)
    
    # Very basic weather code mapping
    weather_code = current.get("weather_code", 0)
    description = "Clear" if weather_code == 0 else "Cloudy/Rainy"
    
    weather_response = WeatherData(
        temperature_min=tmin,
        temperature_max=tmax,
        humidity=current.get("relative_humidity_2m", 0.0),
        rainfall_current=current.get("precipitation", 0.0),
        rainfall_history_12m=rainfall_12m,
        gdd=round(gdd, 2),
        description=description
    )
    
    # Store in cache with 6-hour expiration (21600 seconds)
    if redis_client:
        try:
            await redis_client.setex(cache_key, 21600, weather_response.model_dump_json())
        except Exception as e:
            logger.warning(f"Failed to set Redis cache: {e}")
            
    return weather_response


async def get_weather_forecast(lat: float, lon: float) -> WeatherResponse:
    """
    Compatibility wrapper for the agronomy endpoint.
    The recommendation ingestor keeps the richer WeatherData schema, while
    /agronomy/weather exposes the legacy compact WeatherResponse shape.
    """
    weather = await get_weather_data(lat, lon)
    return WeatherResponse(
        temperature=round((weather.temperature_min + weather.temperature_max) / 2.0, 2),
        humidity=weather.humidity,
        precipitation=weather.rainfall_current,
        description=weather.description or "Current weather"
    )
