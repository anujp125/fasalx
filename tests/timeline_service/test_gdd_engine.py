"""
GDD Engine – Unit tests
Tests: calculate_daily_gdd, process_environmental_data (IoT / API / satellite fallback)
Hardpoints bypassed:
  - Open-Meteo HTTP API   → httpx.AsyncClient mock
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# timeline_service is in sys.path via conftest
from app.engines.gdd_engine import calculate_daily_gdd, process_environmental_data
from app.models.timeline import EnvironmentalSnapshot

from tests.fixtures.test_data import MOCK_OPEN_METEO_DAILY_RESPONSE


# ─────────────────────────────────────────────────────────────────────────────
# calculate_daily_gdd  (pure function, no I/O)
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateDailyGDD:

    def test_normal_conditions(self):
        """(30 + 18) / 2 - 10 = 14.0"""
        assert calculate_daily_gdd(30.0, 18.0) == 14.0

    def test_average_below_base_returns_zero(self):
        """Average < base → GDD = 0 (no negative GDD)."""
        assert calculate_daily_gdd(8.0, 4.0, t_base=10.0) == 0.0

    def test_exactly_at_base_returns_zero(self):
        """Average == base → GDD = 0."""
        assert calculate_daily_gdd(10.0, 10.0, t_base=10.0) == 0.0

    def test_custom_base_temperature(self):
        """Crop-specific base temp override."""
        # t_base=0 (for cold-hardy crops), avg = 15 → GDD = 15
        assert calculate_daily_gdd(20.0, 10.0, t_base=0.0) == 15.0

    def test_high_summer_temperatures(self):
        """Hot climate day."""
        # (45 + 25) / 2 - 10 = 25
        assert calculate_daily_gdd(45.0, 25.0) == 25.0

    def test_same_tmax_tmin(self):
        """t_max == t_min == 20 → (20+20)/2 - 10 = 10."""
        assert calculate_daily_gdd(20.0, 20.0) == 10.0

    def test_returns_float(self):
        result = calculate_daily_gdd(30.0, 18.0)
        assert isinstance(result, float)


# ─────────────────────────────────────────────────────────────────────────────
# process_environmental_data  (async, with fallback chain)
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessEnvironmentalData:

    @pytest.mark.asyncio
    async def test_iot_data_present_no_api_call(self):
        """IoT t_max/t_min provided → API should NOT be called."""
        snapshot = EnvironmentalSnapshot(
            last_updated=datetime.now(timezone.utc),
            t_max=32.0, t_min=18.0, source="iot", weight=1.0
        )
        with patch("app.engines.gdd_engine.httpx.AsyncClient") as mock_client:
            result = await process_environmental_data(snapshot, [77.2, 28.6], t_base=10.0)

        mock_client.assert_not_called()
        assert result == calculate_daily_gdd(32.0, 18.0)

    @pytest.mark.asyncio
    @patch("app.engines.gdd_engine.httpx.AsyncClient")
    async def test_api_fallback_triggered_when_no_iot(self, mock_httpx):
        """Missing t_max/t_min → Open-Meteo API called, weight set to 0.8."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_OPEN_METEO_DAILY_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get        = AsyncMock(return_value=mock_resp)
        mock_httpx.return_value = mock_client

        snapshot = EnvironmentalSnapshot(
            last_updated=datetime.now(timezone.utc),
            t_max=None, t_min=None, source="satellite", weight=0.5
        )
        result = await process_environmental_data(snapshot, [77.2, 28.6], t_base=10.0)

        assert snapshot.source == "api_fallback"
        assert snapshot.weight == 0.8
        assert snapshot.t_max == 32.0
        assert snapshot.t_min == 18.0
        # (32+18)/2 - 10 = 15.0
        assert result == 15.0

    @pytest.mark.asyncio
    @patch("app.engines.gdd_engine.httpx.AsyncClient")
    async def test_satellite_fallback_on_api_failure(self, mock_httpx):
        """API call raises → satellite fallback: t_max = base+15, t_min = base+2, weight=0.5."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get        = AsyncMock(side_effect=Exception("API timeout"))
        mock_httpx.return_value = mock_client

        snapshot = EnvironmentalSnapshot(
            last_updated=datetime.now(timezone.utc),
            t_max=None, t_min=None, source="satellite", weight=0.5
        )
        t_base = 10.0
        result = await process_environmental_data(snapshot, [77.2, 28.6], t_base=t_base)

        assert snapshot.source == "satellite_fallback"
        assert snapshot.weight == 0.5
        assert snapshot.t_max == t_base + 15.0
        assert snapshot.t_min == t_base + 2.0
        expected = calculate_daily_gdd(t_base + 15.0, t_base + 2.0, t_base)
        assert result == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_gdd_zero_when_iot_data_cold(self):
        """Cold IoT data (avg < base) → GDD = 0."""
        snapshot = EnvironmentalSnapshot(
            last_updated=datetime.now(timezone.utc),
            t_max=5.0, t_min=2.0, source="iot", weight=1.0
        )
        result = await process_environmental_data(snapshot, [77.2, 28.6], t_base=10.0)
        assert result == 0.0
