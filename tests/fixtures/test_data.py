"""
FasalX Test Data Fixtures
=========================
Provides deterministic, realistic seed data for all modules.
Replaces all external API / sensor / Firebase dependencies with
hard-coded values so tests are 100% offline and reproducible.
"""
from datetime import datetime, timezone, timedelta

# ─── COMMON IDENTIFIERS ────────────────────────────────────────────────────────
FARMER_UID         = "test-farmer-uid-001"
ADMIN_UID          = "test-admin-uid-002"
NEIGHBOUR_UID      = "test-neighbour-uid-003"   # for geo-trend neighbour farm
CROP_ID            = "wheat-rabi-2024"
DEVICE_ID          = "iot-sensor-farm-a-01"

# ─── FIREBASE / AUTH ───────────────────────────────────────────────────────────
MOCK_FIREBASE_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.MOCK_PAYLOAD.MOCK_SIGNATURE"

MOCK_DECODED_TOKEN = {
    "uid":            FARMER_UID,
    "email":          "kisan.ramesh@example.com",
    "name":           "Ramesh Kumar",
    "email_verified": True,
    "phone_number":   "+919876543210",
}

MOCK_ADMIN_TOKEN = {
    "uid":            ADMIN_UID,
    "email":          "admin@fasalx.com",
    "name":           "FasalX Admin",
    "email_verified": True,
}

# ─── FARMER PROFILE (MongoDB document) ─────────────────────────────────────────
FARMER_PROFILE_DOC = {
    "_id":              FARMER_UID,
    "display_name":     "Ramesh Kumar",
    "role":             "farmer",
    "is_active":        True,
    "preferred_language": "hi",
    "phone_number":     "+919876543210",
    "farm_size_acres":  12.5,
    "location": {
        "latitude":  28.6139,
        "longitude": 77.2090,
    },
    "state":   "Delhi",
    "market":  "Azadpur",
    "created_at": "2024-11-01T06:00:00+00:00",
    "updated_at": "2024-11-01T06:00:00+00:00",
}

# FarmerProfile update payload (matches app.models.user.FarmerProfile)
FARMER_PROFILE_UPDATE_PAYLOAD = {
    "display_name":       "Ramesh Kumar (Updated)",
    "preferred_language": "hi",
    "farm_size_acres":    15.0,
    "role":               "farmer",
    "location": {"latitude": 28.6139, "longitude": 77.2090},
}

# ─── IoT TELEMETRY ─────────────────────────────────────────────────────────────
IOT_PAYLOAD_VALID = {
    "device_id":   DEVICE_ID,
    "moisture":    42.5,
    "temperature": 22.3,
    "ph":          6.8,
    "nitrogen":    35.0,
    "phosphorus":  18.0,
    "potassium":   120.0,
    # timestamp intentionally omitted → server should inject it
}

IOT_PAYLOAD_NO_OPTIONALS = {
    "device_id":   DEVICE_ID,
    "moisture":    55.0,
    "temperature": 18.0,
}

IOT_PAYLOAD_BOUNDARY_HIGH = {
    "device_id":   DEVICE_ID,
    "moisture":    100.0,
    "temperature": 59.9,
    "ph":          14.0,
}

IOT_PAYLOAD_INVALID_MOISTURE = {
    "device_id":   DEVICE_ID,
    "moisture":    150.0,   # out of range ── should fail Pydantic validation
    "temperature": 20.0,
}

IOT_PAYLOAD_INVALID_PH = {
    "device_id":   DEVICE_ID,
    "moisture":    40.0,
    "temperature": 20.0,
    "ph":          -1.0,    # out of range ── should fail
}

# ─── WEATHER API (Open-Meteo response stub) ────────────────────────────────────
MOCK_OPEN_METEO_RESPONSE = {
    "latitude":  28.6,
    "longitude": 77.2,
    "current": {
        "temperature_2m":        24.5,
        "relative_humidity_2m":  65.0,
        "precipitation":          0.0,
        "weather_code":           0,       # Clear sky
    }
}

MOCK_OPEN_METEO_RAINY = {
    "latitude":  28.6,
    "longitude": 77.2,
    "current": {
        "temperature_2m":        18.0,
        "relative_humidity_2m":  90.0,
        "precipitation":         12.5,
        "weather_code":           80,      # Rain showers
    }
}

# Open-Meteo daily stub (used by GDD engine fallback)
MOCK_OPEN_METEO_DAILY_RESPONSE = {
    "daily": {
        "temperature_2m_max": [32.0],
        "temperature_2m_min": [18.0],
    }
}

# ─── MANDI PRICES (data.gov.in response stub) ──────────────────────────────────
MOCK_MANDI_API_RESPONSE = {
    "records": [
        {
            "commodity":    "Wheat",
            "variety":      "Sharbati",
            "min_price":    "2050",
            "max_price":    "2250",
            "modal_price":  "2150",
            "arrival_date": "02/05/2025",
            "state":        "Delhi",
            "market":       "Azadpur",
        },
        {
            "commodity":    "Rice",
            "variety":      "Basmati",
            "min_price":    "3200",
            "max_price":    "3800",
            "modal_price":  "3500",
            "arrival_date": "02/05/2025",
            "state":        "Delhi",
            "market":       "Azadpur",
        },
    ]
}

MOCK_MANDI_FORMATTED_RESPONSE = {
    "state":  "Delhi",
    "market": "Azadpur",
    "commodities": [
        {
            "commodity":   "Wheat",
            "variety":     "Sharbati",
            "min_price":   "2050",
            "max_price":   "2250",
            "modal_price": "2150",
            "arrival_date":"02/05/2025",
        },
        {
            "commodity":   "Rice",
            "variety":     "Basmati",
            "min_price":   "3200",
            "max_price":   "3800",
            "modal_price": "3500",
            "arrival_date":"02/05/2025",
        },
    ],
    "location_source": "explicit",
}

# ─── IP GEOLOCATION (ip-api.com response stub) ─────────────────────────────────
MOCK_IP_GEO_RESPONSE = {
    "status":     "success",
    "lat":        28.6139,
    "lon":        77.2090,
    "regionName": "Delhi",
    "city":       "Azadpur",
}

# ─── CROP TEMPLATE ─────────────────────────────────────────────────────────────
CROP_TEMPLATE_WHEAT = {
    "crop_name":           "Wheat",
    "variety":             "HD-2967",
    "total_duration_days": 120,
    "stages": [
        {"name": "Sowing",      "duration_days": 5,  "instructions": "Sow seeds 4–5 cm deep at 22°C."},
        {"name": "Germination", "duration_days": 10, "instructions": "Ensure moisture at 60% field capacity."},
        {"name": "Tillering",   "duration_days": 25, "instructions": "Apply first dose of Nitrogen (60 kg/ha)."},
        {"name": "Heading",     "duration_days": 30, "instructions": "Irrigate at boot stage."},
        {"name": "Maturity",    "duration_days": 20, "instructions": "Stop irrigation 10 days before harvest."},
        {"name": "Harvest",     "duration_days": 30, "instructions": "Harvest at 14% grain moisture."},
    ],
}

CROP_TEMPLATE_RICE = {
    "crop_name":           "Rice",
    "variety":             "Pusa Basmati 1121",
    "total_duration_days": 140,
    "stages": [
        {"name": "Nursery",     "duration_days": 25, "instructions": "Maintain 2–3 cm water in nursery."},
        {"name": "Transplanting","duration_days":10, "instructions": "Transplant at 21-day-old seedlings."},
        {"name": "Vegetative",  "duration_days": 45, "instructions": "Apply Urea in 3 splits."},
        {"name": "Reproductive","duration_days": 30, "instructions": "Ensure water at panicle initiation."},
        {"name": "Ripening",    "duration_days": 30, "instructions": "Drain field 10 days before harvest."},
    ],
}

# ─── TIMELINE (UserCropTimeline document) ──────────────────────────────────────
SOWING_DATE = datetime(2024, 11, 1, 6, 0, 0, tzinfo=timezone.utc)

TIMELINE_DOC = {
    "user_metadata": {
        "user_id":    FARMER_UID,
        "crop_id":    CROP_ID,
        "sowing_date": SOWING_DATE.isoformat(),
        "location": {
            "type":        "Point",
            "coordinates": [77.2090, 28.6139],   # [lon, lat]
        },
        "t_base": 10.0,
    },
    "lifecycle_state": {
        "current_stage":       "Sowing",
        "progress_percentage": 0.0,
        "total_gdd":           0.0,
    },
    "milestone_map": [
        {
            "name":             "Germination",
            "type":             "macro",
            "status":           "predicted",
            "target_gdd":       100.0,
            "predicted_date":   (SOWING_DATE + timedelta(days=10)).isoformat(),
            "confidence_score": 1.0,
        },
        {
            "name":             "Tillering",
            "type":             "macro",
            "status":           "predicted",
            "target_gdd":       350.0,
            "predicted_date":   (SOWING_DATE + timedelta(days=35)).isoformat(),
            "confidence_score": 1.0,
        },
        {
            "name":             "Heading",
            "type":             "macro",
            "status":           "predicted",
            "target_gdd":       700.0,
            "predicted_date":   (SOWING_DATE + timedelta(days=65)).isoformat(),
            "confidence_score": 1.0,
        },
        {
            "name":             "Maturity",
            "type":             "macro",
            "status":           "predicted",
            "target_gdd":       1100.0,
            "predicted_date":   (SOWING_DATE + timedelta(days=100)).isoformat(),
            "confidence_score": 1.0,
        },
        {
            "name":             "Harvest",
            "type":             "macro",
            "status":           "predicted",
            "target_gdd":       1500.0,
            "predicted_date":   (SOWING_DATE + timedelta(days=120)).isoformat(),
            "confidence_score": 1.0,
        },
        {
            "name":          "Soil Moisture Alert",
            "type":          "micro",
            "status":        "predicted",
            "trigger_logic": "soil_moisture < 20",
            "confidence_score": 1.0,
        },
    ],
    "environmental_snapshot": {
        "last_updated":  datetime.now(timezone.utc).isoformat(),
        "t_max":         30.0,
        "t_min":         15.0,
        "soil_moisture": 45.0,
        "source":        "iot",
        "weight":        1.0,
    },
}

# Timeline after significant GDD accumulation (past Germination)
TIMELINE_DOC_ADVANCED = {
    **TIMELINE_DOC,
    "lifecycle_state": {
        "current_stage":       "Tillering",
        "progress_percentage": 30.0,
        "total_gdd":           450.0,
    },
}

# Neighbour farm with pest alert (for geo-trend tests)
NEIGHBOUR_TIMELINE_DOC = {
    "user_metadata": {
        "user_id":    NEIGHBOUR_UID,
        "crop_id":    "wheat-rabi-2024-neighbour",
        "sowing_date": SOWING_DATE.isoformat(),
        "location": {
            "type":        "Point",
            "coordinates": [77.2200, 28.6200],   # ~2 km away
        },
        "t_base": 10.0,
    },
    "lifecycle_state": {
        "current_stage":       "Tillering",
        "progress_percentage": 28.0,
        "total_gdd":           420.0,
    },
    "milestone_map": [
        {
            "name":          "Pest Blight Alert",
            "type":          "micro",
            "status":        "alert",
            "trigger_logic": "geo-trend",
            "confidence_score": 0.8,
        },
    ],
    "environmental_snapshot": {
        "last_updated":  datetime.now(timezone.utc).isoformat(),
        "t_max":         29.0,
        "t_min":         14.0,
        "soil_moisture": 38.0,
        "source":        "api_fallback",
        "weight":        0.8,
    },
}

# ─── USER ACTIVITIES (MongoDB documents) ────────────────────────────────────────
MOCK_ACTIVITIES = [
    {"_id": "act-001", "user_id": FARMER_UID, "action": "LOGIN",          "timestamp": "2024-11-01T06:00:00+00:00"},
    {"_id": "act-002", "user_id": FARMER_UID, "action": "PROFILE_UPDATE", "timestamp": "2024-11-01T07:30:00+00:00"},
    {"_id": "act-003", "user_id": FARMER_UID, "action": "LOGOUT",         "timestamp": "2024-11-01T18:00:00+00:00"},
]
