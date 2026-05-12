from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from typing import Optional
from app.core.config import settings
from app.core.security import get_current_user
from app.api.routers.disease import predict_disease as predict_disease_with_fallback
from app.db.mongodb import get_mongo_db
from app.engine.ingestors.weather import get_weather_forecast
from app.engine.ingestors.market import get_market_data
from app.services.geolocation_service import resolve_location
from app.services.ml_client import predict_crop_disease
from app.models.agronomy import WeatherResponse, CropTemplate
from app.db.redis import get_redis
import json
from datetime import datetime, timezone

router = APIRouter()


@router.post("/disease/predict", include_in_schema=False)
async def predict_disease(
    crop_name: str = Form(...),
    image: UploadFile | None = File(None),
    issue_text: str | None = Form(None),
    text_issue: str | None = Form(None),
    current_user: dict = Depends(get_current_user),
):
    return await predict_disease_with_fallback(
        crop_name=crop_name,
        image=image,
        issue_text=issue_text,
        text_issue=text_issue,
        current_user=current_user,
    )


async def _read_limited_upload(image: UploadFile) -> bytes | JSONResponse:
    chunks = []
    total_size = 0

    while True:
        chunk = await image.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > settings.ML_PROXY_MAX_UPLOAD_BYTES:
            return _prediction_error(
                status_code=413,
                message=f"Image exceeds max upload size of {settings.ML_PROXY_MAX_UPLOAD_BYTES} bytes.",
            )
        chunks.append(chunk)

    if total_size == 0:
        return _prediction_error(status_code=400, message="Image file is empty.")

    return b"".join(chunks)


def _prediction_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "disease": None,
            "confidence": 0,
            "top3": [],
            "error": message,
        },
    )

@router.get("/weather", response_model=WeatherResponse)
async def get_weather(
    request: Request,
    lat: Optional[float] = None, 
    lon: Optional[float] = None, 
    current_user: dict = Depends(get_current_user)
):
    """
    Get hyper-local weather forecast. 
    Auto-resolves location via GPS -> Profile -> IP Fallback.
    """
    try:
        location = await resolve_location(request, uid=current_user.get("uid"), lat=lat, lon=lon)
        weather = await get_weather_forecast(location["lat"], location["lon"])
        # Adding a small hint in description for debugging the source
        weather.description += f" (Location Source: {location['source']})"
        return weather
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mandi")
@router.get("/mandi-prices")
async def get_mandi_pricing(
    request: Request,
    state: Optional[str] = None, 
    market: Optional[str] = None, 
    commodity: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get real-time commodity market prices.
    Auto-resolves state/market via Explicit Query -> Profile -> IP Fallback.
    """
    try:
        location = await resolve_location(request, uid=current_user.get("uid"), state=state, market=market)
        
        # If user explicitly provided state but NOT market, ignore the resolved market 
        # (which might be an IP fallback like 'Delhi' that doesn't belong to the state)
        final_market = market if (state and not market) else location["market"]
        
        market_data = await get_market_data(location["state"], final_market, commodity)
        data = market_data.model_dump()
        data["location_source"] = location["source"]
        return data
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail="External API error")

@router.post("/templates", response_model=dict)
async def create_crop_template(template: CropTemplate, current_user: dict = Depends(get_current_user)):
    """
    [Admin] Create a new Crop Template in MongoDB.
    """
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    template_data = template.model_dump()
    template_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.crop_templates.insert_one(template_data)
    
    return {
        "message": "Crop template created successfully", 
        "id": str(result.inserted_id),
        "updated_at": template_data["updated_at"]
    }

@router.get("/templates", response_model=list[dict])
async def get_crop_templates(current_user: dict = Depends(get_current_user)):
    """
    Get all available Crop Templates from MongoDB.
    """
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
        
    templates = []
    cursor = db.crop_templates.find({})
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        templates.append(doc)
        
    return templates
