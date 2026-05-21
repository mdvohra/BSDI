"""
Braein AI GIS - Unified Backend
Mounts all services under one FastAPI app on a single port.

Prefixes:
  /unet      - UNet Building Detection
  /maskrcnn  - MaskRCNN Object Detection
  /srgan     - SRGAN Super-Resolution
  /lulc      - Land Use / Land Cover Classification
  /oil_spill - Oil Spill Segmentation
  /Auth      - Authentication (root level)
"""
import os
import sys
import uuid

_backend_root = os.path.dirname(os.path.abspath(__file__))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_backend_root, ".env"))
except ImportError:
    pass

from proj_runtime import clear_bad_proj_env

# PostGIS / pyproj proj.db is too old for GDAL in rasterio wheels — clear before any rasterio import.
clear_bad_proj_env()

# Add lulc/ to sys.path so lulc/server.py can resolve `from app import ...`
sys.path.insert(0, os.path.join(_backend_root, "lulc"))

# Logs go to the backend CMD window opened by start.ps1, not the PowerShell session.
# After a cache wipe, model/torch downloads and JIT compile can take many minutes with no output
# unless we print between import stages (see below).
print(
    "Backend: loading services (quiet period = heavy imports; first run after cache clear is slow)...",
    flush=True,
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from a2wsgi import WSGIMiddleware
from pydantic import BaseModel

from ui_config import get_ui_config_dict

print("  ... analysis + LULC change API", flush=True)
from analysis_api import router as analysis_router
from lulc_change.router import router as lulc_change_router

# Import the three FastAPI sub-apps (each may load models / torch state)
print("  ... UNet (/unet)", flush=True)
from unetnew import app as unet_app
print("  ... Mask R-CNN (/maskrcnn)", flush=True)
from finalmain import app as maskrcnn_app
print("  ... SRGAN (/srgan)", flush=True)
from super_resolution import app as srgan_app
print("  ... oil spill (/oil_spill)", flush=True)
from oil_spill_api import app as oil_spill_app

# Import the Flask LULC app
print("  ... LULC Flask (/lulc)", flush=True)
from server import app as lulc_flask_app  # resolves to lulc/server.py via sys.path

# --------------- Main App ---------------
main_app = FastAPI(title="GeoAI - Unified API")

main_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# --------------- Auth (root level) ---------------
class LoginRequest(BaseModel):
    email: str
    password: str


@main_app.post("/Auth/login")
async def login(request: LoginRequest):
    return {
        "token": "mock-jwt-token-" + uuid.uuid4().hex,
        "role": "user",
        "email": request.email,
    }


@main_app.get("/api/ui-config")
async def api_ui_config():
    """SPA reads GeoAI UI toggles from backend/.env (restart backend after changes)."""
    return get_ui_config_dict()


@main_app.get("/")
async def root():
    return {
        "service": "GeoAI - Unified API",
        "endpoints": {
            "unet": "/unet",
            "maskrcnn": "/maskrcnn",
            "srgan": "/srgan",
            "lulc": "/lulc",
            "oil_spill": "/oil_spill",
            "analysis": "/api/analysis",
            "lulc_change": "/api/analysis/lulc-change",
            "auth": "/Auth/login",
            "ui_config": "/api/ui-config",
        },
    }


main_app.include_router(analysis_router, prefix="/api/analysis")
main_app.include_router(lulc_change_router, prefix="/api/analysis")


# --------------- Mount sub-apps ---------------
main_app.mount("/unet", unet_app)
main_app.mount("/maskrcnn", maskrcnn_app)
main_app.mount("/srgan", srgan_app)
main_app.mount("/oil_spill", oil_spill_app)
main_app.mount("/lulc", WSGIMiddleware(lulc_flask_app))

if __name__ == "__main__":
    import uvicorn

    # Helpful: heavy models load at import time above; this prints only after that work completes.
    print(
        "Sub-apps mounted, models loaded. Starting Uvicorn on http://0.0.0.0:8000 ...",
        flush=True,
    )

    # Reload spawns a child that imports this module again → LULC + torch load twice (~2× startup).
    # Default OFF for fast startup (~single import). Enable when editing Python: UVICORN_RELOAD=1
    _reload = os.environ.get("UVICORN_RELOAD", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    uvicorn.run(
        "main:main_app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=_reload,
        reload_dirs=[_backend_root] if _reload else None,
        reload_excludes=["**/outputs/**", "**/__pycache__/**"] if _reload else None,
    )
