import logging
from app.db.mongodb import get_mongo_db
from app.models.timeline import UserCropTimeline, Milestone, MilestoneType, MilestoneStatus

logger = logging.getLogger(__name__)

async def analyze_geo_trends(timeline: UserCropTimeline) -> UserCropTimeline:
    """
    Executes a $geoNear query in MongoDB to find other timelines within a 50km radius.
    Looks for recently injected "Pest Alert" milestones to warn the current user.
    """
    db = get_mongo_db()
    if db is None:
        logger.error("MongoDB not initialized during Geo-Trend analysis.")
        return timeline

    lon, lat = timeline.user_metadata.location.coordinates
    
    # Construct the $geoNear aggregation pipeline
    # We look for nearby farms within 50km that have an active 'Pest Alert' milestone
    pipeline = [
        {
            "$geoNear": {
                "near": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                },
                "distanceField": "dist.calculated",
                "maxDistance": 50000, # 50km in meters
                "spherical": True
            }
        },
        {
            "$match": {
                # Ensure we don't query the user's own farm
                "user_metadata.user_id": {"$ne": timeline.user_metadata.user_id},
                "milestone_map": {
                    "$elemMatch": {
                        "status": "alert",
                        "name": {"$regex": "pest|disease|blight", "$options": "i"}
                    }
                }
            }
        },
        {
            # Limit to the nearest 10 alerts to reduce memory overhead
            "$limit": 10
        }
    ]
    
    try:
        nearby_alerts_cursor = db.user_crop_timelines.aggregate(pipeline)
        nearby_alerts = [doc async for doc in nearby_alerts_cursor]
        
        if nearby_alerts:
            logger.info(f"Geo-Trend Analyzer found {len(nearby_alerts)} pest alerts near user {timeline.user_metadata.user_id}")
            
            # Check if this user already has a regional alert to avoid duplicates
            existing_alerts = [m.name for m in timeline.milestone_map if m.status == MilestoneStatus.ALERT]
            
            if "Regional Pest Warning" not in existing_alerts:
                # Inject a Risk Node (Micro Milestone)
                risk_node = Milestone(
                    name="Regional Pest Warning",
                    type=MilestoneType.MICRO,
                    status=MilestoneStatus.ALERT,
                    trigger_logic="Geo-Trend Analyzer detected nearby pest outbreaks."
                )
                timeline.milestone_map.append(risk_node)
                
    except Exception as e:
        logger.error(f"Geo-Trend aggregation failed: {e}")
        
    return timeline
