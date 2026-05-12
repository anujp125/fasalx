import logging
from arq import Worker, cron
from arq.connections import RedisSettings
from app.core.config import settings
from app.db.mongodb import init_mongo, close_mongo, get_mongo_db
from app.models.timeline import UserCropTimeline
from app.engines.gdd_engine import process_environmental_data
from app.engines.milestone_predictor import predict_milestones
from app.engines.geo_trend_analyzer import analyze_geo_trends

logger = logging.getLogger("arq.worker")

async def startup(ctx):
    """Initializes MongoDB connection for the worker."""
    logger.info("Initializing background worker resources...")
    await init_mongo()

async def shutdown(ctx):
    """Closes connections gracefully."""
    logger.info("Shutting down worker resources...")
    await close_mongo()

async def recalculate_timeline_gdd(ctx, user_id: str):
    """
    Background job triggered by an IoT sync or daily cron.
    Fetches the user's timeline, applies the GDD engine, milestone predictor, 
    and geo-analyzer, then saves the updated state back to MongoDB.
    """
    logger.info(f"Starting async GDD recalculation for user {user_id}")
    db = get_mongo_db()
    
    # 1. Fetch Timeline
    timeline_dict = await db.user_crop_timelines.find_one({"user_metadata.user_id": user_id})
    if not timeline_dict:
        logger.error(f"Timeline not found for user {user_id}")
        return False
        
    timeline = UserCropTimeline(**timeline_dict)
    
    # 2. Run GDD Engine
    daily_gdd = await process_environmental_data(
        timeline.environmental_snapshot,
        timeline.user_metadata.location.coordinates,
        timeline.user_metadata.t_base
    )
    timeline.lifecycle_state.total_gdd += daily_gdd
    
    # 3. Predict Milestones
    timeline = predict_milestones(timeline)
    
    # 4. Analyze Geo-Trends
    timeline = await analyze_geo_trends(timeline)
    
    # 5. Persist to MongoDB
    update_data = timeline.model_dump(by_alias=True, exclude_unset=True)
    if "_id" in update_data:
        del update_data["_id"] # Don't update the immutable ID
        
    await db.user_crop_timelines.update_one(
        {"user_metadata.user_id": user_id},
        {"$set": update_data}
    )
    
    logger.info(f"Successfully recalibrated timeline for user {user_id}. New GDD: {timeline.lifecycle_state.total_gdd}")
    return True

async def daily_gdd_accumulation_job(ctx):
    """
    Scheduled CRON task to ensure all active timelines progress daily,
    even if the farmer has no IoT sensors.
    """
    logger.info("Running Daily GDD Accumulation Job for all active timelines...")
    db = get_mongo_db()
    
    # In production, you might paginate this or push sub-tasks to the queue
    # if the number of users is massive.
    cursor = db.user_crop_timelines.find({"lifecycle_state.progress_percentage": {"$lt": 100.0}})
    
    async for doc in cursor:
        user_id = doc.get("user_metadata", {}).get("user_id")
        if user_id:
            # Enqueue the individual user recalibration
            await ctx['redis'].enqueue_job('recalculate_timeline_gdd', user_id)
            
    logger.info("Daily GDD Accumulation Job complete.")

class WorkerSettings:
    functions = [recalculate_timeline_gdd]
    cron_jobs = [
        # Runs at 21:30 UTC daily (3:00 AM IST) - Low traffic period in India
        cron(daily_gdd_accumulation_job, hour=21, minute=30)
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
