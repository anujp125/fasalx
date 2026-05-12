from motor.motor_asyncio import AsyncIOMotorClient
import pymongo
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

db_instance = MongoDB()

async def init_mongo():
    try:
        db_instance.client = AsyncIOMotorClient(settings.MONGO_URL)
        db_instance.db = db_instance.client[settings.MONGO_DB_NAME]
        
        # Verify connection
        await db_instance.client.admin.command('ping')
        logger.info("Connected to MongoDB successfully in Timeline Service.")
        
        # Auto-build 2dsphere index for geo-queries as requested
        await build_indexes()
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")

async def build_indexes():
    """
    Startup script to automatically build necessary indexes for the Timeline Service.
    Creates a 2dsphere index on the user_metadata.location field for $near queries.
    """
    try:
        # We index user_crop_timelines on the location field using 2dsphere
        await db_instance.db.user_crop_timelines.create_index(
            [("user_metadata.location", pymongo.GEOSPHERE)],
            name="timeline_location_2dsphere_index"
        )
        logger.info("Successfully built 2dsphere index on user_crop_timelines.")
        
        # Additional index for quick user lookups
        await db_instance.db.user_crop_timelines.create_index(
            "user_metadata.user_id",
            name="timeline_user_id_index"
        )
    except Exception as e:
        logger.error(f"Failed to build MongoDB indexes: {e}")

async def close_mongo():
    if db_instance.client:
        db_instance.client.close()
        logger.info("MongoDB connection closed.")

def get_mongo_db():
    return db_instance.db
