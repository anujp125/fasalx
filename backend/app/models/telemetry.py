from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class IoTDevicePayload(BaseModel):
    device_id: str = Field(..., description="Unique identifier for the sensor device")
    moisture: float = Field(..., ge=0, le=100, description="Soil moisture percentage (0-100)")
    temperature: float = Field(..., description="Soil temperature in Celsius")
    ph: Optional[float] = Field(None, ge=0, le=14, description="Soil pH level (0-14)")
    nitrogen: Optional[float] = Field(None, description="Nitrogen level in mg/kg")
    phosphorus: Optional[float] = Field(None, description="Phosphorus level in mg/kg")
    potassium: Optional[float] = Field(None, description="Potassium level in mg/kg")
    # We will attach the timestamp server-side if not provided
    timestamp: Optional[datetime] = None
