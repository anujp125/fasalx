# FasalX Backend Service

The **Backend** (also referred to as `fasalx-auth`) is the primary API gateway and identity backbone of the FasalX platform. It handles user authentication via Firebase, exposes the agronomic data APIs to the mobile clients, and serves as the trusted service mesh origin for all other microservices.

---

## Table of Contents
1. [Responsibilities](#responsibilities)
2. [Module Architecture](#module-architecture)
3. [Directory Structure & Path Reference](#directory-structure--path-reference)
4. [Configuration & Environment Variables](#configuration--environment-variables)
5. [Dependency Management](#dependency-management)
6. [Running Locally](#running-locally)
7. [Running Tests](#running-tests)
8. [API Reference](#api-reference)

---

## Responsibilities

| Feature | Description |
|---|---|
| **Firebase JWT Auth** | Verifies Firebase ID tokens on every protected endpoint via `HTTPBearer`. |
| **User Management** | CRUD for farmer profiles, account deactivation (soft-delete), and hard deletion across Firebase + MongoDB. |
| **Activity Logging** | Every significant user action (LOGIN, LOGOUT, PROFILE_UPDATE, etc.) is persisted to the `user_activities` MongoDB collection. |
| **Agronomy Data** | Provides crop template data and generates farmer-specific timelines (delegates GDD to the Timeline Service). |
| **Weather API** | Wraps the Open-Meteo API with a Redis-backed cache (1-hour TTL) for hyper-local weather. |
| **Mandi Prices** | Proxies Data.gov.in Mandi price data with a Redis-backed cache (2-hour TTL). |
| **Telemetry** | Ingests IoT sensor data (soil moisture, temperature) and stores it in the `environmental_snapshots` collection. |

---

## Module Architecture

```
backend/
├── app/
│   ├── main.py              # FastAPI app factory, lifespan hooks, router registration
│   ├── api/
│   │   └── routers/         # HTTP endpoint layer (thin controllers)
│   │       ├── users.py     # /api/v1/users/*
│   │       ├── agronomy.py  # /api/v1/agronomy/*
│   │       └── telemetry.py # /api/v1/telemetry/*
│   ├── core/
│   │   ├── config.py        # Pydantic-Settings config (dev / test / prod classes)
│   │   ├── firebase.py      # Firebase Admin SDK init and Firestore client
│   │   └── security.py      # Firebase JWT verification dependency
│   ├── db/
│   │   ├── mongodb.py       # Motor (async MongoDB) connection manager
│   │   └── redis.py         # Redis connection manager
│   ├── models/
│   │   ├── user.py          # FarmerProfile, UserActivity Pydantic models
│   │   ├── agronomy.py      # CropTemplate, CropStage, WeatherResponse models
│   │   └── telemetry.py     # IoT sensor snapshot models
│   └── services/
│       ├── user_service.py          # Business logic: activate/deactivate/delete users
│       ├── mandi_prices.py          # Data.gov.in proxy + Redis cache
│       ├── weather_service.py       # Open-Meteo proxy + Redis cache
│       └── geolocation_service.py   # IP → GPS geolocation fallback logic
├── requirements/
│   ├── base.txt             # Core runtime dependencies
│   ├── dev.txt              # base + testing/linting tools
│   └── prod.txt             # base + gunicorn + sentry
├── tests/                   # Pytest test suite
├── Dockerfile               # Multi-stage production image
├── .env.example             # Template — copy to .env and fill in secrets
└── serviceAccountKey.json   # Firebase key (GITIGNORED — download from Firebase Console)
```

---

## Directory Structure & Path Reference

| Path | Purpose |
|---|---|
| `app/main.py` | Creates the `FastAPI` app instance. Registers all routers with their URL prefixes. Manages startup/shutdown via `lifespan` (init Firebase → Redis → MongoDB). |
| `app/api/routers/users.py` | All `/api/v1/users/*` endpoints: `GET /me`, `PUT /me`, `POST /register`, `DELETE /me`, `PUT /me/deactivate`. |
| `app/api/routers/agronomy.py` | All `/api/v1/agronomy/*` endpoints: crop templates, weather, mandi prices. |
| `app/api/routers/telemetry.py` | All `/api/v1/telemetry/*` endpoints: IoT sensor data ingestion. |
| `app/core/config.py` | Loads env vars via `pydantic-settings`. Active config selected by `ENVIRONMENT` variable. Use `settings = get_settings()`. |
| `app/core/firebase.py` | Initialises Firebase Admin SDK. Exposes `get_db()` for Firestore access. Falls back to ADC (Application Default Credentials) on GCP. |
| `app/core/security.py` | `get_current_user` FastAPI dependency. Verifies Firebase ID tokens with `check_revoked=True`. |
| `app/db/mongodb.py` | Async Motor client. Call `init_mongo()` in lifespan startup; `get_mongo_db()` in route handlers. |
| `app/db/redis.py` | Async Redis client. Call `init_redis()` on startup; `get_redis()` in services. |
| `app/models/user.py` | `FarmerProfile` (profile data), `UserActivity` (audit log entry). |
| `app/models/agronomy.py` | `WeatherResponse`, `CropTemplate`, `CropStage`, `CropTimelineRequest`. |
| `app/services/user_service.py` | `log_user_activity()`, `deactivate_user_account()`, `delete_user_account()`. |
| `app/services/mandi_prices.py` | `get_mandi_prices_async(state, market)` — fetches & caches Mandi prices. |
| `app/services/weather_service.py` | `get_weather_forecast(lat, lon)` — fetches & caches Open-Meteo weather. |

---

## Configuration & Environment Variables

Copy the template, then fill in your real secrets:

```bash
cp .env.example .env
```

| Variable | Default | Required | Description |
|---|---|---|---|
| `ENVIRONMENT` | `development` | No | Config class selector: `development`, `testing`, `production` |
| `PROJECT_NAME` | `FasalX Backend` | No | Shown in FastAPI docs |
| `VERSION` | `0.1.0` | No | API version string |
| `API_V1_STR` | `/api/v1` | No | API URL prefix |
| `MONGO_URL` | `mongodb://localhost:27017` | **Yes (prod)** | MongoDB connection string |
| `MONGO_DB_NAME` | `fasalx` | No | MongoDB database name |
| `REDIS_URL` | `redis://localhost:6379/0` | **Yes (prod)** | Redis connection string |
| `FIREBASE_CREDENTIALS_PATH` | `None` | **Yes (local)** | Path to Firebase service account JSON |
| `LIVE_MANDI_PRICES_API_KEY` | `None` | **Yes** | API key for Mandi price data |

> **Testing**: Set `ENVIRONMENT=testing`. The config will automatically use `fasalx_test` as the DB name and Redis DB index 1.

---

## Dependency Management

```bash
# Local development (includes linters, test tools)
pip install -r requirements/dev.txt

# Production (gunicorn + sentry only added on top of base)
pip install -r requirements/prod.txt

# Minimal base only
pip install -r requirements/base.txt
```

---

## Running Locally

```bash
# 1. Set up virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dev dependencies
pip install -r requirements/dev.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your MongoDB URI, Firebase key path, and API keys

# 4. Start Redis and MongoDB (via Docker Compose from root)
docker-compose up redis mongodb -d

# 5. Run the development server (auto-reload)
ENVIRONMENT=development uvicorn app.main:app --reload --port 8000
```

OpenAPI docs will be available at: **http://localhost:8000/docs**

---

## Running Tests

```bash
ENVIRONMENT=testing pytest tests/ -v
```

---

## API Reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Health check |
| `POST` | `/api/v1/users/register` | Firebase JWT | Register / upsert farmer profile |
| `GET` | `/api/v1/users/me` | Firebase JWT | Get current user profile |
| `PUT` | `/api/v1/users/me` | Firebase JWT | Update profile fields |
| `PUT` | `/api/v1/users/me/deactivate` | Firebase JWT | Soft-deactivate account |
| `DELETE` | `/api/v1/users/me` | Firebase JWT | Hard-delete from Firebase + MongoDB |
| `GET` | `/api/v1/agronomy/weather` | Firebase JWT | Hyper-local weather forecast |
| `GET` | `/api/v1/agronomy/mandi-prices` | Firebase JWT | Mandi commodity prices |
| `POST` | `/api/v1/telemetry/sensor-data` | Firebase JWT | Ingest IoT sensor reading |
