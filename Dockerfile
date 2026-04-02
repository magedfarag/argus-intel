# ─── Stage 1: build ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .

# rasterio requires GDAL; install libgdal from apt before pip install
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        libgdal-dev gdal-bin build-essential && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ─── Stage 2: runtime ──────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends libgdal-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

# Non-root user for security (OWASP A05)
RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_MODE=auto

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
