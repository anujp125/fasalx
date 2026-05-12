from motor.motor_asyncio import AsyncIOMotorClient
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
        logger.info("Connected to MongoDB successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")

async def close_mongo():
    if db_instance.client:
        db_instance.client.close()
        logger.info("MongoDB connection closed.")

def get_mongo_db():
    """Returns the async MongoDB database instance"""
    return db_instance.db
