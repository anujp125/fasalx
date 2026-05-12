import datetime
import logging
from typing import Any, Dict, List, Optional

from app.db.mongodb import get_mongo_db
from app.engine.ingestors.market import get_market_data, get_msp_trend
from app.engine.knowledge_base import CROP_DATABASE, CROP_SOIL_MATCH_OVERRIDES, SOIL_MATCH_DEFAULTS
from app.engine.models.ingestion import FieldIntelligence
from app.engine.models.recommendation import (
    ActionStep,
    DualRecommendationResponse,
    RecommendationResponse,
    ScoreBreakdown,
)
from app.models.admin import SystemConfig

logger = logging.getLogger(__name__)


HORTICULTURE_STAPLE_BENCHMARKS = {
    "banana": ["Paddy(Dhan)(Common)", "Maize"],
    "dragon fruit": ["Maize", "Soyabean"],
    "date palm": ["Wheat", "Barley"],
    "citrus": ["Maize", "Wheat"],
    "pomegranate": ["Wheat", "Gram"],
    "makhana": ["Paddy(Dhan)(Common)", "Moong"],
}


class RecommendationEngine:
    def __init__(
        self,
        intelligence: FieldIntelligence,
        satellite_data: dict,
        target_season: Optional[str] = None,
        previous_crop: Optional[str] = None,
        system_config: Optional[SystemConfig] = None,
        timeline_cache: Optional[List[dict]] = None,
    ):
        self.weather = intelligence.weather
        self.soil = intelligence.soil
        self.market = intelligence.market
        self.satellite_data = satellite_data or {}
        self.target_season = target_season or self._infer_season()
        self.previous_crop = self._resolve_crop_key(previous_crop)
        self.system_config = system_config or SystemConfig()
        self._timeline_cache = timeline_cache or []

    def _resolve_crop_key(self, crop_name: Optional[str]) -> Optional[str]:
        if not crop_name:
            return None
        aliases = {
            "soybean": "Soyabean",
            "soyabean": "Soyabean",
            "paddy": "Paddy(Dhan)(Common)",
            "rice": "Paddy(Dhan)(Common)",
            "mustard": "Mustard",
            "rapeseed & mustard": "Mustard",
            "tur": "Arhar",
            "arhar": "Arhar",
        }
        normalized = crop_name.strip().lower()
        if normalized in aliases:
            return aliases[normalized]
        for known_crop in CROP_DATABASE:
            if known_crop.lower() == normalized:
                return known_crop
        return crop_name

    def _infer_season(self) -> str:
        month = datetime.datetime.now().month
        if 4 <= month <= 9:
            return "Kharif"
        return "Rabi"

    def _range_match(self, value: float, ideal_min: float, ideal_max: float) -> float:
        if ideal_min <= value <= ideal_max:
            return 1.0
        if value < ideal_min:
            distance = (ideal_min - value) / max(ideal_min, 1.0)
        else:
            distance = (value - ideal_max) / max(ideal_max, 1.0)
        return max(0.0, 1.0 - distance)

    def _estimate_seasonal_gdd(self) -> float:
        if not self.weather:
            return 0.0

        cumulative_gdd = getattr(self.weather, "gdd_cumulative", None)
        if cumulative_gdd is not None:
            return float(cumulative_gdd)

        daily_gdd = getattr(self.weather, "gdd", None)
        if daily_gdd is not None:
            return float(daily_gdd) * 120.0

        if not self.system_config.recommendation.use_rainfall_as_gdd_proxy:
            return 0.0
        rainfall = float(getattr(self.weather, "rainfall_history_12m", 0.0) or 0.0)
        return rainfall * self.system_config.recommendation.gdd_rainfall_proxy_factor

    def _npk_match(self, ideal: dict) -> float:
        n_match = max(0.0, 1.0 - abs(self.soil.N - ideal["N"]) / max(ideal["N"], 1.0))
        p_match = max(0.0, 1.0 - abs(self.soil.P - ideal["P"]) / max(ideal["P"], 1.0))
        k_match = max(0.0, 1.0 - abs(self.soil.K - ideal["K"]) / max(ideal["K"], 1.0))
        return (n_match + p_match + k_match) / 3.0

    def _ph_match(self, ideal: dict) -> float:
        return self._range_match(self.soil.pH, ideal["pH_min"], ideal["pH_max"])

    def _ndvi_match(self, db_data: dict) -> float:
        ndvi = self.satellite_data.get("ndvi")
        if ndvi is None:
            return 0.5

        ndvi = max(0.0, min(float(ndvi), 1.0))
        if ndvi < 0.15:
            match = 0.15
        elif ndvi < 0.35:
            match = 0.45
        elif ndvi < 0.55:
            match = 0.75
        else:
            match = 1.0

        moisture = self.satellite_data.get("soil_moisture")
        if moisture is not None and float(moisture) < 0.3 and db_data.get("water_intensive", False):
            match -= 0.20
        return max(0.0, min(match, 1.0))

    def _oc_ec_match(self, crop_name: str, db_data: dict) -> float:
        ideal = db_data["ideal"]
        survival = db_data["survival"]

        soil_match = {
            **SOIL_MATCH_DEFAULTS,
            **CROP_SOIL_MATCH_OVERRIDES.get(crop_name, {}),
        }
        oc_min = ideal.get("oc_min", soil_match.get("oc_min", self.system_config.recommendation.default_oc_min))
        oc_max = ideal.get("oc_max", soil_match.get("oc_max", self.system_config.recommendation.default_oc_max))
        ec_min = ideal.get("ec_min", soil_match.get("ec_min", 0.0))
        ec_max = ideal.get("ec_max", min(survival.get("ec_max", 4.0), soil_match.get("ec_max", 1.2)))

        oc_match = self._range_match(self.soil.OC, oc_min, oc_max)
        ec_match = self._range_match(self.soil.EC, ec_min, ec_max)
        return (oc_match + ec_match) / 2.0

    def _calculate_suitability(self, crop_name: str, db_data: dict) -> float:
        if not self.soil or not self.weather:
            return 0.5

        survival = db_data["survival"]
        ideal = db_data["ideal"]

        if self.soil.pH < survival["pH_min"] or self.soil.pH > survival["pH_max"]:
            return 0.0
        if self.soil.EC > survival.get("ec_max", 4.0):
            return 0.0

        rainfall_12m = float(getattr(self.weather, "rainfall_history_12m", 0.0) or 0.0)
        seasonal_gdd = self._estimate_seasonal_gdd()

        config = self.system_config.recommendation
        weights = config.suitability_weights
        npk_match = self._npk_match(ideal)
        ph_match = self._ph_match(ideal)
        rain_match = self._range_match(rainfall_12m, ideal["rain_min"], ideal["rain_max"])
        gdd_match = self._range_match(
            seasonal_gdd,
            ideal.get("gdd_min", survival.get("gdd_min", 0.0)),
            ideal.get("gdd_max", survival.get("gdd_max", 9999.0)),
        )
        ndvi_match = self._ndvi_match(db_data)
        oc_ec_match = self._oc_ec_match(crop_name, db_data)

        if not config.enable_dynamic_suitability:
            gdd_match = 0.5
            ndvi_match = 0.5
            oc_ec_match = 0.5
        if not config.enable_gdd_scoring:
            gdd_match = 0.5
        if not config.enable_ndvi_crop_health:
            ndvi_match = 0.5
        if not config.enable_oc_ec_soil_match:
            oc_ec_match = 0.5

        suitability = (
            npk_match * weights.npk_match
            + ph_match * weights.ph_match
            + rain_match * weights.rainfall_match
            + gdd_match * weights.gdd_match
            + ndvi_match * weights.ndvi_crop_health
            + oc_ec_match * weights.oc_ec_soil_match
        )

        previous_crop = self.previous_crop
        prev_data = CROP_DATABASE.get(previous_crop) if previous_crop else None
        if prev_data:
            if db_data["family"] == prev_data["family"]:
                suitability -= 0.15
            if prev_data["is_nitrogen_fixer"] and db_data["family"] == "Poaceae":
                suitability += 0.10

        moisture = self.satellite_data.get("soil_moisture")
        if moisture is not None:
            moisture = float(moisture)
            if moisture < 0.3:
                suitability += -0.10 if db_data.get("water_intensive", False) else 0.03
            elif moisture > 0.65:
                suitability += 0.04 if db_data.get("water_intensive", False) else -0.03

        if rainfall_12m < ideal["rain_min"] and db_data.get("water_intensive", False):
            suitability -= 0.10
        elif rainfall_12m > ideal["rain_max"] * 1.25 and not db_data.get("water_intensive", False):
            suitability -= 0.06

        return min(max(suitability, 0.0), 1.0)

    async def _calculate_profitability(self, crop_name: str, db_data: dict) -> float:
        if db_data["type"] == "horticulture":
            return await self._horticulture_profitability(crop_name)

        if not self.market:
            return 0.5

        commodity = self._find_market_commodity(crop_name)
        if not commodity:
            return 0.5

        if commodity.profitability_index is not None:
            return self._score_from_profitability_index(commodity.profitability_index)

        if commodity.historical_trend_percent is not None:
            return self._score_from_trend(commodity.historical_trend_percent)
        return 0.5

    def _calculate_profitability_from_cached_market(self, crop_name: str, db_data: dict) -> float:
        if not self.market:
            return 0.5

        commodity = self._find_market_commodity(crop_name)
        if not commodity:
            return 0.5 if db_data["type"] == "horticulture" else 0.5

        if commodity.profitability_index is not None:
            return self._score_from_profitability_index(commodity.profitability_index)
        if commodity.historical_trend_percent is not None:
            return self._score_from_trend(commodity.historical_trend_percent)

        if db_data["type"] == "horticulture":
            return 0.55 if commodity.modal_price else 0.5
        return 0.5

    def _score_from_profitability_index(self, index: float) -> float:
        if index <= -20.0:
            return 0.0
        if index >= 50.0:
            return 1.0
        if index < 0:
            return 0.5 - (abs(index) / 20.0) * 0.5
        return 0.5 + (index / 50.0) * 0.5

    def _score_from_trend(self, trend: float) -> float:
        if trend <= 0.0:
            return 0.20
        if trend >= 15.0:
            return 0.90
        return min(max(0.30 + (trend / 15.0) * 0.60, 0.20), 0.90)

    def _score_modal_price_against_benchmark(self, modal_price: float, benchmark_msp: Optional[float]) -> float:
        if not modal_price or not benchmark_msp:
            return 0.5
        ratio = modal_price / benchmark_msp
        if ratio <= 0.7:
            return 0.25
        if ratio >= 2.5:
            return 0.9
        return min(max(0.25 + ((ratio - 0.7) / 1.8) * 0.65, 0.25), 0.9)

    async def _horticulture_profitability(self, crop_name: str) -> float:
        if not self.system_config.recommendation.enable_dynamic_horticulture_profitability:
            return 0.5

        live_commodity = self._find_market_commodity(crop_name) if self.market else None
        if live_commodity is None and self.market:
            try:
                market_data = await get_market_data(
                    state=self.market.state,
                    market=self.market.market,
                    commodity=crop_name,
                )
                live_commodity = self._find_market_commodity(crop_name, market_data.commodities)
            except Exception as exc:
                logger.warning(
                    "horticulture_apmc_lookup_failed",
                    extra={"crop": crop_name, "error": str(exc)},
                )

        if live_commodity:
            if live_commodity.profitability_index is not None:
                return self._score_from_profitability_index(live_commodity.profitability_index)
            if live_commodity.historical_trend_percent is not None:
                return self._score_from_trend(live_commodity.historical_trend_percent)
            benchmark_msp = await self._related_staple_msp_benchmark(crop_name)
            return self._score_modal_price_against_benchmark(live_commodity.modal_price, benchmark_msp)

        fruit_trend = await self._historical_horticulture_trend(crop_name)
        staple_trend = await self._related_staple_msp_trend(crop_name)
        if fruit_trend is not None:
            relative_trend = fruit_trend - (staple_trend or 0.0)
            return self._score_from_trend(relative_trend)

        return 0.5

    async def _related_staple_msp_benchmark(self, crop_name: str) -> Optional[float]:
        staples = HORTICULTURE_STAPLE_BENCHMARKS.get(crop_name.lower(), ["Wheat", "Maize"])
        values = []
        for staple in staples:
            trend = await get_msp_trend(staple)
            if trend.get("current_msp"):
                values.append(float(trend["current_msp"]))
        if not values:
            return None
        return sum(values) / len(values)

    async def _related_staple_msp_trend(self, crop_name: str) -> Optional[float]:
        staples = HORTICULTURE_STAPLE_BENCHMARKS.get(crop_name.lower(), ["Wheat", "Maize"])
        values = []
        for staple in staples:
            trend = await get_msp_trend(staple)
            if trend.get("growth_trend") is not None:
                values.append(float(trend["growth_trend"]))
        if not values:
            return None
        return sum(values) / len(values)

    async def _historical_horticulture_trend(self, crop_name: str) -> Optional[float]:
        db = get_mongo_db()
        if db is None:
            return None

        query = {"crop_name": {"$regex": f"^{crop_name}$", "$options": "i"}}
        for collection_name in ("horticulture_price_history", "market_price_history"):
            cursor = (
                db[collection_name]
                .find(query)
                .sort([("date", -1), ("year", -1), ("created_at", -1)])
                .limit(24)
            )
            records = [doc async for doc in cursor]
            if len(records) < 2:
                continue

            latest = self._extract_price(records[0])
            oldest = self._extract_price(records[-1])
            if latest and oldest and oldest > 0:
                return round(((latest - oldest) / oldest) * 100.0, 2)
        return None

    def _extract_price(self, record: dict) -> Optional[float]:
        for key in ("modal_price", "avg_modal_price", "price", "historical_avg_price"):
            value = record.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
        return None

    def _find_market_commodity(self, crop_name: str, commodities: Optional[list] = None):
        aliases = {
            "banana": {"banana", "kela"},
            "citrus": {"citrus", "orange", "mosambi", "sweet lime", "lemon"},
            "cotton": {"cotton", "kapas"},
            "dragon fruit": {"dragon fruit", "pitaya"},
            "gram": {"gram", "chana"},
            "makhana": {"makhana", "fox nut"},
            "mustard": {"mustard", "mustard seed", "rmseed", "rapeseed & mustard"},
            "onion": {"onion", "pyaz", "kanda"},
            "paddy(dhan)(common)": {"paddy(dhan)(common)", "paddy", "rice"},
            "pomegranate": {"pomegranate", "anar"},
            "potato": {"potato", "aloo"},
            "soyabean": {"soyabean", "soybean"},
            "tomato": {"tomato", "tamatar"},
            "maize": {"maize", "maize feed industrial grade"},
        }
        normalized = crop_name.strip().lower()
        candidates = aliases.get(normalized, {normalized})
        source = commodities if commodities is not None else (self.market.commodities if self.market else [])
        for commodity in source:
            values = {
                str(commodity.commodity or "").strip().lower(),
                str(commodity.symbol or "").strip().lower(),
            }
            if values & candidates:
                return commodity
        return None

    def _generate_reasoning(self, crop_name: str, s_score: float, p_score: float, category: str, ideal: dict) -> str:
        reasons = []
        if self.soil and ideal["pH_min"] <= self.soil.pH <= ideal["pH_max"]:
            reasons.append(f"Your soil pH of {self.soil.pH} is perfect for {crop_name}.")
        elif self.soil:
            reasons.append(f"Your soil pH of {self.soil.pH} is acceptable.")

        if self.soil:
            if self.soil.OC > self.system_config.recommendation.default_oc_max:
                reasons.append(f"High organic carbon ({self.soil.OC}%) provides a fertile foundation.")
            elif self.soil.OC < self.system_config.recommendation.default_oc_min:
                reasons.append(f"Low organic carbon ({self.soil.OC}%). Consider adding organic matter.")

        moisture = self.satellite_data.get("soil_moisture")
        if moisture is not None:
            moisture_pct = round(float(moisture) * 100)
            if moisture < 0.3:
                reasons.append(f"Satellite soil moisture is low at {moisture_pct}%.")
            elif moisture > 0.65:
                reasons.append(f"Satellite soil moisture is high at {moisture_pct}%.")
            else:
                reasons.append(f"Satellite soil moisture is moderate at {moisture_pct}%.")

        ndvi = self.satellite_data.get("ndvi")
        if ndvi is not None:
            src = self.satellite_data.get("source", "")
            label = " (Sentinel-2)" if "sentinel" in src else ""
            if ndvi < 0.15:
                reasons.append(f"NDVI{label} is very low ({ndvi}), indicating bare or stressed land.")
            elif ndvi < 0.35:
                reasons.append(f"NDVI{label} is moderate ({ndvi}), suggesting sparse vegetation.")
            else:
                reasons.append(f"NDVI{label} of {ndvi} indicates healthy vegetation cover.")

        if self.weather:
            rain = round(self.weather.rainfall_history_12m)
            if rain < ideal["rain_min"]:
                reasons.append(f"Last-12-month rainfall of {rain} mm is below this crop's ideal range.")
            elif rain > ideal["rain_max"]:
                reasons.append(f"Last-12-month rainfall of {rain} mm is above this crop's ideal range.")
            else:
                reasons.append(f"Last-12-month rainfall of {rain} mm fits this crop's ideal range.")

            gdd_proxy = round(self._estimate_seasonal_gdd())
            gdd_min = ideal.get("gdd_min", 0)
            gdd_max = ideal.get("gdd_max", 9999)
            if gdd_min <= gdd_proxy <= gdd_max:
                reasons.append(f"Estimated seasonal GDD of {gdd_proxy} is within this crop's range.")
            elif gdd_proxy < gdd_min:
                reasons.append(f"Estimated seasonal GDD of {gdd_proxy} is below this crop's requirement.")
            else:
                reasons.append(f"Estimated seasonal GDD of {gdd_proxy} may be too high for this crop.")

        if p_score > 0.6:
            reasons.append("Current market signals are profitable.")
        elif p_score < 0.4:
            reasons.append("Market returns are currently below average.")

        market_commodity = self._find_market_commodity(crop_name) if self.market else None
        if market_commodity and market_commodity.historical_trend_percent is not None:
            trend = round(market_commodity.historical_trend_percent, 1)
            if trend > 0:
                reasons.append(f"MSP or price trend has grown {trend}% recently, improving market security.")
            elif trend < 0:
                reasons.append(f"MSP or price trend has declined by {abs(trend)}% recently, adding market risk.")

        if category == "The Soil Builder":
            reasons.append(f"As a legume, {crop_name} will naturally fix atmospheric nitrogen.")

        return " ".join(reasons)

    def _generate_action_plan(self, crop_name: str, db_data: dict) -> List[ActionStep]:
        """
        Generates a crop action plan. For crops with state-specific timeline data
        in MongoDB (horticulture_crop_timeline), uses that data. Otherwise falls
        back to the static sowing_window from the knowledge base.
        """
        # Try state-specific timeline from in-memory cache (populated at init)
        timeline = self._get_state_timeline(crop_name)

        if timeline:
            steps = []
            if timeline.get("sowing"):
                steps.append(ActionStep(task="Sowing / Nursery Preparation", month=timeline["sowing"]))
            if timeline.get("transplanting"):
                steps.append(ActionStep(task="Transplanting", month=timeline["transplanting"]))
            steps.append(ActionStep(task="Crop Management & Irrigation", month="Ongoing"))
            if timeline.get("harvesting"):
                steps.append(ActionStep(task="Harvesting", month=timeline["harvesting"]))
            return steps if steps else self._fallback_action_plan(db_data)

        return self._fallback_action_plan(db_data)

    def _fallback_action_plan(self, db_data: dict) -> List[ActionStep]:
        sowing = db_data["sowing_window"][0] if db_data["sowing_window"] else "Unknown"
        return [
            ActionStep(task="Soil Preparation", month=sowing),
            ActionStep(task="Sowing & Basal Fertilizer", month=sowing),
            ActionStep(task="First Irrigation / Weed Management", month="1 month later"),
        ]

    def _get_state_timeline(self, crop_name: str) -> Optional[dict]:
        """
        Looks up the state-specific crop timeline from the in-memory cache.
        Priority: exact state + season match > any state match for the season.
        """
        if not hasattr(self, '_timeline_cache'):
            return None

        user_state = self.market.state if self.market else None
        season = self.target_season

        # Exact match: crop + state + season
        if user_state:
            for entry in self._timeline_cache:
                if (entry["crop_name"].lower() == crop_name.lower()
                        and entry["state"].lower() == user_state.lower()
                        and entry["season"].lower() == season.lower()):
                    return entry

        # Fallback: crop + season (any state — use first match)
        for entry in self._timeline_cache:
            if (entry["crop_name"].lower() == crop_name.lower()
                    and entry["season"].lower() == season.lower()):
                return entry

        return None

    def _build_response(self, scored_crops: list[dict]) -> DualRecommendationResponse:
        scored_crops.sort(key=lambda x: x["final"], reverse=True)

        seasonal_list = []
        horticulture_list = []
        family_counts = {}
        categories_assigned = set()

        ui_meta = {
            "The Legend": {"icon": "emoji_events", "color": "#FFD700"},
            "The Safe Bet": {"icon": "security", "color": "#1976D2"},
            "The Gold Mine": {"icon": "trending_up", "color": "#FB8C00"},
            "The Soil Builder": {"icon": "eco", "color": "#43A047"},
            "General Pick": {"icon": "agriculture", "color": "#757575"},
        }

        for item in scored_crops:
            crop_name = item["crop"]
            family = item["data"]["family"]
            ctype = item["data"]["type"]

            if ctype == "seasonal":
                if len(seasonal_list) >= 5:
                    continue
                if family_counts.get(family, 0) >= 2:
                    continue
                family_counts[family] = family_counts.get(family, 0) + 1
            elif ctype == "horticulture" and len(horticulture_list) >= 3:
                continue

            category = "General Pick"
            if "The Legend" not in categories_assigned:
                category = "The Legend"
                categories_assigned.add("The Legend")
            elif item["data"]["is_nitrogen_fixer"] and "The Soil Builder" not in categories_assigned:
                category = "The Soil Builder"
                categories_assigned.add("The Soil Builder")
            elif item["p"] > 0.8 and "The Gold Mine" not in categories_assigned:
                category = "The Gold Mine"
                categories_assigned.add("The Gold Mine")
            elif item["s"] > 0.85 and "The Safe Bet" not in categories_assigned:
                category = "The Safe Bet"
                categories_assigned.add("The Safe Bet")

            meta = ui_meta.get(category, ui_meta["General Pick"])
            reasoning = self._generate_reasoning(crop_name, item["s"], item["p"], category, item["data"]["ideal"])
            action_plan = self._generate_action_plan(crop_name, item["data"])

            resp = RecommendationResponse(
                crop_name=crop_name,
                type=ctype,
                gestation_period=item["data"].get("gestation_period"),
                investment_lifespan=item["data"].get("investment_lifespan"),
                final_score=round(item["final"], 3),
                category=category,
                why_this_crop=reasoning,
                breakdown=ScoreBreakdown(
                    suitability_score=round(item["s"], 3),
                    profitability_score=round(item["p"], 3),
                ),
                hex_color=meta["color"],
                icon_slug=meta["icon"],
                action_priority=len(seasonal_list) + 1 if ctype == "seasonal" else len(horticulture_list) + 1,
                action_plan=action_plan,
            )

            if ctype == "seasonal":
                seasonal_list.append(resp)
            else:
                horticulture_list.append(resp)

        return DualRecommendationResponse(seasonal=seasonal_list, horticulture=horticulture_list)

    def calculate_recommendations(self) -> DualRecommendationResponse:
        scored_crops = []

        for crop_name, db_data in CROP_DATABASE.items():
            if (
                db_data["type"] == "seasonal"
                and db_data["season"] != self.target_season
                and db_data["season"] != "All"
            ):
                continue

            s_score = self._calculate_suitability(crop_name, db_data)
            p_score = self._calculate_profitability_from_cached_market(crop_name, db_data)

            if s_score < 0.15:
                continue

            final_score = (s_score * 0.6) + (p_score * 0.4)
            scored_crops.append(
                {
                    "crop": crop_name,
                    "data": db_data,
                    "s": s_score,
                    "p": p_score,
                    "final": final_score,
                }
            )

        return self._build_response(scored_crops)

    async def calculate_recommendations_async(self) -> DualRecommendationResponse:
        scored_crops = []

        for crop_name, db_data in CROP_DATABASE.items():
            if (
                db_data["type"] == "seasonal"
                and db_data["season"] != self.target_season
                and db_data["season"] != "All"
            ):
                continue

            s_score = self._calculate_suitability(crop_name, db_data)
            p_score = await self._calculate_profitability(crop_name, db_data)

            if s_score < 0.15:
                continue

            final_score = (s_score * 0.6) + (p_score * 0.4)
            scored_crops.append(
                {
                    "crop": crop_name,
                    "data": db_data,
                    "s": s_score,
                    "p": p_score,
                    "final": final_score,
                }
            )

        return self._build_response(scored_crops)
