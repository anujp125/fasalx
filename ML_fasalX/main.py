import logging
from contextlib import asynccontextmanager
from typing import Annotated

import anyio
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ML_fasalX.core.config import settings
from ML_fasalX.core.docs import install_local_docs
from ML_fasalX.core.exceptions import MLServiceError
from ML_fasalX.core.logging import configure_logging
from ML_fasalX.schemas import HealthResponse, ModelsResponse, PredictionResponse
from ML_fasalX.services.prediction_service import prediction_service

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


def prediction_error_response(message: str) -> dict:
    return {
        "success": False,
        "disease": None,
        "confidence": 0,
        "top3": [],
        "error": message,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "ml_service_starting",
        extra={"models_dir": str(settings.MODELS_DIR), "environment": settings.ENVIRONMENT},
    )
    await anyio.to_thread.run_sync(prediction_service.warm_up_models)
    yield
    logger.info("ml_service_stopped")


app = FastAPI(
    title=settings.SERVICE_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    description="Crop disease inference microservice for FasalX.",
    docs_url=None,
    redoc_url=None,
)
install_local_docs(app)


@app.get("/")
async def root():
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "models": "/models",
            "predict": "/predict",
            "docs": "/docs",
        },
    }


@app.exception_handler(MLServiceError)
async def ml_service_error_handler(request: Request, exc: MLServiceError):
    logger.warning(
        "ml_service_error",
        extra={"path": request.url.path, "code": exc.code, "error": exc.message},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=prediction_error_response(exc.message),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "request_validation_error",
        extra={"path": request.url.path, "error": str(exc)},
    )
    return JSONResponse(
        status_code=422,
        content=prediction_error_response("Invalid request payload."),
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "models_dir": str(settings.MODELS_DIR),
        "model_count": len(prediction_service.list_models()),
    }


@app.get("/models", response_model=ModelsResponse)
async def models():
    return {"success": True, "models": prediction_service.list_models(), "error": None}


@app.post("/predict", response_model=PredictionResponse)
async def predict(
    crop_name: Annotated[str, Form(min_length=1)],
    image: Annotated[UploadFile, File(description="Crop leaf image.")],
):
    validate_upload_metadata(image)
    image_bytes = await read_upload_bytes(image)
    result = await anyio.to_thread.run_sync(
        prediction_service.predict_disease,
        crop_name,
        image_bytes,
    )
    return result


def validate_upload_metadata(image: UploadFile) -> None:
    content_type = (image.content_type or "").lower()
    if content_type not in settings.allowed_content_types:
        raise MLServiceError(
            message=f"Unsupported image content type '{content_type or 'unknown'}'.",
            code="UNSUPPORTED_MEDIA_TYPE",
            status_code=415,
        )


async def read_upload_bytes(image: UploadFile) -> bytes:
    max_bytes = settings.MAX_UPLOAD_BYTES
    chunks: list[bytes] = []
    total_size = 0

    while True:
        chunk = await image.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_bytes:
            raise MLServiceError(
                message=f"Image exceeds max upload size of {max_bytes} bytes.",
                code="PAYLOAD_TOO_LARGE",
                status_code=413,
            )
        chunks.append(chunk)

    if total_size == 0:
        raise MLServiceError(
            message="Image file is empty.",
            code="EMPTY_UPLOAD",
            status_code=400,
        )

    return b"".join(chunks)
