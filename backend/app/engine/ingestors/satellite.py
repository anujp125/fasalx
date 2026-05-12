import logging
import time
from typing import Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Token Cache ──────────────────────────────────────────────────────────────
# Sentinel Hub tokens last ~3600s. We cache locally to avoid a token request
# on every field intelligence call.  Thread-safe enough for async single-process.
_token_cache: dict = {"access_token": None, "expires_at": 0.0}

SENTINEL_AUTH_URL = "https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token"
SENTINEL_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"

# ── Fallback: climate-zone-aware regional estimate ───────────────────────────
def _climate_moisture_band(lat: float, lon: float) -> tuple[float, float]:
    if 26.0 <= lat <= 28.5 and 69.0 <= lon <= 72.5:
        return 0.10, 0.20  # Thar/Jaisalmer arid belt
    if 19.0 <= lat <= 20.4 and 75.0 <= lon <= 76.4:
        return 0.32, 0.56  # Marathwada medium black-soil belt
    if 25.3 <= lat <= 26.1 and 87.0 <= lon <= 88.0:
        return 0.55, 0.82  # North Bihar alluvial/high-rainfall belt
    return 0.30, 0.65      # Generic Indian farm belt


def _mock_fallback(lat: float, lon: float) -> dict:
    """Deterministic regional estimate used when Sentinel Hub is unavailable."""
    m_min, m_max = _climate_moisture_band(lat, lon)
    import hashlib
    seed = int(hashlib.md5(f"{round(lat, 4)}:{round(lon, 4)}".encode()).hexdigest(), 16)
    ndvi = round(0.25 + ((seed % 100) / 100.0) * 0.55, 2)   # 0.25–0.80
    moist = round(m_min + (((seed // 100) % 100) / 100.0) * (m_max - m_min), 2)
    return {"ndvi": ndvi, "soil_moisture": moist, "source": "mock_regional_estimate"}


# ── Sentinel Hub helpers ──────────────────────────────────────────────────────
async def _get_sentinel_token() -> Optional[str]:
    """Obtains and caches a Sentinel Hub OAuth2 Bearer token."""
    client_id = settings.SENTINEL_HUB_CLIENT_ID
    client_secret = settings.SENTINEL_HUB_CLIENT_SECRET

    if not client_id or not client_secret:
        logger.warning("Sentinel Hub credentials not configured in .env")
        return None

    # Return cached token if still valid (with 60s buffer)
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SENTINEL_AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )
            resp.raise_for_status()
            token_data = resp.json()
            _token_cache["access_token"] = token_data["access_token"]
            _token_cache["expires_at"] = time.time() + token_data.get("expires_in", 3600)
            logger.info("Sentinel Hub access token refreshed.")
            return _token_cache["access_token"]
    except Exception as e:
        logger.error(f"Sentinel Hub token request failed: {e}")
        return None


async def _fetch_sentinel_band_value(
    lat: float, lon: float, token: str, evalscript: str
) -> Optional[float]:
    """
    Sends a statistical evaluation request to Sentinel Hub Process API
    and returns the mean value of the single output band.
    Uses a 1km bounding box around the point and last 30 days of Sentinel-2 imagery.
    """
    # 1km bounding box (~0.009 degrees per km)
    delta = 0.005
    bbox = [lon - delta, lat - delta, lon + delta, lat + delta]

    import datetime
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=30)).isoformat()
    to_date = today.isoformat()

    payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": f"{from_date}T00:00:00Z", "to": f"{to_date}T23:59:59Z"},
                        "maxCloudCoverage": 30,
                    },
                }
            ],
        },
        "evalscript": evalscript,
        "output": {
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]
        },
    }

    # Use statistical API for scalar value (mean over the bounding box)
    stats_payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": f"{from_date}T00:00:00Z", "to": f"{to_date}T23:59:59Z"},
                        "maxCloudCoverage": 30,
                    },
                }
            ],
        },
        "aggregation": {
            "timeRange": {"from": f"{from_date}T00:00:00Z", "to": f"{to_date}T23:59:59Z"},
            "aggregationInterval": {"of": "P30D"},
            "evalscript": evalscript,
            "resx": 10,
            "resy": 10,
        },
        # Statistics API: calculate stats only on B0 (the index), use B1 (dataMask) for exclusion
        "calculations": {
            "default": {
                "histogramBins": None,
                "statistics": {
                    "default": {
                        "percentiles": {"k": [50]},
                        "noDataPixels": False,
                    }
                },
            }
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://services.sentinel-hub.com/api/v1/statistics",
                json=stats_payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
            intervals = data.get("data", [])
            if intervals:
                outputs = intervals[0].get("outputs", {})
                # The output key matches the evalscript output id ("ndvi" or "ndwi")
                # Fall back to "default" for backwards compat
                index_output = outputs.get("ndvi") or outputs.get("ndwi") or outputs.get("default", {})
                bands = index_output.get("bands", {})
                b0 = bands.get("B0", {})
                stats = b0.get("stats", {})
                mean_val = stats.get("mean")
                if mean_val is not None and str(mean_val).lower() not in ("nan", "none"):
                    return float(mean_val)
    except Exception as e:
        logger.warning(f"Sentinel Hub statistics request failed: {e}")
    return None


# ── Evalscripts ───────────────────────────────────────────────────────────────
# Sentinel Hub Statistics API requires dataMask declared as a SEPARATE named output.
_NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "dataMask"],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(sample) {
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 0.0001);
  return {
    ndvi: [ndvi],
    dataMask: [sample.dataMask]
  };
}
"""

# NDWI (Normalized Difference Water Index) used as a soil moisture proxy
_NDWI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B08", "B11", "dataMask"],
    output: [
      { id: "ndwi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(sample) {
  let ndwi = (sample.B08 - sample.B11) / (sample.B08 + sample.B11 + 0.0001);
  return {
    ndwi: [ndwi],
    dataMask: [sample.dataMask]
  };
}
"""


def _scale_ndwi_to_moisture(ndwi: float) -> float:
    """
    NDWI ranges roughly from -1 to +1.
    Typical dry soil: -0.5 to -0.2. Wet soil / vegetation: 0.0 to +0.5.
    We map [-0.6, +0.6] → [0.0, 1.0] for the moisture score.
    """
    scaled = (ndwi + 0.6) / 1.2
    return round(max(0.0, min(1.0, scaled)), 2)


# ── Public API ────────────────────────────────────────────────────────────────
async def get_field_health(lat: float, lon: float) -> dict:
    """
    Fetches real satellite imagery intelligence (NDVI, Soil Moisture proxy via NDWI)
    from the Sentinel Hub Statistics API using Sentinel-2 L2A imagery.

    Falls back to a deterministic regional estimate if credentials are missing or
    the API request fails (e.g. excessive cloud cover, no images in 30-day window).
    """
    token = await _get_sentinel_token()
    if not token:
        logger.info("Using mock satellite fallback (no Sentinel Hub token)")
        return _mock_fallback(lat, lon)

    # Fetch both indices concurrently
    import asyncio
    ndvi_raw, ndwi_raw = await asyncio.gather(
        _fetch_sentinel_band_value(lat, lon, token, _NDVI_EVALSCRIPT),
        _fetch_sentinel_band_value(lat, lon, token, _NDWI_EVALSCRIPT),
    )

    fallback = _mock_fallback(lat, lon)

    ndvi = round(max(-1.0, min(1.0, ndvi_raw)), 2) if ndvi_raw is not None else fallback["ndvi"]
    moisture = _scale_ndwi_to_moisture(ndwi_raw) if ndwi_raw is not None else fallback["soil_moisture"]
    source = "sentinel_hub_live" if (ndvi_raw is not None or ndwi_raw is not None) else "mock_regional_estimate"

    logger.info(f"Satellite data for ({lat}, {lon}): NDVI={ndvi}, moisture={moisture}, source={source}")
    return {
        "ndvi": ndvi,
        "soil_moisture": moisture,
        "source": source,
    }
