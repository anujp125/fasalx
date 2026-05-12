from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


DEFAULT_DASHBOARD_COMPONENTS = {
    "weather": True,
    "mandi_prices": True,
    "iot_data": True,
    "expense_ledger": True,
    "timeline": True,
    "recommendation": True,
    "chatbot_button": True,
}


class DashboardComponentVisibility(BaseModel):
    weather: bool = True
    mandi_prices: bool = True
    iot_data: bool = True
    expense_ledger: bool = True
    timeline: bool = True
    recommendation: bool = True
    chatbot_button: bool = True


class DashboardVisibilityResponse(BaseModel):
    scope: str = "global"
    components: DashboardComponentVisibility
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


class DashboardVisibilityUpdate(BaseModel):
    components: DashboardComponentVisibility


class DashboardComponentToggleRequest(BaseModel):
    component: str = Field(..., min_length=1)
    visible: bool


class DashboardComponentToggleResponse(BaseModel):
    message: str
    config: DashboardVisibilityResponse
