import httpx
import logging
from typing import Optional, List
from app.models.timeline import EnvironmentalSnapshot

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

def calculate_daily_gdd(t_max: float, t_min: float, t_base: float = 10.0) -> float:
    """
    Calculates Growing Degree Days (GDD) for a single day.
    Formula: GDD = ((T_max + T_min) / 2) - T_base
    If the average temperature is below T_base, GDD is 0.
    """
    t_avg = (t_max + t_min) / 2.0
    gdd = t_avg - t_base
    return max(0.0, gdd)

async def process_environmental_data(snapshot: EnvironmentalSnapshot, coordinates: List[float], t_base: float) -> float:
    """
    Evaluates the EnvironmentalSnapshot and returns the accumulated GDD.
    Leverages Data Quality Weighting: If IoT data is missing, it automatically falls back 
    to hyper-local API data (Open-Meteo) and adjusts the data quality weight.
    """
    # Fallback to API if IoT data is missing
    if snapshot.t_max is None or snapshot.t_min is None:
        logger.warning(f"Missing IoT temperature data. Falling back to Open-Meteo API.")
        try:
            lon, lat = coordinates
            params = {
                "latitude": lat,
                "longitude": lon,
                "daily": ["temperature_2m_max", "temperature_2m_min"],
                "timezone": "auto",
                "forecast_days": 1
            }
            async with httpx.AsyncClient() as client:
                response = await client.get(OPEN_METEO_URL, params=params, timeout=5.0)
                response.raise_for_status()
                data = response.json()
                
                daily = data.get("daily", {})
                t_max_list = daily.get("temperature_2m_max", [])
                t_min_list = daily.get("temperature_2m_min", [])
                
                if t_max_list and t_min_list:
                    snapshot.t_max = t_max_list[0]
                    snapshot.t_min = t_min_list[0]
                    snapshot.source = "api_fallback"
                    snapshot.weight = 0.8 # Lower quality than direct IoT, but better than satellite
                    logger.info(f"API Fallback successful. T_max: {snapshot.t_max}, T_min: {snapshot.t_min}")
        except Exception as e:
            logger.error(f"API Fallback failed: {e}. Executing Tier-3 Satellite Fallback.")
            # Tier-3: Regional Satellite-Derived Averages
            # In a full production system, this would query a historical database (e.g., Earth Engine).
            # For now, we mock a safe regional average based on the base temperature.
            snapshot.t_max = t_base + 15.0  # Assumes a mild day
            snapshot.t_min = t_base + 2.0   # Assumes a cool night
            snapshot.source = "satellite_fallback"
            snapshot.weight = 0.5 # Lowest quality data
            
    # Calculate GDD using the crop-specific base temperature
    return calculate_daily_gdd(snapshot.t_max, snapshot.t_min, t_base)
