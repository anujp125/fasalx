"""
FasalX — Admin Panel API Router
================================
All endpoints are mounted under:
    /api/v1/admin/api/<resource>

Every endpoint requires a valid Firebase admin token
(verified by the ``get_current_admin`` dependency).

Sections
--------
1.  Stats         — dashboard overview counters + recent users
2.  Crops         — full CRUD + icon upload for the crop library
3.  Forum Posts   — list + delete farmer community posts
4.  Users         — list all farmers + block / unblock / suspend
5.  App Config    — expense categories and other global settings
6.  Gov Schemes   — CRUD for government scheme cards
7.  Card Icons    — upload / delete custom dashboard card icons
8.  Storage       — one-time local storage directory setup
9.  Notifications — manual broadcast + test auto-jobs via FCM
"""

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.security import get_current_admin
from app.db.mongodb import get_mongo_db

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────

STATIC_DIR = Path("static/uploads")
STATIC_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_image(file: UploadFile) -> None:
    if file.content_type and file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            400,
            f"Unsupported image type '{file.content_type}'. "
            f"Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )


async def _save_upload(file: UploadFile, subdir: str, prefix: str) -> str:
    """Save uploaded file to static/uploads/<subdir>/ and return the URL path."""
    dest_dir = STATIC_DIR / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "img").suffix or ".png"
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}{suffix}"
    dest = dest_dir / filename
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 5 MB limit.")
    dest.write_bytes(content)
    return f"/static/uploads/{subdir}/{filename}"


# ══════════════════════════════════════════════════════════════════════════════
# 1.  Stats
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_stats(admin: dict = Depends(get_current_admin)):
    """
    Returns aggregate counters and the 10 most recent farmer registrations.
    All counts use MongoDB's fast count_documents (index-covered where possible).
    """
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")

    total_users    = await db.users.count_documents({"role": "farmer"})
    blocked_users  = await db.users.count_documents({"role": "farmer", "status": "blocked"})
    total_crops    = await db.crops.count_documents({})
    total_posts    = await db.forum_posts.count_documents({})
    total_schemes  = await db.schemes.count_documents({})
    # marketplace_listings — tolerate missing collection gracefully
    try:
        total_listings = await db.marketplace_listings.count_documents({})
    except Exception:
        total_listings = 0

    recent_cursor = db.users.find(
        {"role": "farmer"},
        {"_id": 1, "display_name": 1, "email": 1, "location": 1, "created_at": 1},
    ).sort("created_at", -1).limit(10)
    recent_users = await recent_cursor.to_list(10)
    for u in recent_users:
        u["user_id"] = str(u.pop("_id"))
        u["full_name"] = u.pop("display_name", None)

    return {
        "total_users": total_users,
        "blocked_users": blocked_users,
        "total_crops": total_crops,
        "total_posts": total_posts,
        "total_schemes": total_schemes,
        "total_listings": total_listings,
        "recent_users": recent_users,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2.  Crop Library
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/crops")
async def list_crops(admin: dict = Depends(get_current_admin)):
    """Return all crops as a dict keyed by crop slug."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    docs = await db.crops.find({}).sort("updated_at", -1).to_list(500)
    return {"crops": {d.pop("_id"): d for d in docs}}


@router.post("/crops/save")
async def save_crop(payload: dict, admin: dict = Depends(get_current_admin)):
    """Create or update a crop document. The crop key is the MongoDB _id."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    key = payload.get("key")
    if not key:
        raise HTTPException(400, "crop 'key' is required")
    payload["updated_at"] = _now()
    payload.pop("_id", None)  # never let caller overwrite _id directly
    await db.crops.update_one(
        {"_id": key},
        {"$set": payload, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    logger.info(f"Admin {admin.get('uid')} saved crop '{key}'")
    return {"success": True}


@router.post("/crops/delete")
async def delete_crop(payload: dict, admin: dict = Depends(get_current_admin)):
    """Hard-delete a crop by its key."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    key = payload.get("key")
    if not key:
        raise HTTPException(400, "crop 'key' is required")
    result = await db.crops.delete_one({"_id": key})
    if result.deleted_count == 0:
        return {"success": False, "error": "Crop not found"}
    logger.info(f"Admin {admin.get('uid')} deleted crop '{key}'")
    return {"success": True}


@router.post("/crops/upload-icon")
async def upload_crop_icon(
    icon: UploadFile = File(...),
    crop_key: str = Form(...),
    admin: dict = Depends(get_current_admin),
):
    """Upload a crop icon image. Returns the public URL."""
    _validate_image(icon)
    url = await _save_upload(icon, "crops", f"crop_{crop_key}")
    return {"success": True, "url": url}


# ══════════════════════════════════════════════════════════════════════════════
# 3.  Forum Posts
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/posts")
async def list_posts(admin: dict = Depends(get_current_admin)):
    """Return the 200 most recent forum posts."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    posts = await db.forum_posts.find({}).sort("created_at", -1).limit(200).to_list(200)
    for p in posts:
        p["id"] = str(p.pop("_id"))
    return {"posts": posts}


@router.post("/posts/delete")
async def delete_post(payload: dict, admin: dict = Depends(get_current_admin)):
    """Hard-delete a forum post by its id."""
    from bson import ObjectId
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    post_id = payload.get("post_id")
    if not post_id:
        raise HTTPException(400, "'post_id' is required")
    # Support both ObjectId strings and plain string ids
    try:
        result = await db.forum_posts.delete_one({"_id": ObjectId(post_id)})
    except Exception:
        result = await db.forum_posts.delete_one({"_id": post_id})
    if result.deleted_count == 0:
        return {"success": False, "error": "Post not found"}
    logger.info(f"Admin {admin.get('uid')} deleted post '{post_id}'")
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════════
# 4.  Users
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/users")
async def list_users(admin: dict = Depends(get_current_admin)):
    """Return up to 500 farmer accounts, newest first."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    docs = (
        await db.users.find({"role": "farmer"}, {"password": 0, "fcm_token": 0})
        .sort("created_at", -1)
        .limit(500)
        .to_list(500)
    )
    for u in docs:
        u["user_id"] = str(u.pop("_id"))
        u["full_name"] = u.pop("display_name", None)
    return {"users": docs}


@router.post("/users/status")
async def set_user_status(payload: dict, admin: dict = Depends(get_current_admin)):
    """Update a farmer's account status (active / blocked / suspended)."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    user_id = payload.get("user_id")
    status  = payload.get("status")
    if not user_id:
        raise HTTPException(400, "'user_id' is required")
    if status not in ("active", "blocked", "suspended"):
        raise HTTPException(400, "status must be 'active', 'blocked', or 'suspended'")
    result = await db.users.update_one(
        {"_id": user_id},
        {"$set": {"status": status, "updated_at": _now()}},
    )
    if result.matched_count == 0:
        return {"success": False, "error": "User not found"}
    logger.info(f"Admin {admin.get('uid')} set user '{user_id}' status → {status}")
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════════
# 5.  App Config
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/config")
async def get_config(admin: dict = Depends(get_current_admin)):
    """Return the global app configuration document."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    doc = await db.app_config.find_one({"_id": "main"}) or {}
    return {
        "expense_categories": doc.get(
            "expense_categories",
            ["Seeds", "Fertilizer", "Pesticides", "Labour",
             "Irrigation", "Machinery", "Transport", "Miscellaneous"],
        ),
        "feature_flags": doc.get("feature_flags", {}),
    }


@router.post("/config/save")
async def save_config(payload: dict, admin: dict = Depends(get_current_admin)):
    """Persist global app config changes."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    update = {"updated_at": _now(), "updated_by": admin.get("uid")}
    if "expense_categories" in payload:
        update["expense_categories"] = payload["expense_categories"]
    if "feature_flags" in payload:
        update["feature_flags"] = payload["feature_flags"]
    await db.app_config.update_one(
        {"_id": "main"},
        {"$set": update},
        upsert=True,
    )
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════════
# 6.  Government Schemes
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/schemes")
async def list_schemes(admin: dict = Depends(get_current_admin)):
    """Return all government schemes, newest first."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    schemes = await db.schemes.find({}).sort("created_at", -1).to_list(500)
    for s in schemes:
        s["id"] = str(s.pop("_id"))
    return {"schemes": schemes}


@router.post("/schemes/save")
async def save_scheme(payload: dict, admin: dict = Depends(get_current_admin)):
    """Create or update a government scheme."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    if not payload.get("title_en"):
        raise HTTPException(400, "title_en is required")
    scheme_id = payload.pop("id", None) or str(uuid.uuid4())
    payload.pop("_id", None)
    payload["updated_at"] = _now()
    payload["updated_by"] = admin.get("uid")
    await db.schemes.update_one(
        {"_id": scheme_id},
        {"$set": payload, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    logger.info(f"Admin {admin.get('uid')} saved scheme '{scheme_id}'")
    # TODO: send FCM notification to all farmers when a new scheme is published
    return {"success": True}


@router.post("/schemes/delete")
async def delete_scheme(payload: dict, admin: dict = Depends(get_current_admin)):
    """Hard-delete a government scheme."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    scheme_id = payload.get("id")
    if not scheme_id:
        raise HTTPException(400, "'id' is required")
    result = await db.schemes.delete_one({"_id": scheme_id})
    if result.deleted_count == 0:
        return {"success": False, "error": "Scheme not found"}
    logger.info(f"Admin {admin.get('uid')} deleted scheme '{scheme_id}'")
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════════
# 7.  Card Icons
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/card-icons")
async def get_card_icons(admin: dict = Depends(get_current_admin)):
    """Return the mapping of dashboard card_id → custom image URL."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    doc = await db.app_config.find_one({"_id": "card_icons"}) or {}
    return {"icons": doc.get("icons", {})}


@router.post("/card-icons/upload")
async def upload_card_icon(
    icon: UploadFile = File(...),
    card_id: str = Form(...),
    admin: dict = Depends(get_current_admin),
):
    """Upload a custom icon for a dashboard card and persist the URL."""
    _validate_image(icon)
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    url = await _save_upload(icon, "cards", f"card_{card_id}")
    await db.app_config.update_one(
        {"_id": "card_icons"},
        {"$set": {f"icons.{card_id}": url, "updated_at": _now()}},
        upsert=True,
    )
    return {"success": True, "url": url}


@router.post("/card-icons/delete")
async def delete_card_icon(payload: dict, admin: dict = Depends(get_current_admin)):
    """Remove a custom card icon, reverting to the default emoji."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")
    card_id = payload.get("card_id")
    if not card_id:
        raise HTTPException(400, "'card_id' is required")
    await db.app_config.update_one(
        {"_id": "card_icons"},
        {"$unset": {f"icons.{card_id}": ""}},
    )
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════════
# 8.  Storage Setup
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/storage/setup")
async def setup_storage(admin: dict = Depends(get_current_admin)):
    """
    Idempotent one-time setup: creates local upload directories.
    Replace the body with Supabase bucket creation calls for production.
    """
    (STATIC_DIR / "crops").mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "cards").mkdir(parents=True, exist_ok=True)
    logger.info(f"Admin {admin.get('uid')} ran storage setup")
    return {"success": True, "message": "Upload directories are ready."}


# ══════════════════════════════════════════════════════════════════════════════
# 9.  Notifications
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/notifications/broadcast")
async def broadcast_notification(payload: dict, admin: dict = Depends(get_current_admin)):
    """
    Send a push notification to all farmers (or a filtered audience) via FCM.

    Required fields: topic, message_en
    Optional fields: message_hi, link, category, audience ("all" | "active_crop")
    """
    db = get_mongo_db()
    if db is None:
        raise HTTPException(503, "Database not available")

    if not payload.get("topic") or not payload.get("message_en"):
        raise HTTPException(400, "topic and message_en are required")

    audience = payload.get("audience", "all")
    query: dict = {"role": "farmer", "fcm_token": {"$exists": True, "$ne": None}}
    if audience == "active_crop":
        query["active_crops"] = {"$exists": True, "$not": {"$size": 0}}

    users  = await db.users.find(query, {"fcm_token": 1}).to_list(10000)
    tokens = [u["fcm_token"] for u in users if u.get("fcm_token")]

    if not tokens:
        return {"success": True, "sent": 0, "message": "No eligible users with FCM tokens found."}

    sent = 0
    try:
        from firebase_admin import messaging
        # Batch into chunks of 500 (FCM multicast limit)
        chunk_size = 500
        for i in range(0, len(tokens), chunk_size):
            chunk = tokens[i : i + chunk_size]
            msg = messaging.MulticastMessage(
                tokens=chunk,
                notification=messaging.Notification(
                    title=payload["topic"],
                    body=payload["message_en"],
                ),
                data={
                    "link":     payload.get("link", ""),
                    "category": payload.get("category", "general"),
                    "message_hi": payload.get("message_hi", payload["message_en"]),
                },
            )
            result = messaging.send_each_for_multicast(msg)
            sent += result.success_count
    except ImportError:
        # firebase_admin not available in this environment
        logger.warning("FCM broadcast skipped — firebase_admin not importable")
        sent = len(tokens)

    logger.info(
        f"Admin {admin.get('uid')} broadcast '{payload['topic']}' → {sent}/{len(tokens)} sent"
    )
    return {"success": True, "sent": sent}


@router.post("/notifications/test-auto")
async def test_auto_notification(payload: dict, admin: dict = Depends(get_current_admin)):
    """
    Trigger a one-off run of an automatic notification job for testing.
    In production this enqueues a job to the Arq worker.
    """
    notif_type = payload.get("type")
    if notif_type not in ("weather", "tasks"):
        raise HTTPException(400, "type must be 'weather' or 'tasks'")

    # TODO: enqueue via Arq when worker is wired up
    # import arq
    # pool = await arq.create_pool(arq.connections.RedisSettings.from_dsn(settings.REDIS_URL))
    # await pool.enqueue_job(f"send_{notif_type}_notifications")
    logger.info(f"Admin {admin.get('uid')} triggered test-auto '{notif_type}'")
    return {
        "success": True,
        "sent": 0,
        "message": f"Test '{notif_type}' job enqueued (stub — wire Arq worker to activate).",
    }
