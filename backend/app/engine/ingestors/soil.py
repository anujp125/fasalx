import asyncio
import logging
import httpx
from typing import Optional
from app.engine.models.ingestion import SoilData

logger = logging.getLogger(__name__)

async def fetch_isric_soil_data(lat: float, lon: float) -> Optional[dict]:
    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    try:
        async with httpx.AsyncClient() as client:
            query_str = f"?lon={lon}&lat={lat}&property=nitrogen&property=phh2o&property=soc"
            response = await client.get(url + query_str, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            result = {}
            for layer in data.get("properties", {}).get("layers", []):
                name = layer.get("name")
                depths = layer.get("depths", [])
                if not depths:
                    continue
                
                # Use the 0-5cm layer mean
                mean_val = depths[0].get("values", {}).get("mean")
                if mean_val is None:
                    continue
                    
                if name == "nitrogen":
                    # Mapped as cg/kg. 1 cg/kg = 10 ppm. kg/ha ≈ ppm * 2.24
                    result["N"] = round(mean_val * 22.4, 2)
                elif name == "phh2o":
                    # Mapped as pH*10
                    result["pH"] = round(mean_val / 10.0, 2)
                elif name == "soc":
                    # Mapped as dg/kg. dg/kg = 0.01%
                    result["OC"] = round(mean_val / 100.0, 2)
            
            return result if result else None
    except Exception as e:
        logger.error(f"ISRIC SoilGrids fetch failed: {e}")
    return None


# Core "Sharbati" belt detailed profiles
# Values are representative for demonstration
MP_DISTRICT_SOIL_AVERAGES = {
    "Bhopal": {
        "N": 220.5, "P": 18.2, "K": 280.0, "S": 12.5,
        "Zn": 0.65, "Fe": 5.2, "Cu": 1.2, "Mn": 4.5, "B": 0.45,
        "pH": 7.4, "EC": 0.35, "OC": 0.60
    },
    "Raisen": {
        "N": 215.0, "P": 16.5, "K": 295.0, "S": 11.0,
        "Zn": 0.58, "Fe": 4.8, "Cu": 1.1, "Mn": 4.2, "B": 0.42,
        "pH": 7.6, "EC": 0.32, "OC": 0.55
    },
    "Sehore": {
        "N": 230.0, "P": 19.0, "K": 310.0, "S": 13.0,
        "Zn": 0.70, "Fe": 5.5, "Cu": 1.3, "Mn": 4.8, "B": 0.50,
        "pH": 7.3, "EC": 0.30, "OC": 0.65
    },
    "Vidisha": {
        "N": 210.5, "P": 15.8, "K": 275.0, "S": 10.5,
        "Zn": 0.55, "Fe": 4.5, "Cu": 1.0, "Mn": 4.0, "B": 0.40,
        "pH": 7.5, "EC": 0.38, "OC": 0.52
    },
    # Generic "Black Soil" profile for remaining districts
    "Generic_Black_Soil": {
        "N": 200.0, "P": 15.0, "K": 250.0, "S": 10.0,
        "Zn": 0.50, "Fe": 4.0, "Cu": 0.9, "Mn": 3.8, "B": 0.35,
        "pH": 7.8, "EC": 0.40, "OC": 0.45
    }
}

REGIONAL_SOIL_AVERAGES = {
    # Western Rajasthan: sandy, alkaline, low organic matter and low available N.
    "Rajasthan": {
        "Jaisalmer": {
            "N": 120.0, "P": 12.0, "K": 175.0, "S": 8.0,
            "Zn": 0.42, "Fe": 3.2, "Cu": 0.75, "Mn": 2.7, "B": 0.30,
            "pH": 8.2, "EC": 0.75, "OC": 0.22
        }
    },
    # Marathwada black clay: moderate N, low P, high K, slightly alkaline.
    "Maharashtra": {
        "Jalna": {
            "N": 185.0, "P": 17.0, "K": 330.0, "S": 11.0,
            "Zn": 0.55, "Fe": 4.6, "Cu": 1.0, "Mn": 4.1, "B": 0.38,
            "pH": 7.8, "EC": 0.45, "OC": 0.52
        },
        "Aurangabad": {
            "N": 180.0, "P": 16.0, "K": 315.0, "S": 10.5,
            "Zn": 0.52, "Fe": 4.4, "Cu": 0.95, "Mn": 4.0, "B": 0.36,
            "pH": 7.7, "EC": 0.43, "OC": 0.50
        },
        "Chhatrapati Sambhajinagar": {
            "N": 180.0, "P": 16.0, "K": 315.0, "S": 10.5,
            "Zn": 0.52, "Fe": 4.4, "Cu": 0.95, "Mn": 4.0, "B": 0.36,
            "pH": 7.7, "EC": 0.43, "OC": 0.50
        }
    },
    # North Bihar alluvial soils: fertile, near-neutral, higher organic carbon.
    "Bihar": {
        "Purnia": {
            "N": 265.0, "P": 34.0, "K": 205.0, "S": 14.0,
            "Zn": 0.72, "Fe": 6.8, "Cu": 1.25, "Mn": 5.4, "B": 0.48,
            "pH": 6.6, "EC": 0.28, "OC": 0.82
        },
        "Purnea": {
            "N": 265.0, "P": 34.0, "K": 205.0, "S": 14.0,
            "Zn": 0.72, "Fe": 6.8, "Cu": 1.25, "Mn": 5.4, "B": 0.48,
            "pH": 6.6, "EC": 0.28, "OC": 0.82
        }
    }
}

async def fetch_soil_data(lat: float = None, lon: float = None, lgd_code: int = None, state: str = None, district: str = None) -> SoilData:
    """
    Fetches Soil Data from the global ISRIC SoilGrids REST API.
    If the coordinate is masked (e.g. urban center) or the API fails, it falls back
    to detailed static mappings or a generic profile.
    """
    
    # Clean district name if needed
    clean_district = district.replace(" District", "").strip() if district else ""
    
    # Check if we have a detailed profile for the district
    regional_profile = REGIONAL_SOIL_AVERAGES.get(state or "", {}).get(clean_district)
    if regional_profile:
        profile = regional_profile
        logger.info(f"Using regional profile for {state}/{clean_district}")
    elif clean_district in MP_DISTRICT_SOIL_AVERAGES:
        profile = MP_DISTRICT_SOIL_AVERAGES[clean_district]
        logger.info(f"Using detailed profile for {clean_district}")
    elif state == "Madhya Pradesh":
        profile = MP_DISTRICT_SOIL_AVERAGES["Generic_Black_Soil"]
        logger.info(f"Using generic black soil profile for MP district: {clean_district}")
    else:
        # If not MP, we just return the generic profile for the fallback
        profile = MP_DISTRICT_SOIL_AVERAGES["Generic_Black_Soil"].copy()
        logger.info("Using generic soil profile (out of state)")
        
    isric_data = await fetch_isric_soil_data(lat, lon) if lat is not None and lon is not None else None
    source_str = "district_average"
    
    if isric_data:
        profile["N"] = isric_data.get("N", profile["N"])
        profile["pH"] = isric_data.get("pH", profile["pH"])
        profile["OC"] = isric_data.get("OC", profile["OC"])
        source_str = "isric_hybrid"
        logger.info(f"Successfully integrated ISRIC SoilGrids data for lat:{lat}, lon:{lon}")

    return SoilData(
        N=profile["N"],
        P=profile["P"],
        K=profile["K"],
        S=profile["S"],
        Zn=profile["Zn"],
        Fe=profile["Fe"],
        Cu=profile["Cu"],
        Mn=profile["Mn"],
        B=profile["B"],
        pH=profile["pH"],
        EC=profile["EC"],
        OC=profile["OC"],
        source=source_str
    )
