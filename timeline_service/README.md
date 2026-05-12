# FasalX Timeline Service

The **Timeline Service** is the phenological intelligence engine of the FasalX platform. It replaces static crop calendars with dynamic, data-driven lifecycle tracking using **Growing Degree Days (GDD)** — ensuring every farmer's crop stage reflects actual field conditions, not estimates.

---

## Table of Contents
1. [Core Concept](#core-concept)
2. [Module Architecture](#module-architecture)
3. [Directory Structure & Path Reference](#directory-structure--path-reference)
4. [Data Quality Weighting](#data-quality-weighting)
5. [Background Worker (Arq)](#background-worker-arq)
6. [Configuration & Environment Variables](#configuration--environment-variables)
7. [Dependency Management](#dependency-management)
8. [Running Locally](#running-locally)
9. [Running the Arq Worker](#running-the-arq-worker)
10. [Service Mesh: Auth Communication](#service-mesh-auth-communication)
11. [API Reference](#api-reference)

---

## Core Concept

Standard crop calendars use fixed day counts from sowing date (e.g., "wheat tillers at Day 30"). This approach fails in variable climates. FasalX uses the **GDD model**:

```
GDD per day = max(0, ((T_max + T_min) / 2) - T_base)
```

- `T_max`, `T_min`: Daily maximum and minimum temperature (°C)
- `T_base`: Crop-specific threshold below which no growth occurs (default: 10°C)
- GDD accumulates daily — when total GDD crosses a milestone threshold, the crop stage advances.

---

## Module Architecture

```
timeline_service/
├── app/
│   ├── main.py              # FastAPI app factory and lifespan hooks
│   ├── api/
│   │   └── routers/
│   │       └── timeline.py  # /api/v1/timeline/* HTTP endpoints
│   ├── core/
│   │   ├── config.py        # Pydantic-Settings (dev / test / prod classes)
│   │   └── security.py      # Service mesh JWT interceptor (Redis-cached)
│   ├── db/
│   │   └── mongodb.py       # Motor async client — user_crop_timelines collection
│   ├── engines/
│   │   ├── gdd_engine.py        # GDD calculation + multi-tier data fallback
│   │   ├── milestone_predictor.py # Triggers milestone state transitions
│   │   └── geo_trend_analyzer.py  # Regional peer-crop trend analysis
│   ├── models/
│   │   └── timeline.py      # All Pydantic models for timeline data
│   └── worker/
│       └── tasks.py         # Arq worker: GDD job functions + cron schedule
├── requirements/
│   ├── base.txt             # Core runtime dependencies
│   ├── dev.txt              # base + test/lint tools
│   └── prod.txt             # base + gunicorn + sentry
├── Dockerfile               # Multi-stage production image (API + worker share image)
├── cloud-manifest.yaml      # GKE/Cloud Run service mesh manifest
├── .env.example             # Template — copy to .env and fill in values
└── README.md                # This file
```

---

## Directory Structure & Path Reference

| Path | Purpose |
|---|---|
| `app/main.py` | Creates FastAPI app. `lifespan` hook calls `init_mongo()` on startup and `close_mongo()` on shutdown. Registers the `/timeline` router. |
| `app/api/routers/timeline.py` | All `/api/v1/timeline/*` endpoints: create, read, trigger GDD recalculation. All endpoints require a validated JWT via the `verify_token` dependency. |
| `app/core/config.py` | `get_settings()` factory returning `DevelopmentSettings`, `TestingSettings`, or `ProductionSettings` based on the `ENVIRONMENT` variable. Cached with `@lru_cache`. |
| `app/core/security.py` | `verify_token` FastAPI dependency. Extracts JWT → checks Redis cache → calls `GET /api/v1/users/me` on `AUTH_SERVICE_URL` → caches result for 300 seconds. |
| `app/db/mongodb.py` | Motor client lifecycle. `get_mongo_db()` returns the `AsyncIOMotorDatabase` instance. Primary collection: `user_crop_timelines`. |
| `app/engines/gdd_engine.py` | `calculate_daily_gdd(t_max, t_min, t_base)` — pure GDD math. `process_environmental_data(snapshot, coords, t_base)` — applies the 3-tier data fallback. |
| `app/engines/milestone_predictor.py` | `predict_milestones(timeline)` — iterates the `milestone_map`, updates milestone `status` and `predicted_date` based on accumulated GDD vs. `target_gdd` thresholds. |
| `app/engines/geo_trend_analyzer.py` | `analyze_geo_trends(timeline)` — queries nearby timelines in MongoDB to compute regional GDD trend comparisons and surface anomaly flags. |
| `app/models/timeline.py` | All data models: `UserCropTimeline`, `LifecycleState`, `Milestone`, `MilestoneStatus`, `MilestoneType`, `EnvironmentalSnapshot`, `GeoLocation`, `UserMetadata`. |
| `app/worker/tasks.py` | `recalculate_timeline_gdd(ctx, user_id)` — background job. `daily_gdd_accumulation_job(ctx)` — cron (21:30 UTC / 03:00 IST). `WorkerSettings` — Arq worker config. |
| `cloud-manifest.yaml` | GKE service mesh declaration. Defines upstream dependency on `fasalx-auth:8000`, pod resource limits, and HPA autoscaling targets. |

---

## Data Quality Weighting

The `process_environmental_data` function in `gdd_engine.py` implements a 3-tier fallback:

| Tier | Source | Weight | Condition |
|---|---|---|---|
| **1 — IoT** | Direct field sensor (`EnvironmentalSnapshot.t_max/t_min`) | `1.0` | IoT data present and fresh (<24h) |
| **2 — API** | Open-Meteo hyper-local forecast (GPS coordinates) | `0.8` | IoT data absent or stale |
| **3 — Satellite** | Regional historical average (T_base + offset) | `0.5` | Open-Meteo API failure |

Milestones predicted using Tier-3 data are flagged with a `confidence_score` of `0.5` in the `milestone_map`, prompting the farmer to manually verify the crop stage.

---

## Background Worker (Arq)

The Arq worker runs as a **separate process** using the same Docker image, with an overridden `CMD`:

```bash
python -m arq app.worker.tasks.WorkerSettings
```

### Job Functions

| Function | Trigger | Description |
|---|---|---|
| `recalculate_timeline_gdd(ctx, user_id)` | On-demand (API or cron) | Fetches timeline → runs GDD engine → predicts milestones → analyzes geo trends → persists to MongoDB |
| `daily_gdd_accumulation_job(ctx)` | Cron: 21:30 UTC (03:00 IST) | Scans all active timelines (progress < 100%) and enqueues individual `recalculate_timeline_gdd` jobs |

---

## Configuration & Environment Variables

```bash
cp .env.example .env
```

| Variable | Default | Required | Description |
|---|---|---|---|
| `ENVIRONMENT` | `development` | No | Config selector: `development`, `testing`, `production` |
| `PROJECT_NAME` | `FasalX Timeline Service` | No | Displayed in FastAPI docs |
| `API_V1_STR` | `/api/v1` | No | API URL prefix |
| `MONGO_URL` | `mongodb://localhost:27017` | **Yes (prod)** | MongoDB Atlas SRV URI in production |
| `MONGO_DB_NAME` | `fasalx` | No | MongoDB database name |
| `REDIS_URL` | `redis://localhost:6379/0` | **Yes** | Used by Arq queue AND JWT token cache |
| `AUTH_SERVICE_URL` | `http://localhost:8000` | **Yes** | Internal URL of `fasalx-auth` service |

> **Testing**: `ENVIRONMENT=testing` automatically uses `fasalx_test` DB and Redis index 2 (no collision with backend tests on index 1).

---

## Dependency Management

```bash
# Local development
pip install -r requirements/dev.txt

# Production
pip install -r requirements/prod.txt
```

---

## Running Locally

```bash
# 1. Virtual environment
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# 2. Install dev dependencies
pip install -r requirements/dev.txt

# 3. Configure environment
cp .env.example .env
# Set MONGO_URL, REDIS_URL, AUTH_SERVICE_URL

# 4. Start dependencies (from project root)
docker-compose up redis mongodb fasalx-auth -d

# 5. Run the HTTP server
ENVIRONMENT=development uvicorn app.main:app --reload --port 8001
```

OpenAPI docs: **http://localhost:8001/docs**

---

## Running the Arq Worker

```bash
# From the timeline_service/ directory
ENVIRONMENT=development python -m arq app.worker.tasks.WorkerSettings
```

---

## Service Mesh: Auth Communication

The `security.py` module does **not** use Firebase Admin SDK directly. Instead:
1. It calls `GET {AUTH_SERVICE_URL}/api/v1/users/me` with the bearer token.
2. The response is cached in Redis under `auth_token:<token>` for 300 seconds.
3. This reduces cross-service network calls by ~99% under normal load.

---

## API Reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Health check |
| `POST` | `/api/v1/timeline/` | JWT (Mesh) | Create a new crop timeline for the user |
| `GET` | `/api/v1/timeline/me` | JWT (Mesh) | Get the current user's active timeline |
| `POST` | `/api/v1/timeline/me/recalibrate` | JWT (Mesh) | Enqueue an on-demand GDD recalculation job |
