import pytest

from app.engine.core import RecommendationEngine
from app.engine.knowledge_base import CROP_DATABASE
from app.engine.ingestors.geo import get_lgd_codes, infer_indian_admin_from_coordinates
from app.engine.ingestors.satellite import get_field_health
from app.engine.ingestors.soil import fetch_soil_data
from app.engine.models.ingestion import FieldIntelligence, WeatherData


AUDIT_CASES = {
    "rajasthan": {
        "lat": 26.9124,
        "lon": 70.9123,
        "state": "Rajasthan",
        "district": "Jaisalmer",
        "rain": 272.8,
    },
    "maharashtra": {
        "lat": 19.7515,
        "lon": 75.7139,
        "state": "Maharashtra",
        "district": "Jalna",
        "rain": 1156.5,
    },
    "bihar": {
        "lat": 25.7854,
        "lon": 87.4731,
        "state": "Bihar",
        "district": "Purnia",
        "rain": 1665.8,
    },
}


async def _engine_for(case_key: str, previous_crop: str | None = None) -> RecommendationEngine:
    case = AUDIT_CASES[case_key]
    soil = await fetch_soil_data(state=case["state"], district=case["district"])
    satellite = await get_field_health(case["lat"], case["lon"])
    weather = WeatherData(
        temperature_min=22.0,
        temperature_max=36.0,
        humidity=55.0,
        rainfall_current=0.0,
        rainfall_history_12m=case["rain"],
        gdd=19.0,
        description="audit fixture",
    )
    intelligence = FieldIntelligence(
        coordinates={"lat": case["lat"], "lon": case["lon"]},
        weather=weather,
        soil=soil,
        market=None,
        errors={},
    )
    return RecommendationEngine(
        intelligence,
        satellite,
        target_season="Kharif",
        previous_crop=previous_crop,
    )


def test_coordinate_fallbacks_and_lgd_codes_cover_audit_sites():
    for case in AUDIT_CASES.values():
        inferred = infer_indian_admin_from_coordinates(case["lat"], case["lon"])
        assert inferred is not None
        assert inferred["state"] == case["state"]
        assert inferred["district"] == case["district"]

        codes = get_lgd_codes(case["state"], case["district"])
        assert codes["state_lgd"] is not None
        assert codes["district_lgd"] is not None


@pytest.mark.asyncio
async def test_satellite_mock_is_zone_aware_and_deterministic():
    rajasthan = await get_field_health(26.9124, 70.9123)
    maharashtra = await get_field_health(19.7515, 75.7139)
    bihar = await get_field_health(25.7854, 87.4731)

    assert rajasthan == await get_field_health(26.9124, 70.9123)
    assert rajasthan["soil_moisture"] < 0.2
    assert 0.3 <= maharashtra["soil_moisture"] <= 0.56
    assert bihar["soil_moisture"] >= 0.55


@pytest.mark.asyncio
async def test_rajasthan_penalizes_water_intensive_crops_and_keeps_arid_horticulture():
    recs = (await _engine_for("rajasthan")).calculate_recommendations()
    seasonal = {rec.crop_name: rec for rec in recs.seasonal}
    horticulture = {rec.crop_name: rec for rec in recs.horticulture}

    assert "Paddy(Dhan)(Common)" not in seasonal
    assert "Citrus" not in horticulture
    assert {"Date Palm", "Dragon Fruit", "Pomegranate"}.issubset(horticulture)


@pytest.mark.asyncio
async def test_maharashtra_previous_soybean_applies_family_penalty():
    no_history = await _engine_for("maharashtra")
    with_history = await _engine_for("maharashtra", previous_crop="Soybean")

    soy_no_history = no_history._calculate_suitability("Soyabean", CROP_DATABASE["Soyabean"])
    soy_with_history = with_history._calculate_suitability("Soyabean", CROP_DATABASE["Soyabean"])
    moong_no_history = no_history._calculate_suitability("Moong", CROP_DATABASE["Moong"])
    moong_with_history = with_history._calculate_suitability("Moong", CROP_DATABASE["Moong"])

    assert soy_no_history - soy_with_history == pytest.approx(0.15)
    assert moong_no_history - moong_with_history == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_bihar_high_rainfall_horticulture_and_ui_metadata():
    recs = (await _engine_for("bihar")).calculate_recommendations()
    horticulture_names = [rec.crop_name for rec in recs.horticulture]

    assert horticulture_names[:2] == ["Makhana", "Banana"]
    for rec in [*recs.seasonal, *recs.horticulture]:
        assert 0.0 <= rec.final_score <= 1.0
        assert rec.hex_color
        assert rec.action_plan
        assert "soil pH of" in rec.why_this_crop
        assert "Satellite soil moisture" in rec.why_this_crop
