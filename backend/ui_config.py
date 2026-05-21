"""GeoAI UI feature flags from backend/.env (single control plane for SPA)."""
import os


def _env_bool(key: str, default: bool = True) -> bool:
    v = os.environ.get(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _env_float(key: str, default: float) -> float:
    v = os.environ.get(key)
    if v is None or str(v).strip() == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def get_ui_config_dict() -> dict:
    """Values consumed by GET /api/ui-config (camelCase JSON keys)."""
    return {
        # Defaults favor object-detection-only UI; set env vars to true to enable modules.
        "show_super_resolution": _env_bool("GEOAI_UI_SHOW_SUPER_RESOLUTION", False),
        "show_lulc": _env_bool("GEOAI_UI_SHOW_LULC", False),
        "show_analysis": _env_bool("GEOAI_UI_SHOW_ANALYSIS", False),
        "show_lulc_fields": _env_bool("GEOAI_UI_SHOW_LULC_FIELDS", False),
        "show_detection_threshold": _env_bool("GEOAI_UI_SHOW_DETECTION_THRESHOLD", True),
        "show_config_page": _env_bool("GEOAI_UI_SHOW_CONFIG_PAGE", False),
        "default_inference_threshold": _env_float("GEOAI_DEFAULT_INFERENCE_THRESHOLD", 0.3),
    }
