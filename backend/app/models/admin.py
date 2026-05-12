from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class AdminAccess(BaseModel):
    role: str = Field(..., description="Trusted admin role from Firebase custom claims")
    permissions: List[str] = Field(default_factory=list, description="Effective admin permissions")


class AdminAuthResponse(BaseModel):
    uid: str
    email: Optional[str] = None
    display_name: str
    is_active: bool = True
    access: AdminAccess


class AdminSyncResponse(BaseModel):
    message: str
    admin: AdminAuthResponse


class AdminLogoutResponse(BaseModel):
    message: str


class SuitabilityWeights(BaseModel):
    npk_match: float = Field(default=0.30, ge=0, le=1)
    ph_match: float = Field(default=0.10, ge=0, le=1)
    rainfall_match: float = Field(default=0.15, ge=0, le=1)
    gdd_match: float = Field(default=0.20, ge=0, le=1)
    ndvi_crop_health: float = Field(default=0.15, ge=0, le=1)
    oc_ec_soil_match: float = Field(default=0.10, ge=0, le=1)

    @model_validator(mode="after")
    def validate_total_weight(self):
        total = (
            self.npk_match
            + self.ph_match
            + self.rainfall_match
            + self.gdd_match
            + self.ndvi_crop_health
            + self.oc_ec_soil_match
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError("Suitability weights must total 1.0")
        return self


class RecommendationSystemConfig(BaseModel):
    enable_dynamic_suitability: bool = True
    enable_gdd_scoring: bool = True
    enable_ndvi_crop_health: bool = True
    enable_oc_ec_soil_match: bool = True
    enable_dynamic_horticulture_profitability: bool = True
    enable_crop_msp_collection: bool = True
    use_rainfall_as_gdd_proxy: bool = True
    gdd_rainfall_proxy_factor: float = Field(default=2.5, gt=0)
    default_oc_min: float = Field(default=0.50, ge=0)
    default_oc_max: float = Field(default=0.75, ge=0)
    suitability_weights: SuitabilityWeights = Field(default_factory=SuitabilityWeights)


class SystemConfig(BaseModel):
    scope: str = "global"
    recommendation: RecommendationSystemConfig = Field(default_factory=RecommendationSystemConfig)
    msp_refresh_cron: str = Field(default="0 3 15 12 *", description="Annual MSP refresh cron in UTC")
    msp_refresh_source: str = "PIB/CACP government MSP filings"
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class SystemConfigUpdate(BaseModel):
    recommendation: Optional[RecommendationSystemConfig] = None
    msp_refresh_cron: Optional[str] = None
    msp_refresh_source: Optional[str] = None
