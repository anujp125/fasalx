from pydantic import BaseModel, Field
from typing import Optional, List

class RecommendationRequest(BaseModel):
    field_id: str = Field(..., description="The unique ID of the field to get recommendations for")
    target_season: Optional[str] = Field(None, description="Optional target season (Kharif/Rabi)")

class ScoreBreakdown(BaseModel):
    suitability_score: float = Field(..., description="Raw Suitability Score (S) from 0.0 to 1.0")
    profitability_score: float = Field(..., description="Raw Profitability Score (P) from 0.0 to 1.0")

class ActionStep(BaseModel):
    task: str
    month: str

class RecommendationResponse(BaseModel):
    id: Optional[str] = Field(None, description="Unique session ID linked to MongoDB")
    crop_name: str
    type: str = Field(..., description="seasonal or horticulture")
    gestation_period: Optional[int] = Field(None, description="Months before first harvest (for horticulture)")
    investment_lifespan: Optional[int] = Field(None, description="Years of productive lifespan (for horticulture)")
    final_score: float
    category: str
    why_this_crop: str
    breakdown: ScoreBreakdown
    hex_color: Optional[str] = None
    icon_slug: Optional[str] = None
    action_priority: Optional[int] = None
    action_plan: List[ActionStep] = Field(default_factory=list, description="3-step Agri-Calendar timeline")

class DualRecommendationResponse(BaseModel):
    seasonal: List[RecommendationResponse]
    horticulture: List[RecommendationResponse]

class RecommendationSelectRequest(BaseModel):
    field_id: str
    recommendation_id: str
    crop_name: str
