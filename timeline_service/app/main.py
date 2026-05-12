from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.db.mongodb import init_mongo, close_mongo
from app.api.routers import timeline
from app.core.docs import install_local_docs
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FasalX Timeline-Service...")
    await init_mongo()
    yield
    logger.info("Shutting down FasalX Timeline-Service...")
    await close_mongo()

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    description="Microservice for data-driven crop timeline phenological tracking.",
    docs_url=None,
    redoc_url=None,
)
install_local_docs(app)

# Allow CORS for Flutter Web Development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev environments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(timeline.router, prefix=f"{settings.API_V1_STR}/timeline", tags=["Timeline"])

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
