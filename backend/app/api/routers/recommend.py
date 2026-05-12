import time
import logging
import asyncio
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from app.engine.models.recommendation import RecommendationRequest, DualRecommendationResponse, RecommendationSelectRequest
from app.engine.core import RecommendationEngine
from app.api.routers.ingest import get_field_intelligence
from app.engine.ingestors.satellite import get_field_health
from app.core.security import get_current_user
from app.engine.history import get_previous_crop, save_recommendation_session, mark_crop_selected
from app.services.system_config_service import get_system_config

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/calculate", response_model=DualRecommendationResponse)
async def calculate_recommendations(
    request: RecommendationRequest, 
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Core Recommendation Engine endpoint.
    1. Looks up the registered Field.
    2. Fetches Field Intelligence (Weather, Soil, Market, Satellite).
    3. Fetches crop history for the user and field.
    4. Runs the data through the Scoring Heuristics (Dual-Track).
    5. Returns the structured crop recommendations and saves the session async.
    """
    start_time = time.time()
    user_id = current_user.get("uid")
    
    from app.services.field_service import get_field_by_id
    field_doc = await get_field_by_id(user_id, request.field_id)
    if not field_doc:
        raise HTTPException(status_code=404, detail="Field not found")
        
    lat = field_doc["lat"]
    lon = field_doc["lon"]
    
    # 1. Gather Intelligence, Satellite, & History
    try:
        intelligence, satellite_data, previous_crop, system_config = await asyncio.gather(
            get_field_intelligence(lat=lat, lon=lon, commodity=None),
            get_field_health(lat=lat, lon=lon),
            get_previous_crop(user_id=user_id, field_id=request.field_id),
            get_system_config(),
        )
    except Exception as e:
        logger.error(f"Failed to gather intelligence or history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch field intelligence data.")

    # 2. Load state-specific crop timelines (sowing/transplanting/harvesting)
    timeline_cache = []
    try:
        from app.db.mongodb import get_mongo_db
        db = get_mongo_db()
        if db is not None:
            cursor = db.horticulture_crop_timeline.find({}, {"_id": 0, "created_at": 0})
            timeline_cache = [doc async for doc in cursor]
    except Exception as e:
        logger.warning(f"Failed to load crop timelines: {e}")

    # 3. Initialize Engine
    engine = RecommendationEngine(
        intelligence=intelligence, 
        satellite_data=satellite_data,
        target_season=request.target_season,
        previous_crop=previous_crop,
        system_config=system_config,
        timeline_cache=timeline_cache,
    )
    
    # 4. Calculate
    recommendations = await engine.calculate_recommendations_async()
    
    rec_dicts = {
        "seasonal": [r.model_dump() for r in recommendations.seasonal],
        "horticulture": [r.model_dump() for r in recommendations.horticulture]
    }
    intel_dict = intelligence.model_dump()
    intel_dict["satellite"] = satellite_data
    
    session_id = await save_recommendation_session(
        user_id=user_id,
        field_id=request.field_id,
        lat=lat,
        lon=lon,
        intelligence=intel_dict,
        recommendations=rec_dicts
    )
    
    # Attach the session ID to every recommendation returned
    for rec in recommendations.seasonal:
        rec.id = session_id
    for rec in recommendations.horticulture:
        rec.id = session_id
    
    exec_time = (time.time() - start_time) * 1000
    logger.info(f"Recommendation calculated in {exec_time:.2f}ms")
    
    return recommendations

@router.post("/select")
async def select_recommendation(
    request: RecommendationSelectRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint for users to "accept" a recommendation.
    Updates the MongoDB record to mark which crop was actually chosen.
    This informs the history-awareness engine for next season.
    """
    user_id = current_user.get("uid")
    success = await mark_crop_selected(
        user_id=user_id,
        field_id=request.field_id,
        recommendation_id=request.recommendation_id,
        crop_name=request.crop_name
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to mark crop as selected. Invalid ID or unowned record.")
        
    return {"status": "success", "message": f"{request.crop_name} successfully marked as selected for this field."}
