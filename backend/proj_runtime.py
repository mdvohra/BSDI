"""
Strip PROJ_LIB / PROJ_DATA that point at old proj.db bundles (PostGIS, pyproj, etc.).
GDAL/rasterio wheels embed PROJ 9+; stale env vars break every EPSG lookup.

Call clear_bad_proj_env() before any import of rasterio/osgeo.
"""
from __future__ import annotations

import os


def clear_bad_proj_env() -> None:
    for key in ("PROJ_LIB", "PROJ_DATA"):
        v = os.environ.get(key, "")
        if not v:
            continue
        n = v.replace("\\", "/").lower()
        # PostGIS / Postgres stacks ship ancient proj.db (MINOR 2–4)
        if (
            "pyproj" in n
            or "postgis" in n
            or "postgress" in n
            or "/postgresql/" in n
            or "postgresql\\" in n.lower()
        ):
            os.environ.pop(key, None)
