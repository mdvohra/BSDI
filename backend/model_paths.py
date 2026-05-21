"""
Central layout for ML artifacts and demo/sample rasters.

Repo layout (override root with env BRAEIN_MODELS_ROOT):
  models/
    artifacts/<model_id>/   # weights, config.json, preprocessor_config.json, etc.
    samples/<sample_id>/    # demo GeoTIFFs and other bundled inputs

Legacy paths (backend/models/, backend/lulc/, Eg_files/) remain supported as fallbacks.
"""
from __future__ import annotations

import os

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_BACKEND_DIR, ".."))


def repo_root() -> str:
    return _REPO_ROOT


def models_root() -> str:
    return os.path.normpath(os.environ.get("BRAEIN_MODELS_ROOT", os.path.join(_REPO_ROOT, "models")))


def artifacts_root() -> str:
    return os.path.join(models_root(), "artifacts")


def samples_root() -> str:
    return os.path.join(models_root(), "samples")


def artifact_dir(model_id: str) -> str:
    return os.path.join(artifacts_root(), model_id)


def sample_dir(sample_id: str) -> str:
    return os.path.join(samples_root(), sample_id)


def legacy_backend_models_dir() -> str:
    """Previous default flat torch weights directory."""
    return os.path.join(_BACKEND_DIR, "models")


def lulc_package_dir() -> str:
    return os.path.join(_BACKEND_DIR, "lulc")


def legacy_eg_files_dir() -> str:
    return os.path.join(_REPO_ROOT, "Eg_files")


def sar_flood_repo_dir() -> str:
    return os.path.normpath(os.path.join(_REPO_ROOT, "SAR_Flood"))


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def resolve_lulc_pretrained_path() -> str:
    """
    Hugging Face repo id or local directory for SigLIP LULC.
    Env LULC_MODEL_PATH wins; then models/artifacts/lulc; then backend/lulc; else HF id.
    """
    override = os.environ.get("LULC_MODEL_PATH", "").strip()
    if override:
        return override
    art = artifact_dir("lulc")
    if os.path.isfile(os.path.join(art, "config.json")) and os.path.isfile(
        os.path.join(art, "model.safetensors")
    ):
        return art
    pkg = lulc_package_dir()
    if os.path.isfile(os.path.join(pkg, "config.json")) and os.path.isfile(
        os.path.join(pkg, "model.safetensors")
    ):
        return pkg
    return "prithivMLmods/GiD-Land-Cover-Classification"
