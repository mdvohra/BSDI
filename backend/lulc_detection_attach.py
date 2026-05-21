"""
Copy object-detection outputs (UNet / Mask R-CNN) next to a saved LULC prediction so
reload shows buildings without re-inference.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import Any, Dict, Optional

from prediction_archive import validate_lulc_prediction_id, write_lulc_manifest


def _predictions_dir() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "lulc", "predictions"))


def _safe_refresh_manifest(pred_id: str, meta: Dict[str, Any]) -> None:
    """Rewrite slim LULC archive manifest from meta + known paths."""
    pred_dir = _predictions_dir()
    write_lulc_manifest(
        pred_id,
        model_name=meta.get("model_name")
        or os.environ.get("LULC_MODEL_NAME", "GiD-Land-Cover-Classification"),
        source_filename=meta.get("original_filename") or "",
        predictions_dir=pred_dir,
        annotation_png=os.path.join(pred_dir, pred_id + ".png"),
        meta_json=os.path.join(pred_dir, pred_id + ".json"),
        base_png=os.path.join(pred_dir, pred_id + "_base.png")
        if os.path.isfile(os.path.join(pred_dir, pred_id + "_base.png"))
        else None,
        geotiff_path=os.path.join(pred_dir, pred_id + ".tif")
        if os.path.isfile(os.path.join(pred_dir, pred_id + ".tif"))
        else None,
        class_geotiff_path=os.path.join(pred_dir, pred_id + "_classes.tif")
        if os.path.isfile(os.path.join(pred_dir, pred_id + "_classes.tif"))
        else None,
        seg_mode=meta.get("seg_mode") or "",
        buildings_geojson=os.path.join(pred_dir, pred_id + "_buildings.geojson")
        if os.path.isfile(os.path.join(pred_dir, pred_id + "_buildings.geojson"))
        else None,
        buildings_full_geojson=os.path.join(pred_dir, pred_id + "_buildings_full.geojson")
        if os.path.isfile(os.path.join(pred_dir, pred_id + "_buildings_full.geojson"))
        else None,
        unet_confidence_npz=os.path.join(pred_dir, pred_id + "_unet_confidence.npz")
        if os.path.isfile(os.path.join(pred_dir, pred_id + "_unet_confidence.npz"))
        else None,
    )


def attach_building_detection_to_lulc(
    lulc_pred_id: Optional[str],
    *,
    task: str,
    od_run_id: str,
    inference_threshold: float,
    geojson_abs_path: Optional[str],
    full_geojson_abs_path: Optional[str] = None,
    confidence_npz_abs_path: Optional[str] = None,
    model_name: Optional[str] = None,
) -> bool:
    """
    Copy detection artifacts into lulc/predictions/ and merge into <id>.json.
    task: 'unet' | 'maskrcnn'
    """
    if not validate_lulc_prediction_id(lulc_pred_id):
        return False
    pid = lulc_pred_id.strip()
    pred_dir = _predictions_dir()
    meta_path = os.path.join(pred_dir, pid + ".json")
    if not geojson_abs_path or not os.path.isfile(geojson_abs_path) or not os.path.isfile(meta_path):
        return False

    dest_gj = os.path.join(pred_dir, pid + "_buildings.geojson")
    try:
        shutil.copy2(geojson_abs_path, dest_gj)
    except OSError:
        return False

    dest_full = None
    if full_geojson_abs_path and os.path.isfile(full_geojson_abs_path):
        dest_full = os.path.join(pred_dir, pid + "_buildings_full.geojson")
        try:
            shutil.copy2(full_geojson_abs_path, dest_full)
        except OSError:
            dest_full = None

    dest_npz = None
    if task == "unet" and confidence_npz_abs_path and os.path.isfile(confidence_npz_abs_path):
        dest_npz = os.path.join(pred_dir, pid + "_unet_confidence.npz")
        try:
            shutil.copy2(confidence_npz_abs_path, dest_npz)
        except OSError:
            dest_npz = None

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False

    bd: Dict[str, Any] = {
        "task": task,
        "run_id": od_run_id,
        "model_name": model_name or "",
        "inference_threshold": float(inference_threshold),
        "geojson_file": os.path.basename(dest_gj),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if dest_full:
        bd["full_geojson_file"] = os.path.basename(dest_full)
    if dest_npz:
        bd["confidence_npz_file"] = os.path.basename(dest_npz)

    meta["building_detection"] = bd

    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except OSError:
        return False

    try:
        _safe_refresh_manifest(pid, meta)
    except Exception:
        pass

    return True
