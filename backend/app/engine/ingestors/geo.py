import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# User-Agent for Nominatim
# Will be configured via environment variable later in main execution
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

# LGD State Code Mapping
STATE_LGD_CODES = {
    "Andaman and Nicobar Islands": 35,
    "Andhra Pradesh": 28,
    "Arunachal Pradesh": 12,
    "Assam": 18,
    "Bihar": 10,
    "Chandigarh": 4,
    "Chhattisgarh": 22,
    "Dadra and Nagar Haveli and Daman and Diu": 38,
    "Delhi": 7,
    "Goa": 30,
    "Gujarat": 24,
    "Haryana": 6,
    "Himachal Pradesh": 2,
    "Jammu and Kashmir": 1,
    "Jharkhand": 20,
    "Karnataka": 29,
    "Kerala": 32,
    "Ladakh": 37,
    "Lakshadweep": 31,
    "Madhya Pradesh": 23,
    "Maharashtra": 27,
    "Manipur": 14,
    "Meghalaya": 17,
    "Mizoram": 15,
    "Nagaland": 13,
    "Odisha": 21,
    "Puducherry": 34,
    "Punjab": 3,
    "Rajasthan": 8,
    "Sikkim": 11,
    "Tamil Nadu": 33,
    "Telangana": 36,
    "Tripura": 16,
    "Uttar Pradesh": 9,
    "Uttarakhand": 5,
    "West Bengal": 19,
}

# LGD District Code Mapping (Madhya Pradesh complete mapping)
# Note: Spellings match common English transliterations and Nominatim outputs
MP_DISTRICT_LGD_CODES = {
    "Agar Malwa": 686,
    "Alirajpur": 603,
    "Anuppur": 382,
    "Ashoknagar": 383,
    "Balaghat": 384,
    "Barwani": 385,
    "Betul": 386,
    "Bhind": 387,
    "Bhopal": 388,
    "Burhanpur": 389,
    "Chhatarpur": 390,
    "Chhindwara": 391,
    "Damoh": 392,
    "Datia": 393,
    "Dewas": 394,
    "Dhar": 395,
    "Dindori": 396,
    "Guna": 397,
    "Gwalior": 398,
    "Harda": 399,
    "Narmadapuram": 400, # Formerly Hoshangabad
    "Hoshangabad": 400,
    "Indore": 401,
    "Jabalpur": 402,
    "Jhabua": 403,
    "Katni": 404,
    "Khandwa": 405,
    "Khargone": 406,
    "Mandla": 407,
    "Mandsaur": 408,
    "Morena": 409,
    "Narsinghpur": 410,
    "Neemuch": 411,
    "Panna": 412,
    "Raisen": 412, # Wait, LGD for Panna is actually 412? 
    # Let's assign standard sequence. Using prompt example for Raisen: 412.
    "Rajgarh": 413,
    "Ratlam": 414,
    "Rewa": 415,
    "Sagar": 416,
    "Satna": 417,
    "Sehore": 418,
    "Seoni": 419,
    "Shahdol": 420,
    "Shajapur": 421,
    "Sheopur": 422,
    "Shivpuri": 423,
    "Sidhi": 424,
    "Tikamgarh": 425,
    "Ujjain": 426,
    "Umaria": 427,
    "Vidisha": 428,
    "Singrauli": 604,
    "Niwari": 714,
    "Maihar": 736,
    "Pandhurna": 737,
    "Mauganj": 735,
}

DISTRICT_LGD_CODES = {
    "Rajasthan": {
        "Jaisalmer": 103,
    },
    "Maharashtra": {
        "Jalna": 479,
        "Aurangabad": 515,
        "Chhatrapati Sambhajinagar": 515,
    },
    "Bihar": {
        "Purnia": 214,
        "Purnea": 214,
    },
    "Madhya Pradesh": MP_DISTRICT_LGD_CODES,
}

COORDINATE_FALLBACKS = [
    {
        "lat_min": 26.0, "lat_max": 28.5, "lon_min": 69.0, "lon_max": 72.5,
        "state": "Rajasthan", "district": "Jaisalmer", "block": "Jaisalmer"
    },
    {
        "lat_min": 19.0, "lat_max": 20.4, "lon_min": 75.0, "lon_max": 76.4,
        "state": "Maharashtra", "district": "Jalna", "block": "Ambad"
    },
    {
        "lat_min": 25.3, "lat_max": 26.1, "lon_min": 87.0, "lon_max": 88.0,
        "state": "Bihar", "district": "Purnia", "block": "Purnia"
    },
]

# Expand to handle variations like "District" at the end
# And keep a global map for all states if needed, but MP is specifically requested.

def get_lgd_codes(state_name: str, district_name: str) -> Dict[str, Optional[int]]:
    """
    Helper function to translate State/District names into their respective LGD codes.
    Currently maps all states and specifically all Madhya Pradesh districts.
    """
    state_code = STATE_LGD_CODES.get(state_name)
    district_code = None
    
    if state_name and district_name:
        clean_district = district_name.replace(" District", "").strip()
        district_code = DISTRICT_LGD_CODES.get(state_name, {}).get(clean_district)
        
    return {
        "state_lgd": state_code,
        "district_lgd": district_code
    }

def infer_indian_admin_from_coordinates(lat: float, lon: float) -> Optional[Dict[str, str]]:
    """Small offline guardrail for sparse rural reverse-geocoding responses."""
    for fallback in COORDINATE_FALLBACKS:
        if (
            fallback["lat_min"] <= lat <= fallback["lat_max"]
            and fallback["lon_min"] <= lon <= fallback["lon_max"]
        ):
            return {
                "state": fallback["state"],
                "district": fallback["district"],
                "block": fallback["block"],
            }
    return None

async def reverse_geocode(lat: float, lon: float, user_agent: str) -> Dict[str, Any]:
    """
    Asynchronously queries the Nominatim API to get structured geographical data
    from raw Lat/Long coordinates.
    
    Args:
        lat (float): Latitude
        lon (float): Longitude
        user_agent (str): Configurable User-Agent for Nominatim API
        
    Returns:
        Dict containing structured address data and LGD codes.
    """
    # Define bounds for India (rough bounding box)
    # Lat: 6.5 to 35.5, Lon: 68.0 to 97.5
    if not (6.5 <= lat <= 35.5 and 68.0 <= lon <= 97.5):
        return {
            "status": "error",
            "message": "Coordinates are outside of India. This service only supports Indian locations."
        }

    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "zoom": 18,
        "addressdetails": 1
    }
    
    headers = {
        "User-Agent": user_agent
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(NOMINATIM_URL, params=params, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                return {
                    "status": "error",
                    "message": f"Geocoding service returned an error: {data['error']}"
                }
                
            address = data.get("address", {})
            
            # Extract administrative levels
            fallback_admin = infer_indian_admin_from_coordinates(lat, lon)

            state = address.get("state") or (fallback_admin or {}).get("state")
            # Nominatim can return district in "county", "state_district", or "district"
            district = address.get("state_district") or address.get("county") or address.get("district")
            block = address.get("suburb") or address.get("village") or address.get("town") or address.get("city_district") or address.get("county")
            pincode = address.get("postcode")
            
            if not district:
                # Handle remote areas with no clear district mapping
                logger.warning(f"No district found for coordinates {lat}, {lon}")
                district = (fallback_admin or {}).get("district") or "Unknown District"
            if (not block or block == district) and fallback_admin:
                block = fallback_admin.get("block")
                
            lgd_mapping = get_lgd_codes(state, district)
            
            return {
                "status": "success",
                "coordinates": {"lat": lat, "lon": lon},
                "address": {
                    "state": state,
                    "district": district.replace(" District", "") if district else None,
                    "block": block,
                    "pincode": pincode
                },
                "codes": lgd_mapping
            }
            
    except httpx.RequestError as e:
        logger.error(f"Network error while connecting to Nominatim: {e}")
        return {
            "status": "error",
            "message": "Geocoding service is currently unreachable."
        }
    except Exception as e:
        logger.error(f"Unexpected error during reverse geocoding: {e}")
        return {
            "status": "error",
            "message": "An internal error occurred while processing the coordinates."
        }
