# syntax=docker/dockerfile:1
# GeoAI unified FastAPI backend (CPU). GPU: use a CUDA base image and torch CUDA wheels via compose override.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# GDAL/PROJ for rasterio, fiona, geopandas (system libs + headers for any sdist fallbacks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    proj-bin \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# BuildKit cache speeds rebuilds; cache mount does not bloat the final image.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:main_app", "--host", "0.0.0.0", "--port", "8000"]
