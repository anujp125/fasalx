# FasalX — Precision Agriculture Platform

**FasalX** is a microservices-based precision agriculture platform that helps Indian farmers make data-driven decisions about their crops. It replaces static farming calendars with dynamic, sensor- and satellite-informed crop lifecycle tracking powered by the **Growing Degree Day (GDD)** model.

---

## Table of Contents

1. [Product Overview](#product-overview)
2. [Platform Architecture](#platform-architecture)
3. [Repository Structure](#repository-structure)
4. [Microservices Overview](#microservices-overview)
   - [Backend (fasalx-auth)](#1-backend-fasalx-auth)
   - [Timeline Service (fasalx-timeline)](#2-timeline-service-fasalx-timeline)
   - [Frontend Client](#3-frontend-client-fasalx-client)
   - [Frontend Admin](#4-frontend-admin-fasalx-admin)
5. [All Dependencies — Consolidated Reference](#all-dependencies--consolidated-reference)
   - [Backend Dependencies](#backend-dependencies)
   - [Timeline Service Dependencies](#timeline-service-dependencies)
6. [Environment Variables — Full Reference](#environment-variables--full-reference)
   - [Backend `.env`](#backend-env-backendenvenvironmentexample)
   - [Timeline Service `.env`](#timeline-service-env-timeline_serviceenvenvironmentexample)
7. [Configuration System (dev / test / prod)](#configuration-system-dev--test--prod)
8. [Running the Full Stack Locally](#running-the-full-stack-locally)
9. [Running Individual Services](#running-individual-services)
10. [Infrastructure & Deployment](#infrastructure--deployment)
11. [MongoDB Collections Reference](#mongodb-collections-reference)

---

## Product Overview

| Feature | Description |
|---|---|
| **Dynamic Crop Timelines** | GDD-based phenological tracking replaces fixed-date calendars. |
| **Multi-Tier Data Sources** | IoT sensors → hyper-local weather API → satellite fallback, with quality weighting. |
| **Firebase Authentication** | Secure Firebase JWT-based identity, with token revocation support. |
| **Farmer Profile Management** | Full user lifecycle: registration, profile updates, soft deactivation, hard deletion. |
| **Mandi Price Intelligence** | Real-time commodity prices from Data.gov.in with Redis caching. |
| **Weather Intelligence** | Hyper-local forecasts from Open-Meteo, cached per GPS coordinate. |
| **IoT Telemetry Ingestion** | REST endpoint to receive field sensor data (soil moisture, temperature). |
| **Autonomous Background Jobs** | Arq-based daily cron (03:00 IST) accumulates GDD for all active timelines. |
| **Service Mesh Auth** | Timeline service validates JWTs through the auth service, with Redis caching (300s TTL). |

---

## Platform Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FasalX Platform                               │
│                                                                      │
│  ┌─────────────┐    ┌───────────────────┐    ┌─────────────────┐    │
│  │  Mobile App │    │   Admin Dashboard  │    │   IoT Sensors   │    │
│  │ (Flutter)   │    │   (Web — React)   │    │  (Field Devices) │   │
│  └──────┬──────┘    └────────┬──────────┘    └────────┬────────┘    │
│         │                    │                         │             │
│         │           HTTP / REST (Firebase JWT)         │             │
│         │                    │                         │             │
│  ┌──────▼────────────────────▼─────────────────────┐  │             │
│  │        fasalx-auth (Backend Service)             │  │             │
│  │   FastAPI · Firebase Admin · Motor · Redis       │◄─┘             │
│  │   Port: 8000                                     │               │
│  └───────────────────────┬──────────────────────────┘               │
│                           │  Service Mesh (HTTP + Redis JWT Cache)   │
│  ┌────────────────────────▼──────────────────────────────────────┐  │
│  │        fasalx-timeline (Timeline Service)                      │  │
│  │   FastAPI · Motor · Arq · httpx · Redis                       │  │
│  │   Port: 8001                                                  │  │
│  │                                                               │  │
│  │  ┌─────────────────────────────────────────────────────────┐ │  │
│  │  │  fasalx-worker (Arq Background Worker)                  │ │  │
│  │  │  - daily_gdd_accumulation_job  [CRON: 21:30 UTC]        │ │  │
│  │  │  - recalculate_timeline_gdd    [On-demand]              │ │  │
│  │  └─────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────┐    ┌────────────────┐                         │
│  │  MongoDB Atlas   │    │  Redis Cloud   │                         │
│  │  (Shared DB)     │    │  (Shared Cache)│                         │
│  └──────────────────┘    └────────────────┘                         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
FasalX/                              ← Project root
├── docker-compose.yml               ← Full local stack (5 services)
├── .gitignore                       ← Ignores .env, venv, serviceAccountKey.json
├── README.md                        ← This file
│
├── backend/                         ← fasalx-auth microservice
│   ├── app/
│   │   ├── main.py
│   │   ├── api/routers/             ← users.py, agronomy.py, telemetry.py
│   │   ├── core/                    ← config.py, firebase.py, security.py
│   │   ├── db/                      ← mongodb.py, redis.py
│   │   ├── models/                  ← user.py, agronomy.py, telemetry.py
│   │   └── services/                ← user_service.py, mandi_prices.py, weather_service.py, geolocation_service.py
│   ├── requirements/
│   │   ├── base.txt                 ← Runtime dependencies
│   │   ├── dev.txt                  ← base + pytest + ruff + black
│   │   └── prod.txt                 ← base + gunicorn + sentry
│   ├── tests/
│   ├── Dockerfile                   ← Multi-stage production image
│   ├── .env.example                 ← Environment variable template (safe to commit)
│   ├── .env                         ← GITIGNORED — real secrets
│   ├── serviceAccountKey.json       ← GITIGNORED — download from Firebase Console
│   └── README.md                    ← Module-specific docs
│
├── timeline_service/                ← fasalx-timeline microservice
│   ├── app/
│   │   ├── main.py
│   │   ├── api/routers/             ← timeline.py
│   │   ├── core/                    ← config.py, security.py
│   │   ├── db/                      ← mongodb.py
│   │   ├── engines/                 ← gdd_engine.py, milestone_predictor.py, geo_trend_analyzer.py
│   │   ├── models/                  ← timeline.py
│   │   └── worker/                  ← tasks.py (Arq worker + cron)
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── dev.txt
│   │   └── prod.txt
│   ├── Dockerfile
│   ├── cloud-manifest.yaml          ← GKE / Cloud Run service mesh manifest
│   ├── .env.example
│   ├── .env                         ← GITIGNORED
│   └── README.md
│
├── frontend_client/                 ← Flutter mobile app (farmers)
│   └── README.md
│
├── frontend_admin/                  ← Web admin dashboard
│   └── README.md
│
└── venv/                            ← Root-level venv (optional, for IDE tooling only)
```

---

## Microservices Overview

### 1. Backend (`fasalx-auth`)

> **Detailed docs**: [`backend/README.md`](./backend/README.md)

- **Port**: `8000`
- **Framework**: FastAPI + Uvicorn
- **Auth**: Firebase Admin SDK (`firebase-admin`)
- **DB**: MongoDB via Motor (`motor`)
- **Cache**: Redis (`redis`)
- **Key Responsibilities**: User registration/auth, farmer profiles, weather, Mandi prices, IoT telemetry ingestion.

---

### 2. Timeline Service (`fasalx-timeline`)

> **Detailed docs**: [`timeline_service/README.md`](./timeline_service/README.md)

- **Port**: `8001`
- **Framework**: FastAPI + Uvicorn
- **Job Queue**: Arq (Redis-backed)
- **DB**: MongoDB via Motor
- **Key Responsibilities**: GDD calculation, crop milestone prediction, geo-trend analysis, daily cron jobs.

---

### 3. Frontend Client (`fasalx-client`)

> **Status**: In development.

Flutter-based mobile application for farmers. Consumes the `fasalx-auth` REST API.

---

### 4. Frontend Admin (`fasalx-admin`)

> **Status**: Planned.

Web dashboard for platform administrators. Will consume both backend APIs.

---

## All Dependencies — Consolidated Reference

Each microservice manages its own isolated dependencies via a `requirements/` directory. There is **no shared root `requirements.txt`** — this ensures true microservice independence.

### Backend Dependencies

| Package | Version | Layer | Purpose |
|---|---|---|---|
| `fastapi` | `>=0.100.0` | base | HTTP framework |
| `uvicorn[standard]` | `>=0.23.0` | base | ASGI server |
| `motor` | `>=3.3.0` | base | Async MongoDB driver |
| `redis` | `>=5.0.0` | base | Async Redis client |
| `pydantic` | `>=2.4.0` | base | Data validation |
| `pydantic-settings` | `>=2.0.0` | base | Settings from `.env` |
| `firebase-admin` | `>=6.2.0` | base | Firebase JWT verification + Firestore |
| `httpx` | `>=0.25.0` | base | Async HTTP client (Open-Meteo, Data.gov.in) |
| `python-dotenv` | `>=1.0.0` | base | `.env` file loading |
| `pytest` | `>=7.4.0` | **dev** | Test runner |
| `pytest-asyncio` | `>=0.21.0` | **dev** | Async test support |
| `ruff` | `>=0.1.0` | **dev** | Linter |
| `black` | `>=23.0.0` | **dev** | Code formatter |
| `mypy` | `>=1.5.0` | **dev** | Type checker |
| `watchfiles` | `>=0.20.0` | **dev** | Hot-reload watcher |
| `gunicorn` | `>=21.2.0` | **prod** | Multi-worker process manager |
| `sentry-sdk[fastapi]` | `>=1.30.0` | **prod** | Error tracking |

### Timeline Service Dependencies

| Package | Version | Layer | Purpose |
|---|---|---|---|
| `fastapi` | `>=0.100.0` | base | HTTP framework |
| `uvicorn[standard]` | `>=0.23.0` | base | ASGI server |
| `motor` | `>=3.3.0` | base | Async MongoDB driver |
| `redis` | `>=5.0.0` | base | Async Redis client |
| `arq` | `>=0.25.0` | base | Async Redis job queue + cron scheduler |
| `pydantic` | `>=2.4.0` | base | Data validation |
| `pydantic-settings` | `>=2.0.0` | base | Settings from `.env` |
| `httpx` | `>=0.25.0` | base | Open-Meteo API + auth service mesh calls |
| `python-dotenv` | `>=1.0.0` | base | `.env` file loading |
| `pytest` | `>=7.4.0` | **dev** | Test runner |
| `pytest-asyncio` | `>=0.21.0` | **dev** | Async test support |
| `anyio` | `>=4.0.0` | **dev** | Async backend for pytest |
| `ruff` | `>=0.1.0` | **dev** | Linter |
| `black` | `>=23.0.0` | **dev** | Code formatter |
| `mypy` | `>=1.5.0` | **dev** | Type checker |
| `watchfiles` | `>=0.20.0` | **dev** | Hot-reload watcher |
| `gunicorn` | `>=21.2.0` | **prod** | Multi-worker process manager |
| `sentry-sdk[fastapi]` | `>=1.30.0` | **prod** | Error tracking |

---

## Environment Variables — Full Reference

### Backend `.env` (`backend/.env` / environment-specific)

> Template: [`backend/.env.example`](./backend/.env.example)

| Variable | Example Value | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Active config class: `development`, `testing`, `production` |
| `PROJECT_NAME` | `FasalX Backend` | Shown in OpenAPI docs |
| `VERSION` | `0.1.0` | API version string |
| `API_V1_STR` | `/api/v1` | All API routes are prefixed with this |
| `MONGO_URL` | `mongodb://localhost:27017` | MongoDB connection string. Use Atlas SRV URI in prod |
| `MONGO_DB_NAME` | `fasalx` | MongoDB database name (`fasalx_test` in testing) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URI |
| `FIREBASE_CREDENTIALS_PATH` | `./serviceAccountKey.json` | Path to Firebase Admin SDK key JSON |
| `DATA_GOV_IN_API_KEY` | `your_api_key_here` | API key for Data.gov.in Mandi price datasets |

### Timeline Service `.env` (`timeline_service/.env` / environment-specific)

> Template: [`timeline_service/.env.example`](./timeline_service/.env.example)

| Variable | Example Value | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Active config class selector |
| `PROJECT_NAME` | `FasalX Timeline Service` | Shown in OpenAPI docs |
| `API_V1_STR` | `/api/v1` | API route prefix |
| `MONGO_URL` | `mongodb://localhost:27017` | Same Atlas cluster as backend |
| `MONGO_DB_NAME` | `fasalx` | Shared database (`fasalx_test` in testing) |
| `REDIS_URL` | `redis://localhost:6379/0` | Used by Arq queue **and** JWT token cache |
| `AUTH_SERVICE_URL` | `http://localhost:8000` | Internal URL of the `fasalx-auth` backend |

---

## Configuration System (dev / test / prod)

Both microservices use the same pattern in `app/core/config.py`:

```python
# Select active config via ENVIRONMENT variable
settings = get_settings()  # Returns DevelopmentSettings, TestingSettings, or ProductionSettings
```

| `ENVIRONMENT` | MongoDB DB | Redis Index | Notes |
|---|---|---|---|
| `development` | `fasalx` | `0` | Default. Uses localhost. |
| `testing` | `fasalx_test` | `1` (backend) / `2` (timeline) | Isolated. Used by CI. |
| `production` | `fasalx` | `0` | Expects Atlas URI + managed Redis. |

```bash
# Select environment at runtime
ENVIRONMENT=production uvicorn app.main:app ...
ENVIRONMENT=testing pytest tests/ -v
```

---

## Running the Full Stack Locally

```bash
# Clone the repository
git clone <your-repo-url> FasalX
cd FasalX

# Create environment files from templates
cp backend/.env.example backend/.env
cp timeline_service/.env.example timeline_service/.env

# Edit both .env files with your secrets:
#   - FIREBASE_CREDENTIALS_PATH (backend only)
#   - MONGO_URL (if using Atlas instead of local MongoDB)
#   - DATA_GOV_IN_API_KEY (backend only)

# Build and start all services
docker-compose up --build
```

| Service | URL |
|---|---|
| Backend API (OpenAPI Docs) | http://localhost:8000/docs |
| Timeline Service (OpenAPI Docs) | http://localhost:8001/docs |
| Backend Health | http://localhost:8000/health |
| Timeline Health | http://localhost:8001/health |

---

## Running Individual Services

```bash
# Backend only (with local venv)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env  # fill in values
ENVIRONMENT=development uvicorn app.main:app --reload --port 8000

# Timeline Service only
cd timeline_service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env
ENVIRONMENT=development uvicorn app.main:app --reload --port 8001

# Arq Worker only
cd timeline_service
ENVIRONMENT=development python -m arq app.worker.tasks.WorkerSettings
```

---

## Infrastructure & Deployment

| Component | Tool | Config File |
|---|---|---|
| Local orchestration | Docker Compose | `docker-compose.yml` |
| Backend container | Dockerfile (multi-stage) | `backend/Dockerfile` |
| Timeline container | Dockerfile (multi-stage) | `timeline_service/Dockerfile` |
| Cloud deployment | GKE / Cloud Run | `timeline_service/cloud-manifest.yaml` |
| Service mesh | HTTP + Redis JWT cache | `timeline_service/app/core/security.py` |
| Cron / background jobs | Arq | `timeline_service/app/worker/tasks.py` |

---

## MongoDB Collections Reference

| Collection | Service | Documents Stored |
|---|---|---|
| `users` | backend | `FarmerProfile` documents |
| `user_activities` | backend | `UserActivity` audit log entries |
| `environmental_snapshots` | backend | IoT telemetry readings |
| `user_crop_timelines` | timeline | `UserCropTimeline` (GDD, milestones, lifecycle state) |
