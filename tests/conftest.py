"""
Shared pytest conftest for the FasalX test suite.
Patches all hardpoints (Firebase, MongoDB, Redis, external HTTP APIs)
so every test runs offline without any real infrastructure.

IMPORTANT: sys.path for each service (backend / timeline_service) is set in
the per-package conftest.py files (tests/backend/conftest.py and
tests/timeline_service/conftest.py) to avoid the 'app' namespace collision.
This root conftest only patches firebase_admin and provides shared fixtures.
"""
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))

# ── Patch firebase_admin BEFORE any app module is imported ───────────────────
# This prevents the real Firebase SDK from being initialised during collection.
firebase_mock_module = MagicMock()
firebase_auth_mock   = MagicMock()
firebase_mock_module.auth = firebase_auth_mock
sys.modules.setdefault("firebase_admin",              firebase_mock_module)
sys.modules.setdefault("firebase_admin.auth",         firebase_auth_mock)
sys.modules.setdefault("firebase_admin.credentials",  MagicMock())

# NOTE: test_data is imported lazily in per-package conftest so the
# correct 'app' is already on sys.path when modules load.

# ─────────────────────────────────────────────────────────────────────────────
# Reusable mock-DB factory
# ─────────────────────────────────────────────────────────────────────────────

def _build_mock_db(users_doc=None, activities=None, crop_templates=None,
                   telemetry=None, timelines=None):
    """
    Returns a MagicMock that mimics Motor's async database.
    Populate keyword args with the find_one / to_list return values you need.
    """
    db = MagicMock()

    # ── users ────────────────────────────────────────────────────────────────
    db.users = AsyncMock()
    db.users.find_one        = AsyncMock(return_value=users_doc)
    db.users.insert_one      = AsyncMock(return_value=MagicMock(inserted_id="new-id-001"))
    db.users.update_one      = AsyncMock(return_value=MagicMock(modified_count=1))
    db.users.delete_one      = AsyncMock(return_value=MagicMock(deleted_count=1))

    # ── user_activities ───────────────────────────────────────────────────────
    mock_cursor = AsyncMock()
    mock_cursor.sort         = MagicMock(return_value=mock_cursor)
    mock_cursor.skip         = MagicMock(return_value=mock_cursor)
    mock_cursor.limit        = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list      = AsyncMock(return_value=activities or [])
    db.user_activities       = AsyncMock()
    db.user_activities.find  = MagicMock(return_value=mock_cursor)
    db.user_activities.insert_one = AsyncMock(return_value=MagicMock(inserted_id="act-new"))
    db.user_activities.delete_many = AsyncMock()

    # ── crop_templates ────────────────────────────────────────────────────────
    async def _async_gen(items):
        for i in items:
            yield i
    template_cursor = AsyncMock()
    template_cursor.__aiter__ = MagicMock(side_effect=lambda: _async_gen(crop_templates or []))
    db.crop_templates        = AsyncMock()
    db.crop_templates.find   = MagicMock(return_value=template_cursor)
    db.crop_templates.insert_one = AsyncMock(return_value=MagicMock(inserted_id="tmpl-001"))

    # ── telemetry ─────────────────────────────────────────────────────────────
    db.telemetry             = AsyncMock()
    db.telemetry.insert_one  = AsyncMock(return_value=MagicMock(inserted_id="telem-001"))

    # ── user_crop_timelines ───────────────────────────────────────────────────
    db.user_crop_timelines   = AsyncMock()
    db.user_crop_timelines.find_one    = AsyncMock(return_value=timelines)
    db.user_crop_timelines.insert_one  = AsyncMock(return_value=MagicMock(inserted_id="tl-001"))
    db.user_crop_timelines.update_one  = AsyncMock(return_value=MagicMock(modified_count=1))
    tl_cursor = AsyncMock()
    tl_cursor.__aiter__ = MagicMock(return_value=iter([]))
    db.user_crop_timelines.find        = MagicMock(return_value=tl_cursor)
    db.user_crop_timelines.aggregate   = MagicMock(return_value=tl_cursor)

    return db


# ─────────────────────────────────────────────────────────────────────────────
# Pytest fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db_factory():
    """Expose the builder so individual tests can customise it."""
    return _build_mock_db


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get      = AsyncMock(return_value=None)   # cache miss by default
    redis.setex    = AsyncMock()
    redis.ping     = AsyncMock(return_value=True)
    return redis
