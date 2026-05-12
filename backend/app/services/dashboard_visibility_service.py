import json
import logging
from datetime import datetime, timezone

from app.db.mongodb import get_mongo_db
from app.db.redis import get_redis
from app.models.dashboard_visibility import (
    DEFAULT_DASHBOARD_COMPONENTS,
    DashboardComponentVisibility,
    DashboardVisibilityResponse,
)

logger = logging.getLogger(__name__)

DASHBOARD_VISIBILITY_SCOPE = "global"
DASHBOARD_VISIBILITY_CACHE_KEY = "dashboard_visibility:global"
DASHBOARD_VISIBILITY_CACHE_TTL_SECONDS = 300


def _default_response() -> DashboardVisibilityResponse:
    return DashboardVisibilityResponse(
        scope=DASHBOARD_VISIBILITY_SCOPE,
        components=DashboardComponentVisibility(**DEFAULT_DASHBOARD_COMPONENTS),
    )


def _response_from_doc(doc: dict | None) -> DashboardVisibilityResponse:
    if not doc:
        return _default_response()
    components = {
        **DEFAULT_DASHBOARD_COMPONENTS,
        **(doc.get("components") or {}),
    }
    return DashboardVisibilityResponse(
        scope=doc.get("scope") or DASHBOARD_VISIBILITY_SCOPE,
        components=DashboardComponentVisibility(**components),
        updated_at=doc.get("updated_at"),
        updated_by=doc.get("updated_by"),
    )


async def get_dashboard_visibility() -> DashboardVisibilityResponse:
    redis_client = get_redis()
    if redis_client:
        try:
            cached = await redis_client.get(DASHBOARD_VISIBILITY_CACHE_KEY)
            if cached:
                return DashboardVisibilityResponse.model_validate_json(cached)
        except Exception as exc:
            logger.warning("dashboard_visibility_cache_read_failed", extra={"error": str(exc)})

    db = get_mongo_db()
    if db is None:
        return _default_response()

    doc = await db.dashboard_visibility.find_one({"scope": DASHBOARD_VISIBILITY_SCOPE})
    response = _response_from_doc(doc)
    await _cache_visibility(response)
    return response


async def set_dashboard_visibility(
    components: DashboardComponentVisibility,
    updated_by: str | None,
) -> DashboardVisibilityResponse:
    now = datetime.now(timezone.utc)
    db = get_mongo_db()
    response = DashboardVisibilityResponse(
        scope=DASHBOARD_VISIBILITY_SCOPE,
        components=components,
        updated_at=now,
        updated_by=updated_by,
    )

    if db is not None:
        await db.dashboard_visibility.update_one(
            {"scope": DASHBOARD_VISIBILITY_SCOPE},
            {
                "$set": {
                    "scope": DASHBOARD_VISIBILITY_SCOPE,
                    "components": components.model_dump(),
                    "updated_at": now,
                    "updated_by": updated_by,
                }
            },
            upsert=True,
        )

    await _cache_visibility(response)
    return response


async def toggle_dashboard_component(
    component: str,
    visible: bool,
    updated_by: str | None,
) -> DashboardVisibilityResponse:
    current = await get_dashboard_visibility()
    current_components = current.components.model_dump()
    if component not in current_components:
        valid = ", ".join(sorted(current_components))
        raise ValueError(f"Unknown dashboard component '{component}'. Valid components: {valid}")

    current_components[component] = visible
    return await set_dashboard_visibility(
        DashboardComponentVisibility(**current_components),
        updated_by=updated_by,
    )


async def _cache_visibility(response: DashboardVisibilityResponse) -> None:
    redis_client = get_redis()
    if not redis_client:
        return
    try:
        await redis_client.setex(
            DASHBOARD_VISIBILITY_CACHE_KEY,
            DASHBOARD_VISIBILITY_CACHE_TTL_SECONDS,
            response.model_dump_json(),
        )
    except Exception as exc:
        logger.warning("dashboard_visibility_cache_write_failed", extra={"error": str(exc)})
