import redis.asyncio as redis
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

redis_client = None

async def init_redis():
    global redis_client
    try:
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Connected to Redis successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        # In a real app, you might want to raise this or handle fallback
        redis_client = None

async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()

def get_redis():
    return redis_client
