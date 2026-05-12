"""
Integration test – Full GDD recalculation pipeline (worker task)
Tests: recalculate_timeline_gdd() end-to-end
Simulates the Arq background worker running without Redis/real MongoDB.

Hardpoints bypassed:
  - MongoDB           → mock_db_factory (via conftest)
  - Open-Meteo API    → httpx mock (when IoT data absent)
  - Arq context       → dict stub
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# timeline_service is in sys.path via conftest
from app.worker.tasks import recalculate_timeline_gdd
from tests.fixtures.test_data import (
    FARMER_UID, TIMELINE_DOC, MOCK_OPEN_METEO_DAILY_RESPONSE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_arq_ctx():
    """Minimal Arq context dict (worker passes this as first arg to tasks)."""
    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock()
    return {"redis": mock_redis}


class TestRecalculateTimelineGDD:

    @pytest.mark.asyncio
    async def test_full_pipeline_with_iot_data(self, mock_db_factory):
        """
        IoT snapshot present → GDD accumulated → milestones evaluated →
        geo-trend checked → DB updated.
        """
        doc = {**TIMELINE_DOC}
        doc["environmental_snapshot"]["t_max"] = 30.0
        doc["environmental_snapshot"]["t_min"] = 18.0

        db = mock_db_factory(timelines=doc)
        ctx = _make_arq_ctx()

        with patch("app.worker.tasks.get_mongo_db", return_value=db), \
             patch("app.engines.geo_trend_analyzer.get_mongo_db", return_value=db):
            result = await recalculate_timeline_gdd(ctx, FARMER_UID)

        assert result is True
        db.user_crop_timelines.update_one.assert_called_once()

        # Verify total_gdd was incremented in the update call
        update_args = db.user_crop_timelines.update_one.call_args[0]
        # update_args[1] is the $set dict
        new_gdd = update_args[1]["$set"]["lifecycle_state"]["total_gdd"]
        # Initial GDD is 0 from TIMELINE_DOC; daily_gdd = (30+18)/2 - 10 = 14
        assert new_gdd == pytest.approx(14.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_pipeline_returns_false_when_timeline_missing(self, mock_db_factory):
        """No timeline found → task returns False, no DB write."""
        db = mock_db_factory(timelines=None)
        ctx = _make_arq_ctx()

        with patch("app.worker.tasks.get_mongo_db", return_value=db):
            result = await recalculate_timeline_gdd(ctx, "ghost-user-999")

        assert result is False
        db.user_crop_timelines.update_one.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.engines.gdd_engine.httpx.AsyncClient")
    async def test_pipeline_with_api_fallback(self, mock_httpx, mock_db_factory):
        """No IoT t_max/t_min → Open-Meteo fallback called during pipeline."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_OPEN_METEO_DAILY_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get        = AsyncMock(return_value=mock_resp)
        mock_httpx.return_value = mock_client

        # Build timeline with no IoT temperature
        doc = {**TIMELINE_DOC}
        doc["environmental_snapshot"] = {
            **doc["environmental_snapshot"],
            "t_max": None,
            "t_min": None,
            "source": "satellite",
            "weight": 0.5,
        }

        db = mock_db_factory(timelines=doc)
        ctx = _make_arq_ctx()

        with patch("app.worker.tasks.get_mongo_db", return_value=db), \
             patch("app.engines.geo_trend_analyzer.get_mongo_db", return_value=db):
            result = await recalculate_timeline_gdd(ctx, FARMER_UID)

        assert result is True
        # API was called once (during GDD engine fallback)
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_gdd_never_decrements(self, mock_db_factory):
        """
        Even on a cold day (daily_gdd = 0), total_gdd should not decrease.
        Initial total_gdd = 200, daily = 0 → stored = 200.
        """
        doc = {**TIMELINE_DOC}
        doc["lifecycle_state"]["total_gdd"] = 200.0
        # Cold temps: (5+2)/2 - 10 = -3.5 → clamped to 0
        doc["environmental_snapshot"]["t_max"] = 5.0
        doc["environmental_snapshot"]["t_min"] = 2.0

        db = mock_db_factory(timelines=doc)
        ctx = _make_arq_ctx()

        with patch("app.worker.tasks.get_mongo_db", return_value=db), \
             patch("app.engines.geo_trend_analyzer.get_mongo_db", return_value=db):
            result = await recalculate_timeline_gdd(ctx, FARMER_UID)

        assert result is True
        update_args = db.user_crop_timelines.update_one.call_args[0]
        new_gdd = update_args[1]["$set"]["lifecycle_state"]["total_gdd"]
        assert new_gdd == pytest.approx(200.0)   # 200 + 0 = 200
