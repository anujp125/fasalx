from pydantic import BaseModel, Field


class TopPrediction(BaseModel):
    disease: str
    confidence: float = Field(ge=0, le=100)


class PredictionResponse(BaseModel):
    success: bool
    disease: str | None = None
    confidence: float = Field(default=0, ge=0, le=100)
    top3: list[TopPrediction] = Field(default_factory=list)
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    models_dir: str
    model_count: int


class ModelsResponse(BaseModel):
    success: bool = True
    models: list[dict]
    error: str | None = None

