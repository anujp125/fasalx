import logging
from datetime import datetime, timezone

from app.db.mongodb import get_mongo_db
from app.db.redis import get_redis
from app.models.admin import SystemConfig, SystemConfigUpdate

logger = logging.getLogger(__name__)

SYSTEM_CONFIG_SCOPE = "global"
SYSTEM_CONFIG_CACHE_KEY = "system_config:global"
SYSTEM_CONFIG_CACHE_TTL_SECONDS = 300


def _default_config() -> SystemConfig:
    return SystemConfig(scope=SYSTEM_CONFIG_SCOPE)


def _config_from_doc(doc: dict | None) -> SystemConfig:
    if not doc:
        return _default_config()
    doc = {key: value for key, value in doc.items() if key != "_id"}
    doc["scope"] = doc.get("scope") or SYSTEM_CONFIG_SCOPE
    return SystemConfig.model_validate(doc)


async def get_system_config() -> SystemConfig:
    redis_client = get_redis()
    if redis_client:
        try:
            cached = await redis_client.get(SYSTEM_CONFIG_CACHE_KEY)
            if cached:
                return SystemConfig.model_validate_json(cached)
        except Exception as exc:
            logger.warning("system_config_cache_read_failed", extra={"error": str(exc)})

    db = get_mongo_db()
    if db is None:
        return _default_config()

    doc = await db.system_config.find_one({"scope": SYSTEM_CONFIG_SCOPE})
    config = _config_from_doc(doc)
    await _cache_config(config)
    return config


async def set_system_config(update: SystemConfigUpdate, updated_by: str | None) -> SystemConfig:
    current = await get_system_config()
    payload = current.model_dump()
    update_data = update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if key == "recommendation" and value is not None:
            payload["recommendation"] = value
        elif value is not None:
            payload[key] = value

    now = datetime.now(timezone.utc)
    payload["scope"] = SYSTEM_CONFIG_SCOPE
    payload["updated_at"] = now
    payload["updated_by"] = updated_by
    config = SystemConfig.model_validate(payload)

    db = get_mongo_db()
    if db is not None:
        await db.system_config.update_one(
            {"scope": SYSTEM_CONFIG_SCOPE},
            {"$set": config.model_dump()},
            upsert=True,
        )

    await _cache_config(config)
    return config


async def _cache_config(config: SystemConfig) -> None:
    redis_client = get_redis()
    if not redis_client:
        return
    try:
        await redis_client.setex(
            SYSTEM_CONFIG_CACHE_KEY,
            SYSTEM_CONFIG_CACHE_TTL_SECONDS,
            config.model_dump_json(),
        )
    except Exception as exc:
        logger.warning("system_config_cache_write_failed", extra={"error": str(exc)})
