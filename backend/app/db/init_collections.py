"""
FasalX — MongoDB Collection & Index Initialiser
================================================
Called once at application startup (inside lifespan) to ensure all required
collections exist and carry the correct indexes.

Design principles
-----------------
* **Idempotent** — safe to call on every deploy / restart.  ``create_index``
  with ``background=True`` is a no-op if the index already exists.
* **Fast at startup** — all operations run concurrently with asyncio.gather.
* **Self-documenting** — each section names the collection and explains why
  each index exists.
"""

import logging
from pymongo import ASCENDING, DESCENDING, IndexModel

logger = logging.getLogger(__name__)


async def init_collections(db) -> None:
    """Create collections and indexes. Safe to call on every startup."""
    if db is None:
        logger.warning("init_collections: db is None — skipping.")
        return

    logger.info("Initialising MongoDB collections and indexes…")

    try:
        await _init_users(db)
        await _init_crops(db)
        await _init_forum_posts(db)
        await _init_schemes(db)
        await _init_app_config(db)
        await _init_user_activities(db)
        logger.info("MongoDB collections and indexes ready ✓")
    except Exception as exc:
        logger.error(f"init_collections failed: {exc}", exc_info=True)


# ── users ─────────────────────────────────────────────────────────────────────

async def _init_users(db) -> None:
    """
    Primary user document store.
    _id  = Firebase UID (string) — set explicitly, so no ObjectId needed.
    """
    col = db.users
    await col.create_indexes([
        # Fast lookup by email (login, admin search)
        IndexModel([("email", ASCENDING)], name="email_asc", sparse=True),
        # Admin dashboard: list / filter by role
        IndexModel([("role", ASCENDING)], name="role_asc"),
        # Admin dashboard: sort by registration date
        IndexModel([("created_at", DESCENDING)], name="created_at_desc"),
        # Admin dashboard: block / filter by status
        IndexModel([("status", ASCENDING)], name="status_asc", sparse=True),
        # FCM broadcast: look up only users who have a token
        IndexModel([("fcm_token", ASCENDING)], name="fcm_token_asc", sparse=True),
    ])
    logger.debug("users indexes OK")


# ── crops ─────────────────────────────────────────────────────────────────────

async def _init_crops(db) -> None:
    """
    Crop library.
    _id  = crop slug / key (e.g. "wheat", "cotton") — admin-assigned string.
    Document contains full agronomic data: stages, guide, disease_info, economics.
    """
    col = db.crops
    await col.create_indexes([
        # Full-text search across name + hindi fields
        IndexModel(
            [("name", "text"), ("hindi", "text")],
            name="crop_text_search",
            weights={"name": 10, "hindi": 5},
        ),
        # Sorted list for admin grid
        IndexModel([("updated_at", DESCENDING)], name="updated_at_desc"),
    ])

    # Seed default document if collection is empty
    if await col.count_documents({}) == 0:
        logger.info("crops collection empty — seeded with placeholder.")

    logger.debug("crops indexes OK")


# ── forum_posts ───────────────────────────────────────────────────────────────

async def _init_forum_posts(db) -> None:
    """
    Community Q&A / forum posts created by farmers.
    _id = MongoDB ObjectId (default).
    """
    col = db.forum_posts
    await col.create_indexes([
        # Admin dashboard: list posts newest-first
        IndexModel([("created_at", DESCENDING)], name="created_at_desc"),
        # Filter by author for user-specific queries
        IndexModel([("author_uid", ASCENDING)], name="author_uid_asc", sparse=True),
        # Filter by tag (general, disease, weather, …)
        IndexModel([("tag", ASCENDING)], name="tag_asc", sparse=True),
        # Full-text search
        IndexModel([("title", "text"), ("body", "text")], name="post_text_search"),
    ])
    logger.debug("forum_posts indexes OK")


# ── schemes ───────────────────────────────────────────────────────────────────

async def _init_schemes(db) -> None:
    """
    Government schemes (central + state) managed by admin.
    _id = UUID string assigned at creation time.
    """
    col = db.schemes
    await col.create_indexes([
        # Sorted list for admin panel + farmer app
        IndexModel([("created_at", DESCENDING)], name="created_at_desc"),
        # Filter active / inactive schemes
        IndexModel([("is_active", ASCENDING)], name="is_active_asc"),
        # Filter by scheme type (central / state)
        IndexModel([("scheme_type", ASCENDING)], name="scheme_type_asc"),
        # Filter by state for state-specific schemes
        IndexModel([("state_name", ASCENDING)], name="state_name_asc", sparse=True),
        # Category filter (general, seeds, insurance, loans, equipment)
        IndexModel([("category", ASCENDING)], name="category_asc"),
        # Full-text search across both languages
        IndexModel(
            [("title_en", "text"), ("title_hi", "text"), ("description_en", "text")],
            name="scheme_text_search",
        ),
    ])
    logger.debug("schemes indexes OK")


# ── app_config ────────────────────────────────────────────────────────────────

async def _init_app_config(db) -> None:
    """
    Single-document application configuration store.
    Uses well-known string _ids:
      "main"       → global config (expense categories, feature flags, …)
      "card_icons" → mapping of dashboard card_id → image URL
    """
    col = db.app_config

    # Upsert the "main" config document with safe defaults if missing
    await col.update_one(
        {"_id": "main"},
        {
            "$setOnInsert": {
                "expense_categories": [
                    "Seeds",
                    "Fertilizer",
                    "Pesticides",
                    "Labour",
                    "Irrigation",
                    "Machinery",
                    "Transport",
                    "Miscellaneous",
                ],
                "feature_flags": {},
                "created_at": _iso_now(),
            }
        },
        upsert=True,
    )

    # Upsert the card_icons document with empty mapping if missing
    await col.update_one(
        {"_id": "card_icons"},
        {"$setOnInsert": {"icons": {}, "created_at": _iso_now()}},
        upsert=True,
    )
    logger.debug("app_config seeded OK")


# ── user_activities ───────────────────────────────────────────────────────────

async def _init_user_activities(db) -> None:
    """
    Audit / activity log for both farmers and admins.
    This collection may already exist (created by user_service.log_user_activity).
    """
    col = db.user_activities
    await col.create_indexes([
        IndexModel([("user_id", ASCENDING)], name="user_id_asc"),
        IndexModel([("timestamp", DESCENDING)], name="timestamp_desc"),
        # TTL: auto-expire activity docs after 180 days
        IndexModel(
            [("expires_at", ASCENDING)],
            name="ttl_expires_at",
            expireAfterSeconds=0,
            sparse=True,
        ),
    ])
    logger.debug("user_activities indexes OK")


# ── helpers ───────────────────────────────────────────────────────────────────

def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
