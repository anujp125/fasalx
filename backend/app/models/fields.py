from pydantic import BaseModel, Field
from typing import Optional, List

class FieldRegistrationRequest(BaseModel):
    name: str = Field(..., description="Custom name for the field (e.g., 'North Hill Plot')")
    lat: float = Field(..., description="Latitude of the field", ge=-90.0, le=90.0)
    lon: float = Field(..., description="Longitude of the field", ge=-180.0, le=180.0)
    area: float = Field(..., description="Total area of the field in acres", gt=0.0)

class FieldResponse(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    area: float
    selected_crop: Optional[str] = None

class FarmOverviewResponse(BaseModel):
    total_fields: int
    total_area_acres: float
    estimated_gross_revenue: float
    estimated_total_cost: float
    estimated_net_profit: float
    active_crops: List[str]
