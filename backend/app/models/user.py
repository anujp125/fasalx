from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

class Location(BaseModel):
    latitude: float
    longitude: float

class FarmerProfile(BaseModel):
    display_name: str = Field(..., description="Full name of the farmer")
    preferred_language: str = Field(default="en", description="Language code (e.g., 'hi', 'en', 'mr')")
    location: Optional[Location] = None
    farm_size_acres: Optional[float] = Field(None, description="Total area of the farm in acres")
    role: str = Field(default="farmer", description="Role of the user (e.g., 'farmer', 'admin')")
    avatar_url: Optional[str] = Field(None, description="URL to the user's profile picture")
    phone_number: Optional[str] = Field(None, description="User's phone number")
    is_active: bool = Field(default=True, description="Whether the user account is active")

class UserActivity(BaseModel):
    user_id: str = Field(..., description="Firebase UID of the user")
    action: str = Field(..., description="Action performed (e.g., LOGIN, LOGOUT, PROFILE_UPDATE)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional context about the action")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Time the action occurred")
