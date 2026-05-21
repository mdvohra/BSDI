"""Filesystem layout for LULC change comparisons (JSON + GeoTIFF only)."""

from __future__ import annotations

import os

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_backend_root() -> str:
    return _BACKEND_ROOT


def get_predictions_dir() -> str:
    return os.path.normpath(os.path.join(_BACKEND_ROOT, "lulc", "predictions"))


def get_change_archive_root() -> str:
    root = os.environ.get("LULC_CHANGE_ARCHIVE_DIR", "").strip()
    if root:
        return os.path.normpath(root)
    return os.path.normpath(os.path.join(_BACKEND_ROOT, "lulc_change_archive"))


def comparison_dir(comparison_id: str) -> str:
    return os.path.join(get_change_archive_root(), "comparisons", comparison_id)


def region_sets_dir() -> str:
    return os.path.join(get_change_archive_root(), "region_sets")


def region_set_dir(set_id: str) -> str:
    return os.path.join(region_sets_dir(), set_id)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
