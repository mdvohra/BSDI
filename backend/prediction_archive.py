"""
File-based prediction archive: JSON manifests under PREDICTION_ARCHIVE_DIR for later analysis.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional

_SCHEMA_VERSION = "1.0"

_BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_ROOT = os.path.normpath(
    os.environ.get("PREDICTION_ARCHIVE_DIR", os.path.join(_BACKEND_ROOT, "prediction_archive"))
)

_RUN_ID_SAFE = re.compile(r"^[0-9a-fA-F\-]{32,36}$")
_LULC_PRED_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-fA-F]{8}$")


def get_archive_root() -> str:
    os.makedirs(ARCHIVE_ROOT, exist_ok=True)
    return ARCHIVE_ROOT


def validate_run_id(run_id: str) -> bool:
    if not run_id or len(run_id) > 64:
        return False
    return bool(_RUN_ID_SAFE.match(run_id))


def validate_lulc_prediction_id(pred_id: Optional[str]) -> bool:
    if not pred_id or len(pred_id) > 64:
        return False
    return bool(_LULC_PRED_ID_RE.match(pred_id.strip()))


def _lulc_predictions_dir() -> str:
    return os.path.normpath(os.path.join(_BACKEND_ROOT, "lulc", "predictions"))


def _artifact_paths_from_manifest(m: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    art = m.get("artifacts") or {}
    if isinstance(art, dict):
        for _k, v in art.items():
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
    return out


def _unlink_if_under_backend(path: str) -> bool:
    if not path:
        return False
    abs_p = os.path.abspath(path)
    backend = os.path.abspath(_BACKEND_ROOT)
    if abs_p != backend and not abs_p.startswith(backend + os.sep):
        return False
    try:
        if os.path.isfile(abs_p):
            os.unlink(abs_p)
            return True
    except OSError:
        pass
    return False


def _unlink_lulc_prediction_files(pred_id: str) -> List[str]:
    """Remove known files for a LULC prediction id under lulc/predictions/."""
    pred_dir = _lulc_predictions_dir()
    base = os.path.join(pred_dir, pred_id)
    candidates = (
        base + ".json",
        base + ".png",
        base + "_base.png",
        base + ".tif",
        base + "_classes.tif",
        base + "_buildings.geojson",
        base + "_buildings_full.geojson",
        base + "_unet_confidence.npz",
    )
    removed: List[str] = []
    for p in candidates:
        if _unlink_if_under_backend(p):
            removed.append(p)
    return removed


def _rmtree_archive_entry(entry_name: str) -> None:
    root = get_archive_root()
    path = os.path.join(root, entry_name)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def delete_prediction_run(task: str, run_id: str) -> Dict[str, Any]:
    """
    Remove archive manifest folder and any artifact paths recorded there (backend tree only).
    For LULC, also deletes flat files under lulc/predictions/.
    """
    task = (task or "").strip().lower()
    if task == "lulc":
        if not validate_lulc_prediction_id(run_id):
            return {"ok": False, "error": "invalid lulc prediction id"}
        entry = f"lulc_{run_id}"
        m = read_manifest(entry)
        removed_files: List[str] = []
        if m:
            for p in _artifact_paths_from_manifest(m):
                if _unlink_if_under_backend(p):
                    removed_files.append(p)
        removed_files.extend(_unlink_lulc_prediction_files(run_id))
        _rmtree_archive_entry(entry)
        return {"ok": True, "task": task, "id": run_id, "removed_files": removed_files}

    if task not in ("unet", "maskrcnn", "solar_panel"):
        return {"ok": False, "error": "unsupported task"}
    if not validate_run_id(run_id):
        return {"ok": False, "error": "invalid run id"}
    entry = run_id
    m = read_manifest(entry)
    removed_files: List[str] = []
    if m:
        for p in _artifact_paths_from_manifest(m):
            if _unlink_if_under_backend(p):
                removed_files.append(p)
    _rmtree_archive_entry(entry)
    return {"ok": True, "task": task, "id": run_id, "removed_files": removed_files}


def delete_all_archived_predictions() -> Dict[str, Any]:
    """Delete every manifest under the archive root (object detection + LULC)."""
    root = get_archive_root()
    names: List[str] = []
    try:
        names = sorted(os.listdir(root))
    except OSError as e:
        return {"ok": False, "error": str(e), "deleted": 0, "failed": 0}

    deleted = 0
    failed = 0
    details: List[Dict[str, Any]] = []
    for entry in names:
        mpath = os.path.join(root, entry, "manifest.json")
        if not os.path.isfile(mpath):
            continue
        m = read_manifest(entry)
        if not m:
            failed += 1
            details.append({"entry": entry, "error": "bad manifest"})
            continue
        task = str(m.get("task") or "").lower()
        rid = str(m.get("run_id") or "")
        r = delete_prediction_run(task, rid)
        if r.get("ok"):
            deleted += 1
        else:
            failed += 1
            details.append({"entry": entry, "task": task, "id": rid, "error": r.get("error")})

    return {"ok": True, "deleted": deleted, "failed": failed, "details": details[:50]}


def delete_all_lulc_predictions_only() -> Dict[str, Any]:
    """Delete all LULC runs by scanning lulc/predictions/*.json (covers orphans without manifests)."""
    pred_dir = _lulc_predictions_dir()
    ids: List[str] = []
    try:
        for fn in os.listdir(pred_dir):
            if not fn.endswith(".json"):
                continue
            pid = fn[:-5]
            if validate_lulc_prediction_id(pid):
                ids.append(pid)
    except OSError as e:
        return {"ok": False, "error": str(e), "deleted": 0}

    deleted = 0
    failed = 0
    details: List[Dict[str, Any]] = []
    for pid in ids:
        r = delete_prediction_run("lulc", pid)
        if r.get("ok"):
            deleted += 1
        else:
            failed += 1
            details.append({"id": pid, "error": r.get("error")})

    # Archive dirs left behind if json was missing (manifest-only or partial)
    try:
        root = get_archive_root()
        for name in os.listdir(root):
            if not name.startswith("lulc_"):
                continue
            path = os.path.join(root, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass

    return {"ok": True, "deleted": deleted, "failed": failed, "details": details[:50]}


def _write_manifest(run_id: str, payload: Dict[str, Any]) -> Optional[str]:
    if not validate_run_id(run_id):
        return None
    root = get_archive_root()
    run_dir = os.path.join(root, run_id)
    try:
        os.makedirs(run_dir, exist_ok=True)
        path = os.path.join(run_dir, "manifest.json")
        payload = {**payload, "schema_version": _SCHEMA_VERSION, "run_id": run_id}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return path
    except OSError:
        return None


def file_sha256_preview(path: str, max_bytes: int = 2_000_000) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            chunk = f.read(max_bytes)
            h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def write_maskrcnn_manifest(
    run_id: str,
    *,
    model_name: str,
    source_filename: Optional[str],
    inference_threshold: float,
    score_floor: float,
    geojson_path: Optional[str],
    full_geojson_path: Optional[str],
    shapefile_path: Optional[str],
    overlay_path: Optional[str],
) -> Optional[str]:
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    return _write_manifest(
        run_id,
        {
            "task": "maskrcnn",
            "created_at": created_at,
            "model_name": model_name,
            "source_filename": source_filename or "",
            "inference_threshold": float(inference_threshold),
            "score_floor": float(score_floor),
            "artifacts": {
                "geojson": geojson_path,
                "full_geojson": full_geojson_path,
                "shapefile": shapefile_path,
                "overlay": overlay_path,
            },
        },
    )


def write_solar_panel_manifest(
    run_id: str,
    *,
    model_name: str,
    source_filename: Optional[str],
    inference_threshold: float,
    score_floor: float,
    geojson_path: Optional[str],
    full_geojson_path: Optional[str],
    shapefile_path: Optional[str],
    overlay_path: Optional[str],
) -> Optional[str]:
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    return _write_manifest(
        run_id,
        {
            "task": "solar_panel",
            "created_at": created_at,
            "model_name": model_name,
            "source_filename": source_filename or "",
            "inference_threshold": float(inference_threshold),
            "score_floor": float(score_floor),
            "artifacts": {
                "geojson": geojson_path,
                "full_geojson": full_geojson_path,
                "shapefile": shapefile_path,
                "overlay": overlay_path,
            },
        },
    )


def write_unet_manifest(
    run_id: str,
    *,
    model_name: str,
    source_filename: Optional[str],
    inference_threshold: float,
    geojson_path: Optional[str],
    shapefile_path: Optional[str],
    overlay_path: Optional[str],
    confidence_npz_path: Optional[str],
    meta_json_path: Optional[str],
    width: Optional[int],
    height: Optional[int],
) -> Optional[str]:
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    return _write_manifest(
        run_id,
        {
            "task": "unet",
            "created_at": created_at,
            "model_name": model_name,
            "source_filename": source_filename or "",
            "inference_threshold": float(inference_threshold),
            "width": width,
            "height": height,
            "artifacts": {
                "geojson": geojson_path,
                "shapefile": shapefile_path,
                "overlay": overlay_path,
                "confidence_npz": confidence_npz_path,
                "unet_run_meta": meta_json_path,
            },
        },
    )


def write_lulc_manifest(
    pred_id: str,
    *,
    model_name: str,
    source_filename: Optional[str],
    predictions_dir: str,
    annotation_png: str,
    meta_json: str,
    base_png: Optional[str],
    geotiff_path: Optional[str],
    seg_mode: Optional[str],
    buildings_geojson: Optional[str] = None,
    buildings_full_geojson: Optional[str] = None,
    unet_confidence_npz: Optional[str] = None,
    class_geotiff_path: Optional[str] = None,
) -> Optional[str]:
    """Pointer manifest for LULC outputs living under backend/lulc/predictions/."""
    if not pred_id:
        return None
    root = get_archive_root()
    run_dir = os.path.join(root, f"lulc_{pred_id}")
    try:
        os.makedirs(run_dir, exist_ok=True)
        path = os.path.join(run_dir, "manifest.json")
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "task": "lulc",
            "run_id": pred_id,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model_name": model_name,
            "source_filename": source_filename or "",
            "seg_mode": seg_mode or "",
            "predictions_dir": predictions_dir,
            "artifacts": {
                "annotation_png": annotation_png,
                "meta_json": meta_json,
                "base_png": base_png or "",
                "geotiff": geotiff_path or "",
                "class_geotiff": class_geotiff_path or "",
                "buildings_geojson": buildings_geojson or "",
                "buildings_full_geojson": buildings_full_geojson or "",
                "unet_confidence_npz": unet_confidence_npz or "",
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return path
    except OSError:
        return None


def read_manifest(run_dir_name: str) -> Optional[Dict[str, Any]]:
    root = get_archive_root()
    path = os.path.join(root, run_dir_name, "manifest.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_manifests(task: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    root = get_archive_root()
    out: List[Dict[str, Any]] = []
    try:
        names = sorted(os.listdir(root), reverse=True)
    except OSError:
        return out
    for name in names:
        m = read_manifest(name)
        if not m:
            continue
        if task and m.get("task") != task:
            continue
        out.append(m)
        if len(out) >= max(1, int(limit)):
            break
    return out
