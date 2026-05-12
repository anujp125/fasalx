# ==============================================================================
# FasalX Backend — Dockerfile (Production)
# ==============================================================================
# Multi-stage build:
#   Stage 1 (builder): Installs dependencies in an isolated layer.
#   Stage 2 (runtime): Copies only the installed packages, keeps image lean.
# ==============================================================================

# ---------- Stage 1: Dependency Builder ----------
FROM python:3.11-slim AS builder

WORKDIR /install

# Prevents .pyc files and enables real-time logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build dependencies (gcc needed for some C-extension packages)
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy only the requirements directory first (leverages Docker layer caching)
COPY requirements/ ./requirements/

# Install production dependencies into a prefix directory
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install/deps -r requirements/prod.txt


# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ENVIRONMENT=production

# Copy installed packages from the builder stage
COPY --from=builder /install/deps /usr/local

# Copy application source code
COPY app/ ./app/

# Copy Firebase credentials
COPY serviceAccountKey.json ./serviceAccountKey.json

# Expose the main API port and the recommendation-engine port.
EXPOSE 8000 8002

# Production command: Gunicorn with uvicorn workers
# Workers = 2 * CPU_cores + 1 is a standard starting point.
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120"]
