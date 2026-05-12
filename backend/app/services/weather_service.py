import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel
import httpx

from app.db.redis import get_redis

logger = logging.getLogger(__name__)

class WeatherData(BaseModel):
    temperature_min: float
    temperature_max: float
    rainfall_history_12m: float
    gdd_cumulative: float
    monsoon_intensity: str  # e.g., "Normal", "Deficient", "Excess"
    last_updated: datetime

class WeatherService:
    def __init__(self):
        self.archive_url = "https://archive-api.open-meteo.com/v1/archive"
        self.base_temp_gdd = 10.0

    def _determine_monsoon_intensity(self, monsoon_rainfall: float) -> str:
        """
        Determines monsoon intensity based on cumulative rainfall.
        Using central Indian averages as a baseline heuristic:
        Normal: 600mm - 1000mm
        Excess: > 1000mm
        Deficient: < 600mm
        """
        if monsoon_rainfall > 1000:
            return "Excess"
        elif monsoon_rainfall < 600:
            return "Deficient"
        return "Normal"

    async def get_historical_weather(self, lat: float, lon: float) -> WeatherData:
        redis_client = get_redis()
        # Create a cache key rounded to 2 decimals (~1.1 km precision) to normalize nearby calls
        cache_key = f"weather_history:{round(lat, 2)}:{round(lon, 2)}"

        if redis_client:
            try:
                cached_data = await redis_client.get(cache_key)
                if cached_data:
                    logger.info(f"Cache hit for weather history at {lat}, {lon}")
                    return WeatherData.model_validate_json(cached_data)
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")

        logger.info(f"Fetching historical weather from Open-Meteo for {lat}, {lon}")

        # Open-Meteo Archive data usually has a few days lag, so we start from 5 days ago
        end_date = datetime.now() - timedelta(days=5)
        start_date = end_date - timedelta(days=365)

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
            "timezone": "auto"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.archive_url, params=params, timeout=15.0)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching Open-Meteo archive data: {e.response.status_code}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error fetching Open-Meteo archive data: {e}")
                raise

        daily_data = data.get("daily", {})
        times = daily_data.get("time", [])
        tmax_list = daily_data.get("temperature_2m_max", [])
        tmin_list = daily_data.get("temperature_2m_min", [])
        precip_list = daily_data.get("precipitation_sum", [])

        if not times or not tmax_list or not tmin_list or not precip_list:
            raise ValueError("Incomplete data received from Open-Meteo")

        gdd_cumulative = 0.0
        rainfall_12m = 0.0
        monsoon_rainfall = 0.0

        # Calculate metrics
        for i, date_str in enumerate(times):
            # Rainfall processing
            precip = precip_list[i]
            if precip is not None:
                rainfall_12m += precip
                
                # Check if date falls in Monsoon window (June 1st to Sept 30th)
                # Date format is "YYYY-MM-DD"
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                if 6 <= dt.month <= 9:
                    monsoon_rainfall += precip

            # GDD processing
            tmax = tmax_list[i]
            tmin = tmin_list[i]
            if tmax is not None and tmin is not None:
                gdd = max(0.0, ((tmax + tmin) / 2.0) - self.base_temp_gdd)
                gdd_cumulative += gdd

        # For the current temperature, take the most recent valid readings
        latest_tmin = next((t for t in reversed(tmin_list) if t is not None), 0.0)
        latest_tmax = next((t for t in reversed(tmax_list) if t is not None), 0.0)

        weather_response = WeatherData(
            temperature_min=latest_tmin,
            temperature_max=latest_tmax,
            rainfall_history_12m=round(rainfall_12m, 2),
            gdd_cumulative=round(gdd_cumulative, 2),
            monsoon_intensity=self._determine_monsoon_intensity(monsoon_rainfall),
            last_updated=datetime.now(timezone.utc)
        )

        if redis_client:
            try:
                # Cache for 7 days (7 * 24 * 60 * 60 seconds = 604800)
                await redis_client.setex(cache_key, 604800, weather_response.model_dump_json())
            except Exception as e:
                logger.warning(f"Failed to set Redis cache: {e}")

        return weather_response

# Singleton instance
weather_service = WeatherService()
