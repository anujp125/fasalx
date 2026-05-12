import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import disease, ingest, recommend
from app.core.config import settings
from app.core.docs import install_local_docs
from app.core.exceptions import AppError
from app.core.firebase import init_firebase
from app.db.mongodb import close_mongo, init_mongo
from app.db.redis import close_redis, init_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FasalX Recommendation Engine...")
    init_firebase()
    await init_redis()
    await init_mongo()
    yield
    logger.info("Shutting down FasalX Recommendation Engine...")
    await close_mongo()
    await close_redis()


app = FastAPI(
    title="FasalX Recommendation Engine",
    version=settings.VERSION,
    lifespan=lifespan,
    description="Field intelligence, crop recommendation, and crop disease inference APIs for FasalX.",
    docs_url=None,
    redoc_url=None,
)
install_local_docs(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router, prefix=f"{settings.API_V1_STR}/ingest", tags=["Field Intelligence"])
app.include_router(recommend.router, prefix=f"{settings.API_V1_STR}/recommend", tags=["Recommendations"])
app.include_router(disease.router, prefix=f"{settings.API_V1_STR}/disease", tags=["Disease Detection"])


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error(f"AppError: {exc.code} - {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "detail": exc.message,
            "error": {
                "code": exc.code,
                "message": exc.message,
            },
        },
    )


@app.get("/")
async def root():
    return {
        "message": "Welcome to FasalX Recommendation Engine",
        "version": settings.VERSION,
        "endpoints": {
            "field_intelligence": f"{settings.API_V1_STR}/ingest",
            "recommendations": f"{settings.API_V1_STR}/recommend",
            "disease_detection": f"{settings.API_V1_STR}/disease/predict",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "recommendation-engine"}
