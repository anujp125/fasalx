import logging
from typing import List, Dict, Any, Optional
from bson import ObjectId
from app.db.mongodb import get_mongo_db
from app.models.fields import FieldRegistrationRequest, FieldResponse, FarmOverviewResponse
from app.engine.ingestors.market import MSP_DATA

logger = logging.getLogger(__name__)

# Heuristics for Farm Overview Profit Estimations
EXPECTED_YIELD_QUINTALS_PER_ACRE = {
    "Wheat": 20,
    "Soyabean": 10,
    "Paddy(Dhan)(Common)": 18,
    "Mustard": 8,
    "Gram": 6,
    "Garlic": 35,
    "Onion": 80,
    "Moong": 5,
    "Pomegranate": 40,
    "Dragon Fruit": 30,
    "Citrus": 50
}
COST_OF_CULTIVATION_PER_ACRE = 15000  # Default ₹15,000 for cereals

async def create_field(user_id: str, request: FieldRegistrationRequest) -> str:
    db = get_mongo_db()
    if db is None:
        raise Exception("Database not initialized")
        
    doc = request.model_dump()
    doc["user_id"] = user_id
    doc["selected_crop"] = None
    
    result = await db.fields.insert_one(doc)
    return str(result.inserted_id)

async def get_user_fields(user_id: str) -> List[FieldResponse]:
    db = get_mongo_db()
    if db is None:
        return []
        
    cursor = db.fields.find({"user_id": user_id})
    fields = []
    async for doc in cursor:
        fields.append(FieldResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            lat=doc["lat"],
            lon=doc["lon"],
            area=doc["area"],
            selected_crop=doc.get("selected_crop")
        ))
    return fields

async def get_field_by_id(user_id: str, field_id: str) -> Optional[dict]:
    db = get_mongo_db()
    if db is None:
        return None
    try:
        doc = await db.fields.find_one({"_id": ObjectId(field_id), "user_id": user_id})
        return doc
    except Exception:
        return None

async def update_field_crop(user_id: str, field_id: str, crop_name: str) -> bool:
    db = get_mongo_db()
    if db is None:
        return False
    try:
        result = await db.fields.update_one(
            {"_id": ObjectId(field_id), "user_id": user_id},
            {"$set": {"selected_crop": crop_name}}
        )
        return result.modified_count > 0
    except Exception:
        return False

async def get_farm_overview(user_id: str) -> FarmOverviewResponse:
    fields = await get_user_fields(user_id)
    
    total_area = 0.0
    gross_revenue = 0.0
    total_cost = 0.0
    active_crops = set()
    
    for f in fields:
        total_area += f.area
        total_cost += (f.area * COST_OF_CULTIVATION_PER_ACRE)
        
        if f.selected_crop:
            active_crops.add(f.selected_crop)
            # Use MSP as a proxy for expected price
            expected_price = 2000  # Default generic fallback
            if f.selected_crop in MSP_DATA:
                expected_price = MSP_DATA[f.selected_crop]["msp"]
            elif f.selected_crop in ["Pomegranate", "Dragon Fruit", "Citrus"]:
                # Horticulture tends to have much higher prices per quintal, rough estimate
                expected_price = 8000
                
            yield_per_acre = EXPECTED_YIELD_QUINTALS_PER_ACRE.get(f.selected_crop, 10)
            
            # Revenue = Area * Yield * Price
            gross_revenue += (f.area * yield_per_acre * expected_price)
            
    net_profit = gross_revenue - total_cost
    
    return FarmOverviewResponse(
        total_fields=len(fields),
        total_area_acres=round(total_area, 2),
        estimated_gross_revenue=round(gross_revenue, 2),
        estimated_total_cost=round(total_cost, 2),
        estimated_net_profit=round(net_profit, 2),
        active_crops=list(active_crops)
    )
