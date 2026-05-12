from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class WeatherData(BaseModel):
    temperature_min: float = Field(..., description="Minimum temperature in Celsius")
    temperature_max: float = Field(..., description="Maximum temperature in Celsius")
    humidity: float = Field(..., description="Current relative humidity percentage")
    rainfall_current: float = Field(..., description="Current precipitation in mm")
    rainfall_history_12m: float = Field(..., description="Total rainfall over the last 12 months in mm")
    gdd: float = Field(..., description="Growing Degree Days calculated with base 10C")
    description: Optional[str] = Field(None, description="General weather description")

class SoilData(BaseModel):
    # Macronutrients
    N: float = Field(..., description="Nitrogen (kg/ha)")
    P: float = Field(..., description="Phosphorus (kg/ha)")
    K: float = Field(..., description="Potassium (kg/ha)")
    # Secondary Nutrients
    S: float = Field(..., description="Sulphur (ppm)")
    # Micronutrients
    Zn: float = Field(..., description="Zinc (ppm)")
    Fe: float = Field(..., description="Iron (ppm)")
    Cu: float = Field(..., description="Copper (ppm)")
    Mn: float = Field(..., description="Manganese (ppm)")
    B: float = Field(..., description="Boron (ppm)")
    # Physical Parameters
    pH: float = Field(..., description="Soil pH value")
    EC: float = Field(..., description="Electrical Conductivity (dS/m)")
    OC: float = Field(..., description="Organic Carbon (%)")
    
    source: str = Field(..., description="Origin of data: 'shc_simulation' or 'district_average'")

class CommodityPrice(BaseModel):
    commodity: str
    modal_price: float
    msp: Optional[float]
    profitability_index: Optional[float] = Field(None, description="Percentage difference between Modal Price and MSP")
    source: Optional[str] = Field(None, description="Origin of the price, e.g. data_gov")
    symbol: Optional[str] = None
    contract_expiry: Optional[str] = None
    spot_price: Optional[float] = None
    historical_avg_price: Optional[float] = None
    historical_trend_percent: Optional[float] = None
    price_timestamp: Optional[str] = None

class MarketData(BaseModel):
    state: str
    market: str
    commodities: List[CommodityPrice]
    source: Optional[str] = None

class FieldIntelligence(BaseModel):
    coordinates: Dict[str, float]
    weather: Optional[WeatherData]
    soil: Optional[SoilData]
    market: Optional[MarketData]
    errors: Optional[Dict[str, str]] = Field(default_factory=dict, description="Captures any service failures")
