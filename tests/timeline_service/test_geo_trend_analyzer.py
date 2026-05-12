"""
Geo-Trend Analyzer – Unit tests
Tests: analyze_geo_trends() with nearby pest alert injection
Hardpoints bypassed:
  - MongoDB $geoNear aggregation pipeline  → mock async cursor
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.geo_trend_analyzer import analyze_geo_trends
from app.models.timeline import (
    UserCropTimeline, UserMetadata, LifecycleState,
    Milestone, MilestoneType, MilestoneStatus,
    EnvironmentalSnapshot, GeoLocation,
)
from tests.fixtures.test_data import (
    FARMER_UID, CROP_ID, SOWING_DATE, NEIGHBOUR_TIMELINE_DOC,
)


def _base_timeline() -> UserCropTimeline:
    return UserCropTimeline(
        user_metadata=UserMetadata(
            user_id=FARMER_UID,
            crop_id=CROP_ID,
            sowing_date=SOWING_DATE,
            location=GeoLocation(coordinates=[77.209, 28.614]),
            t_base=10.0,
        ),
        lifecycle_state=LifecycleState(
            current_stage="Tillering",
            progress_percentage=30.0,
            total_gdd=400.0,
        ),
        milestone_map=[
            Milestone(
                name="Tillering",
                type=MilestoneType.MACRO,
                status=MilestoneStatus.COMPLETED,
                target_gdd=350.0,
                confidence_score=1.0,
            ),
        ],
        environmental_snapshot=EnvironmentalSnapshot(
            last_updated=datetime.now(timezone.utc),
            t_max=30.0,
            t_min=15.0,
            soil_moisture=45.0,
            source="iot",
            weight=1.0,
        ),
    )


class TestAnalyzeGeoTrends:

    @pytest.mark.asyncio
    async def test_injects_pest_warning_when_nearby_alerts(self):
        """Nearby farm has pest alert → 'Regional Pest Warning' added."""
        mock_db = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__ = MagicMock(
            return_value=aiter_from_list([NEIGHBOUR_TIMELINE_DOC])
        )
        mock_db.user_crop_timelines.aggregate.return_value = mock_cursor

        tl = _base_timeline()

        with patch("app.engines.geo_trend_analyzer.get_mongo_db", return_value=mock_db):
            result = await analyze_geo_trends(tl)

        names = [m.name for m in result.milestone_map]
        assert "Regional Pest Warning" in names

        warning = next(m for m in result.milestone_map if m.name == "Regional Pest Warning")
        assert warning.status == MilestoneStatus.ALERT
        assert warning.type   == MilestoneType.MICRO

    @pytest.mark.asyncio
    async def test_no_injection_when_no_nearby_alerts(self):
        """No neighbours with pest alerts → milestone_map unchanged."""
        mock_db = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__ = MagicMock(return_value=aiter_from_list([]))
        mock_db.user_crop_timelines.aggregate.return_value = mock_cursor

        tl = _base_timeline()
        original_count = len(tl.milestone_map)

        with patch("app.engines.geo_trend_analyzer.get_mongo_db", return_value=mock_db):
            result = await analyze_geo_trends(tl)

        assert len(result.milestone_map) == original_count

    @pytest.mark.asyncio
    async def test_no_duplicate_regional_warning(self):
        """If Regional Pest Warning already exists, don't add another one."""
        mock_db = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__ = MagicMock(
            return_value=aiter_from_list([NEIGHBOUR_TIMELINE_DOC])
        )
        mock_db.user_crop_timelines.aggregate.return_value = mock_cursor

        tl = _base_timeline()
        # Pre-insert the warning
        tl.milestone_map.append(Milestone(
            name="Regional Pest Warning",
            type=MilestoneType.MICRO,
            status=MilestoneStatus.ALERT,
            confidence_score=0.8,
        ))
        count_before = len(tl.milestone_map)

        with patch("app.engines.geo_trend_analyzer.get_mongo_db", return_value=mock_db):
            result = await analyze_geo_trends(tl)

        regional_warnings = [m for m in result.milestone_map if m.name == "Regional Pest Warning"]
        assert len(regional_warnings) == 1   # still just one
        assert len(result.milestone_map) == count_before

    @pytest.mark.asyncio
    async def test_graceful_when_db_not_initialized(self):
        """MongoDB unavailable → returns timeline unchanged, no crash."""
        tl = _base_timeline()
        original_count = len(tl.milestone_map)

        with patch("app.engines.geo_trend_analyzer.get_mongo_db", return_value=None):
            result = await analyze_geo_trends(tl)

        assert len(result.milestone_map) == original_count

    @pytest.mark.asyncio
    async def test_graceful_on_aggregation_exception(self):
        """Aggregation error → handled gracefully, timeline returned unchanged."""
        mock_db = MagicMock()
        mock_db.user_crop_timelines.aggregate.side_effect = Exception("DB error")

        tl = _base_timeline()
        original_count = len(tl.milestone_map)

        with patch("app.engines.geo_trend_analyzer.get_mongo_db", return_value=mock_db):
            result = await analyze_geo_trends(tl)

        assert len(result.milestone_map) == original_count


# ─── Helper: async generator from a list ─────────────────────────────────────
def aiter_from_list(items):
    """Returns an async iterator over a plain list."""
    async def _gen():
        for item in items:
            yield item
    return _gen()
