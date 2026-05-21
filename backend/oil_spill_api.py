"""
Oil spill semantic segmentation API (DeepLabV3+).
Mounted at /oil_spill on the unified backend.

Endpoints:
  GET  /models
  POST /predict
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import uuid
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

_BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from proj_runtime import clear_bad_proj_env

clear_bad_proj_env()

import numpy as np
import rasterio
from rasterio.io import DatasetReader
from rasterio.windows import Window
from rasterio.warp import transform_bounds
from PIL import Image

import torch
import torch.nn.functional as F

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from model_paths import artifact_dir, ensure_dir
from oil_spill.seg_models import ResNet50DeepLabV3Plus

from roi_geotiff_clip import (
    bounds_look_like_wgs84_degrees,
    geometry_polygon_from_roi_geojson,
    maskrcnn_roi_geotiff_with_fallbacks,
    parse_roi_full_bounds_swne,
)

BASE_DIR = _BACKEND_ROOT
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

MODEL_ARTIFACT_DIR = artifact_dir("oil_spill")
ensure_dir(MODEL_ARTIFACT_DIR)

NUM_CLASSES = 5
LABEL_COLORS_RGB = np.array(
    [
        [0, 0, 0],
        [0, 255, 255],
        [255, 0, 0],
        [153, 76, 0],
        [0, 153, 0],
    ],
    dtype=np.uint8,
)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _oil_spill_max_upload_bytes() -> int:
    """Prefer OIL_SPILL_MAX_UPLOAD_BYTES, then MAX_UPLOAD_BYTES, then 3 GiB (large GeoTIFFs)."""
    raw = os.environ.get("OIL_SPILL_MAX_UPLOAD_BYTES", "").strip()
    if raw:
        return int(raw)
    raw = os.environ.get("MAX_UPLOAD_BYTES", "").strip()
    if raw:
        return int(raw)
    return 3 * 1024 * 1024 * 1024


MAX_UPLOAD_BYTES = _oil_spill_max_upload_bytes()
TILE_SIZE = int(os.environ.get("OIL_SPILL_TILE_SIZE", "512"))
TILE_OVERLAP = int(os.environ.get("OIL_SPILL_TILE_OVERLAP", "128"))
PREVIEW_SCALE = max(1, int(os.environ.get("OIL_SPILL_PREVIEW_SCALE", "4")))

logger = logging.getLogger("oil_spill_api")
logging.basicConfig(level=logging.INFO)

_model_cache: Dict[str, torch.nn.Module] = {}

_progress_lock = Lock()
_progress_state: Dict[str, Any] = {
    "progress": 0,
    "phase": "idle",
    "current_step": "",
    "total_chips": 0,
    "processed_chips": 0,
    "eta_seconds": None,
    "status": "idle",
}


def _reset_progress() -> None:
    with _progress_lock:
        _progress_state.update(
            progress=0,
            phase="idle",
            current_step="",
            total_chips=0,
            processed_chips=0,
            eta_seconds=None,
            status="idle",
        )


def _update_progress(**kwargs: Any) -> None:
    with _progress_lock:
        _progress_state.update(kwargs)
        if "processed_chips" in kwargs and "total_chips" in kwargs:
            tc = int(_progress_state.get("total_chips") or 0)
            pc = int(_progress_state.get("processed_chips") or 0)
            if tc > 0:
                _progress_state["progress"] = min(99, int(99 * pc / tc))


def _format_size(n: int) -> str:
    if n >= 1024 * 1024 * 1024:
        return f"{n / (1024 ** 3):.1f} GiB"
    if n >= 1024 * 1024:
        return f"{n / (1024 ** 2):.0f} MiB"
    return f"{n / 1024:.0f} KiB"

app = FastAPI(title="Oil Spill Segmentation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


@app.get("/progress")
def get_progress():
    """Same shape as Mask R-CNN / UNet progress (satellite UI polls this while uploading)."""
    with _progress_lock:
        return dict(_progress_state)


def _stats_path() -> str:
    override = os.environ.get("OIL_SPILL_IMAGE_STATS_JSON", "").strip()
    if override and os.path.isfile(override):
        return override
    p = os.path.join(MODEL_ARTIFACT_DIR, "image_stats.json")
    if os.path.isfile(p):
        return p
    raise FileNotFoundError(
        f"image_stats.json not found under {MODEL_ARTIFACT_DIR}. "
        "Add mean/std JSON or set OIL_SPILL_IMAGE_STATS_JSON."
    )


def _normalize_mean_std_rgb(raw_mean: Any, raw_std: Any) -> Tuple[np.ndarray, np.ndarray]:
    """Build (1,1,3) mean/std for RGB preprocessing.

    Supports:
      - Three-channel lists/tuples `[r,g,b]` (training export)
      - Single scalar per key (typical SAR / grayscale stats) → broadcast to 3 channels
    """
    m = np.asarray(raw_mean, dtype=np.float32).ravel()
    s = np.asarray(raw_std, dtype=np.float32).ravel()
    if m.size == 1:
        m = np.broadcast_to(m, (3,))
    if s.size == 1:
        s = np.broadcast_to(s, (3,))
    if m.size != 3 or s.size != 3:
        raise ValueError(
            "image_stats.json: mean and std must be length-3 RGB lists or single scalars "
            f"(got mean.shape={m.shape}, std.shape={s.shape})."
        )
    mean = m.reshape(1, 1, 3)
    std = s.reshape(1, 1, 3)
    std = np.where(std < 1e-8, 1e-8, std)
    return mean, std


def _load_mean_std() -> Tuple[np.ndarray, np.ndarray]:
    path = _stats_path()
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return _normalize_mean_std_rgb(d["mean"], d["std"])


def _list_weight_files() -> List[str]:
    out: List[str] = []
    if os.path.isdir(MODEL_ARTIFACT_DIR):
        for name in sorted(os.listdir(MODEL_ARTIFACT_DIR)):
            if name.lower().endswith(".pt"):
                out.append(name)
    return out


def _resolve_model_path(model_name: str) -> str:
    path = os.path.join(MODEL_ARTIFACT_DIR, model_name)
    if os.path.isfile(path):
        return path
    raise FileNotFoundError(f"Model not found: {model_name}")


def _get_model(model_name: str) -> ResNet50DeepLabV3Plus:
    key = model_name
    if key in _model_cache:
        return _model_cache[key]
    path = _resolve_model_path(model_name)
    m = ResNet50DeepLabV3Plus(num_classes=NUM_CLASSES, pretrained=False)
    state = torch.load(path, map_location=DEVICE, weights_only=False)
    m.load_state_dict(state, strict=True)
    m.to(DEVICE)
    m.eval()
    _model_cache[key] = m
    logger.info("Loaded oil spill model %s on %s", model_name, DEVICE)
    return m


def _window_to_uint8_rgb(chw: np.ndarray) -> np.ndarray:
    """(bands, h, w) -> uint8 RGB (h,w,3)."""
    if chw.dtype != np.uint8:
        amin = float(chw.min())
        amax = float(chw.max())
        if amax <= amin:
            chw = np.zeros_like(chw, dtype=np.uint8)
        else:
            chw = ((chw.astype(np.float32) - amin) / (amax - amin) * 255.0).astype(np.uint8)
    if chw.shape[0] == 1:
        b = chw[0]
        rgb = np.stack([b, b, b], axis=-1)
        return rgb
    if chw.shape[0] >= 3:
        r, g, br = chw[0], chw[1], chw[2]
        return np.stack([r, g, br], axis=-1)
    raise ValueError(f"Unsupported band count: {chw.shape[0]}")


def _preprocess_tile(hw_u8: np.ndarray, mean: np.ndarray, std: np.ndarray) -> torch.Tensor:
    x = hw_u8.astype(np.float32) / 255.0
    x = (x - mean) / std
    # NCHW
    chw = np.transpose(x, (2, 0, 1))
    t = torch.from_numpy(chw).unsqueeze(0).float().to(DEVICE)
    return t


def _count_inference_tiles(height: int, width: int) -> int:
    step = max(1, TILE_SIZE - TILE_OVERLAP)
    n = 0
    for row in range(0, height, step):
        for col in range(0, width, step):
            win_w = min(TILE_SIZE, width - col)
            win_h = min(TILE_SIZE, height - row)
            if win_w <= 0 or win_h <= 0:
                continue
            n += 1
    return max(1, n)


def _infer_full_raster(
    src: DatasetReader,
    model: ResNet50DeepLabV3Plus,
    mean: np.ndarray,
    std: np.ndarray,
) -> Tuple[np.ndarray, int]:
    """Returns (uint8 class map (H,W) full resolution, tile count)."""
    height, width = src.height, src.width
    acc = np.zeros((NUM_CLASSES, height, width), dtype=np.float32)
    wsum = np.zeros((height, width), dtype=np.float32)

    step = max(1, TILE_SIZE - TILE_OVERLAP)
    total_tiles = _count_inference_tiles(height, width)
    _update_progress(
        phase="inference",
        total_chips=total_tiles,
        processed_chips=0,
        current_step=f"Starting {total_tiles} tiles…",
        status="running",
    )

    processed = 0
    with torch.no_grad():
        for row in range(0, height, step):
            for col in range(0, width, step):
                win_w = min(TILE_SIZE, width - col)
                win_h = min(TILE_SIZE, height - row)
                if win_w <= 0 or win_h <= 0:
                    continue
                window = Window(col, row, win_w, win_h)
                bands = src.read(window=window)
                hw_rgb = _window_to_uint8_rgb(bands)
                tensor = _preprocess_tile(hw_rgb, mean, std)
                logits = model(tensor)
                probs = F.softmax(logits, dim=1).squeeze(0).cpu().numpy()

                acc[:, row : row + win_h, col : col + win_w] += probs
                wsum[row : row + win_h, col : col + win_w] += 1.0

                processed += 1
                if processed == 1 or processed == total_tiles or processed % max(1, total_tiles // 50) == 0:
                    _update_progress(
                        processed_chips=processed,
                        total_chips=total_tiles,
                        current_step=f"Tile {processed} / {total_tiles}",
                        phase="inference",
                        status="running",
                    )

    eps = 1e-8
    stacked = acc / (wsum[np.newaxis, :, :] + eps)
    pred = np.argmax(stacked, axis=0).astype(np.uint8)
    return pred, total_tiles


def _write_class_geotiff(
    source_path: str,
    class_arr: np.ndarray,
    dest_path: str,
    nodata: int = 255,
) -> bool:
    try:
        with rasterio.open(source_path) as src:
            transform = src.transform
            crs = src.crs
            h, w = src.height, src.width
        data = np.asarray(class_arr, dtype=np.uint8)
        if data.shape != (h, w):
            img = Image.fromarray(data, mode="L")
            img = img.resize((w, h), Image.Resampling.NEAREST)
            data = np.asarray(img, dtype=np.uint8)
        profile = {
            "driver": "GTiff",
            "height": h,
            "width": w,
            "count": 1,
            "dtype": "uint8",
            "transform": transform,
            "compress": "lzw",
            "nodata": int(nodata),
        }
        if crs is not None:
            profile["crs"] = crs
        with rasterio.open(dest_path, "w", **profile) as dst:
            dst.write(data, 1)
        return True
    except Exception as e:
        logger.exception("GeoTIFF write failed: %s", e)
        return False


def _class_to_rgb(pred: np.ndarray) -> np.ndarray:
    """H,W uint8 labels -> H,W,3 RGB."""
    h, w = pred.shape
    out = np.zeros((h, w, 3), dtype=np.uint8)
    for c in range(NUM_CLASSES):
        mask = pred == c
        out[mask] = LABEL_COLORS_RGB[c]
    return out


def _overlay_bounds_from_src(src_path: str) -> Optional[List[List[float]]]:
    try:
        with rasterio.open(src_path) as src:
            bounds_native = src.bounds
            crs = src.crs
            left, bottom, right, top = (
                bounds_native.left,
                bounds_native.bottom,
                bounds_native.right,
                bounds_native.top,
            )
            if crs is None and bounds_look_like_wgs84_degrees(left, bottom, right, top):
                return [[bottom, left], [top, right]]
            if crs is not None:
                minx, miny, maxx, maxy = transform_bounds(
                    crs, "EPSG:4326", left, bottom, right, top, densify_pts=21
                )
                return [[miny, minx], [maxy, maxx]]
    except Exception as e:
        logger.error("bounds: %s", e)
    return None


@app.get("/models")
def list_models():
    try:
        models = _list_weight_files()
        return {"models": models}
    except Exception as e:
        logger.exception("list_models: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict")
def predict(
    image: UploadFile = File(...),
    model_name: str = Query(...),
    threshold: float = Query(0.5, ge=0.0, le=1.0),
    roi_geojson: Optional[str] = Form(None),
    roi_full_bounds_swne: Optional[str] = Form(None),
):
    tmp_name = uuid.uuid4().hex + os.path.splitext(image.filename or "")[1]
    upload_path = os.path.join(tempfile.gettempdir(), tmp_name)
    paths_to_delete: List[str] = []

    try:
        _reset_progress()
        _update_progress(
            phase="upload",
            current_step="Reading upload…",
            status="running",
        )
        _ = threshold  # accepted for API compatibility with satellite UI; logits are not thresholded here
        uploaded_bytes = image.file.read()
        if len(uploaded_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Uploaded file too large ({_format_size(len(uploaded_bytes))}). "
                    f"Maximum for oil spill is {_format_size(MAX_UPLOAD_BYTES)}. "
                    "Set env OIL_SPILL_MAX_UPLOAD_BYTES (bytes), e.g. 5368709120 for 5 GiB."
                ),
            )
        with open(upload_path, "wb") as f:
            f.write(uploaded_bytes)
        paths_to_delete.append(upload_path)

        raster_path = upload_path
        roi_raw = (roi_geojson or "").strip()
        bounds_swne = parse_roi_full_bounds_swne((roi_full_bounds_swne or "").strip())
        if roi_raw:
            ext = os.path.splitext(upload_path)[1].lower()
            if ext not in (".tif", ".tiff"):
                raise HTTPException(
                    status_code=400,
                    detail="ROI polygon is only supported for GeoTIFF uploads.",
                )
            try:
                geom = geometry_polygon_from_roi_geojson(roi_raw)
                crop_path = maskrcnn_roi_geotiff_with_fallbacks(upload_path, geom, bounds_swne)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid roi_geojson (not valid JSON)")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            paths_to_delete.append(crop_path)
            raster_path = crop_path

        ext = os.path.splitext(raster_path)[1].lower()
        if ext not in (".tif", ".tiff"):
            raise HTTPException(
                status_code=400,
                detail="Oil spill inference expects a GeoTIFF (.tif / .tiff).",
            )

        mean, std = _load_mean_std()
        _update_progress(phase="loading_model", current_step="Loading model…", status="running")
        model = _get_model(model_name)

        with rasterio.open(raster_path) as src:
            bc = src.count
            if bc < 1:
                raise HTTPException(status_code=400, detail="GeoTIFF has no bands")
            width, height = src.width, src.height

            pred, n_tiles = _infer_full_raster(src, model, mean, std)

        _update_progress(
            phase="post_processing",
            current_step="Writing GeoTIFF outputs…",
            processed_chips=n_tiles,
            total_chips=n_tiles,
            progress=99,
            status="running",
        )

        uid = uuid.uuid4().hex
        class_name = f"oil_spill_classes_{uid}.tif"
        preview_name = f"oil_spill_preview_{uid}.png"
        rgb_name = f"oil_spill_preview_{uid}.tif"

        class_path = os.path.join(OUTPUT_DIR, class_name)
        preview_path = os.path.join(OUTPUT_DIR, preview_name)
        rgb_path = os.path.join(OUTPUT_DIR, rgb_name)

        if not _write_class_geotiff(raster_path, pred, class_path):
            raise HTTPException(status_code=500, detail="Failed to write class GeoTIFF")

        rgb_full = _class_to_rgb(pred)
        Image.fromarray(rgb_full, mode="RGB").save(preview_path, format="PNG")

        scale = PREVIEW_SCALE
        small_h = max(1, height // scale)
        small_w = max(1, width // scale)
        rgb_small = np.array(
            Image.fromarray(rgb_full).resize((small_w, small_h), Image.Resampling.NEAREST)
        )

        try:
            with rasterio.open(raster_path) as src:
                tr = src.transform
                crs = src.crs
                new_tr = rasterio.Affine(
                    tr.a * scale,
                    tr.b,
                    tr.c,
                    tr.d,
                    tr.e * scale,
                    tr.f,
                )
            profile = {
                "driver": "GTiff",
                "height": small_h,
                "width": small_w,
                "count": 3,
                "dtype": "uint8",
                "transform": new_tr,
                "compress": "lzw",
            }
            if crs is not None:
                profile["crs"] = crs
            data = np.transpose(rgb_small, (2, 0, 1))
            with rasterio.open(rgb_path, "w", **profile) as dst:
                dst.write(data)
        except Exception as e:
            logger.warning("RGB preview GeoTIFF optional write failed: %s", e)
            rgb_path = ""

        overlay_bounds = _overlay_bounds_from_src(raster_path)

        crs_display = None
        try:
            with rasterio.open(raster_path) as src:
                crs_display = src.crs.to_string() if src.crs is not None else None
                b = src.bounds
                if crs_display is None and bounds_look_like_wgs84_degrees(
                    b.left, b.bottom, b.right, b.top
                ):
                    crs_display = "EPSG:4326 (map grid)"
        except Exception:
            pass

        response: Dict[str, Any] = {
            "task": "oil_spill",
            "run_id": uid,
            "model_name": model_name,
            "width": width,
            "height": height,
            "crs": crs_display,
            "prediction_geotiff_url": f"/outputs/{class_name}",
            "preview_png_url": f"/outputs/{preview_name}",
            "preview_geotiff_url": f"/outputs/{rgb_name}" if rgb_path and os.path.isfile(rgb_path) else None,
            "overlay_url": f"/outputs/{preview_name}",
            "overlay_bounds": overlay_bounds,
            "num_classes": NUM_CLASSES,
            "class_legend": {
                "0": "sea_surface",
                "1": "oil_spill",
                "2": "oil_spill_look_alike",
                "3": "ship",
                "4": "land",
            },
        }
        _update_progress(
            phase="done",
            current_step="Complete",
            progress=100,
            status="done",
            processed_chips=n_tiles,
            total_chips=n_tiles,
            eta_seconds=0,
        )
        return JSONResponse(content=response)

    except HTTPException as he:
        _update_progress(
            phase="error",
            current_step=str(he.detail) if isinstance(he.detail, str) else "Request failed",
            status="error",
        )
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("predict failed: %s", e)
        _update_progress(phase="error", current_step=str(e), status="error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for p in paths_to_delete:
            try:
                if p and os.path.isfile(p):
                    os.unlink(p)
            except OSError:
                pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("OIL_SPILL_PORT", "8010")))
