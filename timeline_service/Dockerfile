# ==============================================================================
# FasalX Timeline Service — Dockerfile (Production)
# ==============================================================================
# Multi-stage build for a lean production image.
# The Arq worker is run as a SEPARATE process/container using the same image
# with a different CMD (see docker-compose.yml).
# ==============================================================================

# ---------- Stage 1: Dependency Builder ----------
FROM python:3.11-slim AS builder

WORKDIR /install

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy only requirements to leverage layer caching
COPY requirements/ ./requirements/

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install/deps -r requirements/prod.txt


# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ENVIRONMENT=production

COPY --from=builder /install/deps /usr/local

# Copy application source
COPY app/ ./app/

EXPOSE 8001

# Default: run the FastAPI HTTP server
# Override CMD in docker-compose.yml to run the Arq worker instead:
#   command: python -m arq app.worker.tasks.WorkerSettings
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8001", \
     "--timeout", "120"]
