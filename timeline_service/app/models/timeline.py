from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime
from enum import Enum

class MilestoneType(str, Enum):
    MACRO = "macro"
    MICRO = "micro"

class MilestoneStatus(str, Enum):
    COMPLETED = "completed"
    PREDICTED = "predicted"
    ALERT = "alert"

class GeoLocation(BaseModel):
    type: str = Field(default="Point")
    # Strict longitudinal [-180, 180] and latitudinal [-90, 90] constraints
    coordinates: List[float] = Field(..., description="[longitude, latitude]", min_length=2, max_length=2)

class UserMetadata(BaseModel):
    user_id: str
    crop_id: str
    sowing_date: datetime
    location: GeoLocation
    t_base: float = Field(default=10.0, description="Base temperature for crop GDD calculation")

class LifecycleState(BaseModel):
    current_stage: str
    progress_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    total_gdd: float = Field(default=0.0, description="Accumulated Growing Degree Days")

class Milestone(BaseModel):
    name: str
    type: MilestoneType
    status: MilestoneStatus
    target_gdd: Optional[float] = None
    trigger_logic: Optional[str] = None
    predicted_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in the milestone prediction (1.0 = IoT, 0.8 = API, 0.5 = Satellite)")

class EnvironmentalSnapshot(BaseModel):
    last_updated: datetime
    # Realistic agricultural constraints: -50C to 60C
    t_max: Optional[float] = Field(default=None, ge=-50.0, le=60.0)
    t_min: Optional[float] = Field(default=None, ge=-50.0, le=60.0)
    soil_moisture: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    source: str = Field(default="satellite", description="e.g., 'iot', 'api', 'satellite'")
    weight: float = Field(default=0.5, description="Data Quality Weight (0.0 to 1.0)", ge=0.0, le=1.0)

class UserCropTimeline(BaseModel):
    id: Optional[str] = Field(alias="_id", default=None)
    user_metadata: UserMetadata
    lifecycle_state: LifecycleState
    milestone_map: List[Milestone]
    environmental_snapshot: EnvironmentalSnapshot
    
    class Config:
        populate_by_name = True
