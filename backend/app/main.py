from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.firebase import init_firebase
from app.db.redis import init_redis, close_redis
from app.db.mongodb import init_mongo, close_mongo
from app.api.routers import admin_auth, agronomy, chatbot, dashboard_visibility, disease, fields, geo, system_config, telemetry, users, admin_panel, schemes
from app.core.exceptions import AppError
from app.core.docs import install_local_docs
import logging
import pathlib

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting up FasalX Backend...")
    init_firebase()
    await init_redis()
    await init_mongo()
    yield
    # Shutdown actions
    logger.info("Shutting down FasalX Backend...")
    await close_mongo()
    await close_redis()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    description="Backend API for FasalX - Precision Agriculture Platform",
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

app.include_router(agronomy.router, prefix=f"{settings.API_V1_STR}/agronomy", tags=["Agronomy"])
app.include_router(admin_auth.router, prefix=f"{settings.API_V1_STR}/admin/auth", tags=["Admin Auth"])
app.include_router(chatbot.router, prefix=f"{settings.API_V1_STR}/chatbot", tags=["Chatbot"])
app.include_router(disease.router, prefix=f"{settings.API_V1_STR}/disease", tags=["Disease"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["Users"])
app.include_router(telemetry.router, prefix=f"{settings.API_V1_STR}/telemetry", tags=["Telemetry"])
app.include_router(geo.router, prefix=f"{settings.API_V1_STR}/geo", tags=["Geo"])
app.include_router(fields.router, prefix=f"{settings.API_V1_STR}/fields", tags=["Fields"])
app.include_router(dashboard_visibility.router, prefix=f"{settings.API_V1_STR}", tags=["Dashboard Visibility"])
app.include_router(system_config.router, prefix=f"{settings.API_V1_STR}", tags=["System Config"])
# Admin panel — all dashboard management endpoints
app.include_router(admin_panel.router, prefix=f"{settings.API_V1_STR}/admin/api", tags=["Admin Panel"])
app.include_router(schemes.router, prefix=f"{settings.API_V1_STR}/schemes", tags=["Schemes"])
# ── Static files for image uploads ───────────────────────────────────────────
_upload_dir = pathlib.Path("static/uploads")
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Serve admin dashboard HTML ────────────────────────────────────────────────
_admin_html = pathlib.Path("frontend_admin/admin_dash.html")

@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
async def serve_admin_dashboard():
    """Serve the admin dashboard single-page application."""
    if _admin_html.exists():
        return FileResponse(str(_admin_html))
    return JSONResponse({"error": "Admin dashboard not found"}, status_code=404)

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error(f"AppError: {exc.code} - {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "detail": exc.message, # Backward compatibility for Flutter clients
            "error": {
                "code": exc.code,
                "message": exc.message
            }
        }
    )

@app.get("/")
async def root():
    return {"message": "Welcome to FasalX API", "version": settings.VERSION}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
