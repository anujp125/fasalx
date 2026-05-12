from pydantic import BaseModel, Field
from typing import List, Optional

class WeatherResponse(BaseModel):
    temperature: float = Field(..., description="Current temperature in Celsius")
    humidity: float = Field(..., description="Current relative humidity percentage")
    precipitation: float = Field(..., description="Precipitation in mm")
    description: str = Field(..., description="Text description of the weather")

class CropStage(BaseModel):
    name: str = Field(..., description="Name of the stage (e.g., Sowing, Germination, Vegetative, Harvest)")
    duration_days: int = Field(..., description="Typical duration of this stage in days")
    instructions: str = Field(..., description="Agronomic advice for this stage")

class CropTemplate(BaseModel):
    crop_name: str = Field(..., description="Name of the crop (e.g., Wheat, Rice)")
    variety: Optional[str] = Field(None, description="Specific variety of the crop")
    total_duration_days: int = Field(..., description="Total lifecycle duration in days")
    stages: List[CropStage] = Field(..., description="Chronological list of crop stages")

class CropTimelineRequest(BaseModel):
    sowing_date: str = Field(..., description="ISO 8601 date string for when the crop was sown")
    crop_template_id: str = Field(..., description="ID of the crop template in Firestore")
