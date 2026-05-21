import os
import io
import json
import sys
import uuid
import zipfile
import logging
import tempfile
import math
import time
from typing import Dict, Any, List, Tuple, Optional, Generator
from threading import Lock

_BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
from proj_runtime import clear_bad_proj_env
from sse_json import sse_json_dumps

clear_bad_proj_env()

import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window
import rasterio.features
from rasterio.warp import transform_bounds
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.validation import make_valid
import geopandas as gpd
from pydantic import BaseModel

import torch
import torch.nn as nn
from torchvision import transforms
from torchvision.models.detection import MaskRCNN
from torchvision.models.detection.backbone_utils import resnet_fpn_backbone
from torchvision.models.detection.transform import GeneralizedRCNNTransform

from fastapi import FastAPI, File, UploadFile, Query, HTTPException, Form
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from model_paths import artifact_dir, legacy_backend_models_dir, ensure_dir
from detection_postprocess import finalize_instance_detection_polygons, regularize_detection_polygons
from roi_geotiff_clip import (
    bounds_look_like_wgs84_degrees,
    geometry_polygon_from_roi_geojson,
    maskrcnn_roi_geotiff_with_fallbacks,
    parse_roi_full_bounds_swne,
)
from prediction_archive import (
    list_manifests,
    read_manifest,
    validate_run_id as archive_validate_run_id,
    write_maskrcnn_manifest,
    write_solar_panel_manifest,
)
from lulc_detection_attach import attach_building_detection_to_lulc
from solar_panel_resunet import (
    extract_solar_instances_from_tile,
    load_solar_model,
    prepare_rgb_uint8_for_solar,
)
from esri_dlpk_detection import (
    is_esri_model_name,
    list_esri_model_ids,
    resolve_esri_model_dir,
    load_esri_maskrcnn,
    load_inference_overrides,
    load_emd,
    parse_export_config,
    raster_window_to_esri_input,
    upsample_detection_output_to_native_hw,
)


# -------------------- Configuration --------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = artifact_dir("maskrcnn")
SOLAR_PANEL_DIR = artifact_dir("solar_panel")
LEGACY_MODEL_DIR = legacy_backend_models_dir()
ensure_dir(MODEL_DIR)
ensure_dir(SOLAR_PANEL_DIR)
ensure_dir(LEGACY_MODEL_DIR)
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)
run_id_to_files = {}

# Tile / inference config
TILE_SIZE = int(os.environ.get("TILE_SIZE", 1024))
TILE_OVERLAP = int(os.environ.get("TILE_OVERLAP", 128))
BATCH_TILES = int(os.environ.get("BATCH_TILES", 4))  # how many tiles to send to model at once
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 800 * 1024 * 1024))  # 800MB
# Mask R-CNN: retain boxes with score >= floor; UI ``threshold`` filters exports.
# Solar ResUNet: request ``threshold`` is the mask cutoff (same as standalone ``predict_mask(..., threshold=)``).
# Exports include all polygonized instances (standalone script does not filter by mean probability).
MASKRCNN_SCORE_FLOOR = float(os.environ.get("MASKRCNN_SCORE_FLOOR", "0.05"))
SOLAR_PANEL_SCORE_FLOOR = float(os.environ.get("SOLAR_PANEL_SCORE_FLOOR", "0.05"))
SOLAR_TILE_SIZE = int(os.environ.get("SOLAR_TILE_SIZE", str(TILE_SIZE)))
SOLAR_TILE_OVERLAP = int(os.environ.get("SOLAR_TILE_OVERLAP", str(TILE_OVERLAP)))

# Gated UI-only post-processing trials (preview / apply); off by default.
ENABLE_POSTPROCESS_LAB = os.environ.get("ENABLE_POSTPROCESS_LAB", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Align GDAL CRS resolution with EPSG registry (helps GeoTIFF+ROI on Windows / mixed PROJ installs).
os.environ.setdefault("GTIFF_SRS_SOURCE", "EPSG")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("maskrcnn_api")
logger.info(f"Device: {DEVICE}")

# FastAPI
app = FastAPI(title="MaskRCNN Detection API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

# -------------------- Progress Tracking --------------------
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


def _reset_progress():
    with _progress_lock:
        _progress_state.update(
            progress=0, phase="idle", current_step="",
            total_chips=0, processed_chips=0, eta_seconds=None, status="idle",
        )


def _update_progress(*, phase: str = None, current_step: str = None,
                     total_chips: int = None, processed_chips: int = None,
                     eta_seconds: float = None, status: str = None):
    with _progress_lock:
        if phase is not None:
            _progress_state["phase"] = phase
        if current_step is not None:
            _progress_state["current_step"] = current_step
        if total_chips is not None:
            _progress_state["total_chips"] = total_chips
        if processed_chips is not None:
            _progress_state["processed_chips"] = processed_chips
        if eta_seconds is not None:
            _progress_state["eta_seconds"] = eta_seconds
        if status is not None:
            _progress_state["status"] = status
        total = _progress_state["total_chips"]
        done = _progress_state["processed_chips"]
        _progress_state["progress"] = int((done / total) * 100) if total > 0 else 0


@app.get("/progress")
def get_progress():
    with _progress_lock:
        return dict(_progress_state)

# -------------------- Authentication Mock --------------------
class PostprocessLabBody(BaseModel):
    run_id: str
    task: str
    inference_threshold: Optional[float] = None
    regularize_mode: Optional[str] = None
    regularize_tolerance: Optional[float] = None
    iou_threshold: Optional[float] = None
    seam_merge_gap: Optional[float] = None
    merge_touching: Optional[bool] = None


class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/Auth/login")
async def login(request: LoginRequest):
    # Mock authentication - accepts any credentials
    return {
        "token": "mock-jwt-token-" + uuid.uuid4().hex,
        "role": "user",
        "email": request.email
    }

# -------------------- Model loading & cache --------------------
model_cache: Dict[str, nn.Module] = {}
model_cache_lock = Lock()
MAX_CACHED_MODELS = 4


def _sanitize_model_name(name: str) -> str:
    name = os.path.basename(name)
    if not (name.endswith('.pth') or name.endswith('.pt')):
        name = name + '.pth'
    return name


def _is_solar_panel_model(model_name: str) -> bool:
    bn = os.path.basename(model_name).lower()
    allow = os.environ.get("SOLAR_PANEL_MODEL_NAMES", "").strip()
    if allow:
        allowed = {x.strip().lower() for x in allow.split(",") if x.strip()}
        if _sanitize_model_name(model_name).lower() in allowed:
            return True
    if bn.startswith("solarpanel") and (bn.endswith(".pth") or bn.endswith(".pt")):
        return True
    if "_solar" in bn and (bn.endswith(".pth") or bn.endswith(".pt")):
        return True
    return False


def _resolve_solar_panel_weights(model_name: str) -> str:
    name = _sanitize_model_name(model_name)
    p = os.path.join(SOLAR_PANEL_DIR, name)
    if os.path.isfile(p):
        return p
    raise FileNotFoundError(f"Solar panel weights not found: {name} under {SOLAR_PANEL_DIR}")


def _make_key(model_name: str, channels: int) -> str:
    return f"{model_name}::ch{channels}"


def get_detection_backbone(in_channels: int):
    backbone = resnet_fpn_backbone(backbone_name='resnet50', weights=None)
    # Replace conv1 to accept in_channels
    backbone.body.conv1 = torch.nn.Conv2d(in_channels=in_channels, out_channels=64, kernel_size=7, stride=2, padding=3, bias=False)
    return backbone


def load_model(model_name: str, in_channels: int) -> nn.Module:
    model_name = _sanitize_model_name(model_name)
    key = _make_key(model_name, in_channels)

    with model_cache_lock:
        if key in model_cache:
            return model_cache[key]

    model_path = os.path.join(MODEL_DIR, model_name)
    if not os.path.exists(model_path):
        model_path = os.path.join(LEGACY_MODEL_DIR, model_name)
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_name} (maskrcnn or legacy backend/models)")

    # Build model and load weights
    num_classes = 2  # background + object
    backbone = get_detection_backbone(in_channels)
    model = MaskRCNN(backbone, num_classes=num_classes)

    state = torch.load(model_path, map_location=DEVICE)
    # accommodate checkpoints that wrap into dicts
    if isinstance(state, dict) and 'model' in state:
        state = state['model']

    # If conv1 weights exist but channels mismatch, try to adapt
    conv1_key = 'backbone.body.conv1.weight'
    if isinstance(state, dict) and conv1_key in state:
        w = state[conv1_key]
        if w.shape[1] != in_channels:
            logger.info(f"Adapting conv1 weights (saved ch={w.shape[1]} -> required ch={in_channels})")
            with torch.no_grad():
                if in_channels == 4 and w.shape[1] == 3:
                    extra = w.mean(dim=1, keepdim=True)
                    state[conv1_key] = torch.cat([w, extra], dim=1)
                elif in_channels == 3 and w.shape[1] == 4:
                    state[conv1_key] = w[:, :3, :, :].clone()
                else:
                    # generic: repeat or truncate
                    if w.shape[1] < in_channels:
                        repeats = int(math.ceil(in_channels / w.shape[1]))
                        state[conv1_key] = w.repeat(1, repeats, 1, 1)[:, :in_channels, :, :].clone()
                    else:
                        state[conv1_key] = w[:, :in_channels, :, :].clone()

    try:
        model.load_state_dict(state, strict=False)
    except Exception as e:
        logger.warning(f"Non-fatal state_dict load issue: {e}")
        model.load_state_dict(state, strict=False)

    # Set transforms (means/std) for model
    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]
    if in_channels == 4:
        mean = mean + [0.5]
        std = std + [0.25]
    model.transform = GeneralizedRCNNTransform(min_size=800, max_size=1333, image_mean=mean, image_std=std)

    model.to(DEVICE)
    model.eval()

    with model_cache_lock:
        if len(model_cache) >= MAX_CACHED_MODELS:
            # remove an arbitrary cache entry (simple eviction)
            k = next(iter(model_cache))
            logger.info(f"Evicting cached model {k}")
            del model_cache[k]
        model_cache[key] = model

    logger.info(f"Loaded model {model_name} for {in_channels} channels")
    return model

# -------------------- Utilities --------------------


def sanitize_float(x: float) -> Any:
    if x is None:
        return None
    try:
        if math.isfinite(x):
            return float(x)
    except Exception:
        pass
    return None


def save_geojson_and_shapefile(gdf: gpd.GeoDataFrame, out_prefix: str) -> Tuple[str, str]:
    # gdf: expected to be in EPSG:4326 for saving (GeoJSON for web)
    geojson_path = os.path.join(OUTPUT_DIR, out_prefix + '.geojson')
    zip_path = os.path.join(OUTPUT_DIR, out_prefix + '.zip')

    if gdf.empty:
        # create empty geojson
        gdf.to_file(geojson_path, driver='GeoJSON')
        with zipfile.ZipFile(zip_path, 'w'):
            pass
        return geojson_path, zip_path

    gdf.to_file(geojson_path, driver='GeoJSON')
    # write shapefile components into a temp dir then zip
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, out_prefix)
        gdf.to_file(base + '.shp')
        # zip all files with prefix
        files = [f for f in os.listdir(td) if f.startswith(out_prefix)]
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for f in files:
                zf.write(os.path.join(td, f), arcname=f)
    return geojson_path, zip_path


def _postprocess_lab_or_403() -> None:
    if not ENABLE_POSTPROCESS_LAB:
        raise HTTPException(status_code=403, detail="Post-process lab is disabled (set ENABLE_POSTPROCESS_LAB=1).")


def _maskrcnn_resolve_full_geojson_path(run_id: str) -> Optional[str]:
    if run_id in run_id_to_files:
        p = run_id_to_files[run_id].get("full_geojson")
        if p and os.path.isfile(p):
            return p
    m = read_manifest(run_id)
    if m and m.get("task") in ("maskrcnn", "solar_panel"):
        p = (m.get("artifacts") or {}).get("full_geojson")
        if p and os.path.isfile(p):
            return p
    cand = os.path.join(OUTPUT_DIR, f"detections_{run_id}_full.geojson")
    return cand if os.path.isfile(cand) else None


def _maskrcnn_resolve_output_paths(run_id: str) -> Tuple[Optional[str], Optional[str]]:
    g_path, z_path = None, None
    if run_id in run_id_to_files:
        g_path = run_id_to_files[run_id].get("geojson")
        z_path = run_id_to_files[run_id].get("shapefile")
    m = read_manifest(run_id)
    if m and m.get("task") in ("maskrcnn", "solar_panel"):
        art = m.get("artifacts") or {}
        if not g_path or not os.path.isfile(g_path):
            g_path = art.get("geojson")
        if not z_path or not os.path.isfile(z_path):
            z_path = art.get("shapefile")
    if g_path and not os.path.isfile(g_path):
        g_path = None
    if z_path and not os.path.isfile(z_path):
        z_path = None
    if not g_path:
        cand = os.path.join(OUTPUT_DIR, f"detections_{run_id}.geojson")
        g_path = cand if os.path.isfile(cand) else None
    if not z_path:
        cand = os.path.join(OUTPUT_DIR, f"detections_{run_id}.zip")
        z_path = cand if os.path.isfile(cand) else None
    return g_path, z_path


def _fc_to_polygons_and_confidence(fc: dict) -> Tuple[List[Polygon], List[float]]:
    polys: List[Polygon] = []
    confs: List[float] = []
    for f in fc.get("features") or []:
        geom = f.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
            if not getattr(g, "is_valid", True):
                g = make_valid(g)
            if g is None or g.is_empty:
                continue
            props = f.get("properties") or {}
            c_raw = props.get("confidence")
            c = float(c_raw) if c_raw is not None else 0.0
            if isinstance(g, Polygon):
                if g.area > 0:
                    polys.append(g)
                    confs.append(c)
            elif isinstance(g, MultiPolygon):
                for gg in g.geoms:
                    if isinstance(gg, Polygon) and gg.area > 0:
                        polys.append(gg)
                        confs.append(c)
        except Exception:
            continue
    return polys, confs


def _gdf4326_from_polygons_with_attrs(merged_list: List[Polygon]) -> gpd.GeoDataFrame:
    gdf_4326 = gpd.GeoDataFrame(geometry=merged_list, crs="EPSG:4326")
    if gdf_4326.empty:
        return gdf_4326
    gdf_4326["area"] = gdf_4326.geometry.area
    gdf_4326["length"] = gdf_4326.geometry.length
    gdf_4326["coords"] = gdf_4326.geometry.apply(
        lambda g: list(g.exterior.coords) if isinstance(g, Polygon) else []
    )
    return gdf_4326


def _maskrcnn_lab_merge_polygons(body: PostprocessLabBody, polys: List[Polygon], task: str) -> List[Polygon]:
    if task == "solar_panel":
        return regularize_detection_polygons(
            polys,
            mode=body.regularize_mode,
            tolerance=body.regularize_tolerance,
        )
    return finalize_instance_detection_polygons(
        polys,
        iou_threshold=body.iou_threshold,
        seam_merge_gap=body.seam_merge_gap,
        merge_touching=body.merge_touching,
        regularize_mode=body.regularize_mode,
        regularize_tolerance=body.regularize_tolerance,
    )


def _maskrcnn_lab_load_and_process(body: PostprocessLabBody) -> Tuple[List[Polygon], gpd.GeoDataFrame, Dict[str, Any]]:
    path = _maskrcnn_resolve_full_geojson_path(body.run_id)
    if not path:
        raise HTTPException(status_code=404, detail="full_geojson not found for run_id")
    with open(path, "r", encoding="utf-8") as f:
        fc = json.load(f)
    polys, confs = _fc_to_polygons_and_confidence(fc)
    m = read_manifest(body.run_id)
    task = (body.task or "").strip().lower()
    if task not in ("maskrcnn", "solar_panel"):
        if m and m.get("task") in ("maskrcnn", "solar_panel"):
            task = str(m.get("task"))
        else:
            raise HTTPException(status_code=400, detail="task must be maskrcnn or solar_panel")
    thr_default = float(m.get("inference_threshold")) if m and m.get("inference_threshold") is not None else MASKRCNN_SCORE_FLOOR
    thr = float(body.inference_threshold) if body.inference_threshold is not None else thr_default
    if task == "maskrcnn":
        polys = [p for p, c in zip(polys, confs) if c >= thr]
    merged = _maskrcnn_lab_merge_polygons(body, polys, task)
    gdf = _gdf4326_from_polygons_with_attrs(merged)
    total_area = float(gdf["area"].sum()) if not gdf.empty else 0.0
    stats = {"count": len(gdf), "total_area": sanitize_float(total_area)}
    return merged, gdf, stats


# -------------------- Core processing --------------------


def iter_tile_windows(width: int, height: int, tile_size: int = TILE_SIZE, overlap: int = TILE_OVERLAP):
    step = tile_size - overlap
    if step <= 0:
        raise ValueError("tile_size must be larger than overlap")
    nx = math.ceil((width - overlap) / step)
    ny = math.ceil((height - overlap) / step)
    for i in range(nx):
        for j in range(ny):
            xoff = i * step
            yoff = j * step
            w = tile_size if xoff + tile_size <= width else width - xoff
            h = tile_size if yoff + tile_size <= height else height - yoff
            yield (xoff, yoff, int(w), int(h))


def tile_to_tensor(tile_arr: np.ndarray) -> torch.Tensor:
    # tile_arr shape: (bands, H, W) -> convert to (C,H,W) float tensor normalized [0,1]
    t = torch.from_numpy(tile_arr.astype(np.float32) / 255.0)
    return t.to(DEVICE)


def _extract_scored_instances_from_output(
    out: Dict[str, Any], meta_tile: Tuple[int, int, int, int, Affine], score_floor: float
) -> List[Tuple[Polygon, float, int]]:
    """Instance polygons in native CRS with score and class label (for analysis / full GeoJSON)."""
    out_list: List[Tuple[Polygon, float, int]] = []
    scores = out.get("scores", torch.tensor([])).cpu().numpy()
    masks = out.get("masks", torch.tensor([]))
    labels_t = out.get("labels", None)
    if masks is None or masks.numel() == 0 or len(scores) == 0:
        return out_list
    labels_np = labels_t.cpu().numpy() if labels_t is not None and labels_t.numel() > 0 else None
    tile_tr = meta_tile[4]
    n = int(min(len(scores), masks.shape[0]))
    for i in range(n):
        if float(scores[i]) < score_floor:
            continue
        m = masks[i]
        mask_np = (m[0].cpu().numpy() >= 0.5).astype("uint8")
        if mask_np.ndim == 3:
            mask_np = mask_np[0]
        sc = float(scores[i])
        lab = int(labels_np[i]) if labels_np is not None and i < len(labels_np) else 1
        for geom, val in rasterio.features.shapes(mask_np, transform=tile_tr):
            if val != 1:
                continue
            try:
                poly = shape(geom)
                if not poly.is_valid:
                    poly = make_valid(poly)
                if poly.is_empty or poly.area <= 0:
                    continue
                out_list.append((poly, sc, lab))
            except Exception:
                logger.exception("failed to convert geom to polygon")
                continue
    return out_list


def _maskrcnn_polygons_to_preview_geojson(
    polygons: List[Polygon], crs, bounds_native
) -> dict:
    crs_gdf = crs
    if crs_gdf is None and bounds_look_like_wgs84_degrees(
        bounds_native.left, bounds_native.bottom, bounds_native.right, bounds_native.top
    ):
        crs_gdf = "EPSG:4326"
    if not polygons:
        return {"type": "FeatureCollection", "features": []}
    gdf = gpd.GeoDataFrame(geometry=polygons, crs=crs_gdf)
    g4326 = gdf.copy()
    try:
        if g4326.crs is not None and g4326.crs.to_string() != "EPSG:4326":
            g4326 = g4326.to_crs("EPSG:4326")
    except Exception as e:
        logger.error("preview reproject failed: %s", e)
        return {"type": "FeatureCollection", "features": []}
    return json.loads(g4326.to_json())


def _maskrcnn_raster_extent_bounds_wgs84(crs, bounds_native) -> Optional[list]:
    left, bottom, right, top = bounds_native.left, bounds_native.bottom, bounds_native.right, bounds_native.top
    try:
        if crs is None and bounds_look_like_wgs84_degrees(left, bottom, right, top):
            return [[bottom, left], [top, right]]
        if crs is not None:
            minx, miny, maxx, maxy = transform_bounds(
                crs, "EPSG:4326", left, bottom, right, top, densify_pts=21
            )
            return [[miny, minx], [maxy, maxx]]
    except Exception as e:
        logger.error("extent bounds WGS84 failed: %s", e)
    return None


def _solar_panel_streaming_events(
    raster_path: str,
    model_name: str,
    threshold: float,
    stream_tile_interval: int,
    source_filename: Optional[str] = None,
    lulc_prediction_id: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """SSE stream for ResUNet-A solar segmentation (same envelope as Mask R-CNN stream)."""
    stream_tile_interval = max(1, min(int(stream_tile_interval), 200))
    _reset_progress()
    _update_progress(phase="loading_model", current_step="Loading solar model...", status="running")
    try:
        solar_path = _resolve_solar_panel_weights(model_name)
        model_solar = load_solar_model(solar_path, DEVICE)
        with rasterio.open(raster_path) as src:
            width = src.width
            height = src.height
            crs = src.crs
            transform = src.transform
            bounds_native = src.bounds
            band_count = src.count
            if band_count not in (3, 4):
                yield {"type": "error", "error": f"Unsupported band count: {band_count}. Expect 3 or 4."}
                return

            crs_display = crs.to_string() if crs is not None else None
            if crs_display is None and bounds_look_like_wgs84_degrees(
                bounds_native.left, bounds_native.bottom, bounds_native.right, bounds_native.top
            ):
                crs_display = "EPSG:4326 (map grid)"
            extent_wgs84 = _maskrcnn_raster_extent_bounds_wgs84(crs, bounds_native)
            tile_specs = list(iter_tile_windows(width, height, SOLAR_TILE_SIZE, SOLAR_TILE_OVERLAP))
            total_tiles = len(tile_specs)
            logger.info(
                "[predict-stream] Solar ResUNet: %s tiles; preview every %s tiles",
                total_tiles,
                stream_tile_interval,
            )
            yield {
                "type": "start",
                "task": "solar_panel",
                "crs": crs_display,
                "overlay_bounds": extent_wgs84,
                "width": width,
                "height": height,
                "total_tiles": total_tiles,
                "stream_interval": stream_tile_interval,
                "message": f"Solar detection: {total_tiles} tiles — map preview every {stream_tile_interval}",
            }

            scored_instances: List[Tuple[Polygon, float, int]] = []
            tiles_processed = 0
            _start_time = time.time()
            last_yielded_tile = 0
            _update_progress(
                phase="inference",
                current_step="Starting tile inference...",
                total_chips=total_tiles,
                processed_chips=0,
                status="running",
            )

            def iter_progress_events(is_final_flush: bool):
                nonlocal last_yielded_tile
                n = stream_tile_interval
                while last_yielded_tile + n <= tiles_processed:
                    last_yielded_tile += n
                    preview_polys = [p for p, _sc, _lb in scored_instances]
                    gj = _maskrcnn_polygons_to_preview_geojson(preview_polys, crs, bounds_native)
                    nfeat = len(gj.get("features", []) or [])
                    msg = (
                        f"Tiles {last_yielded_tile}/{total_tiles}: merged preview → map ({nfeat} features)"
                    )
                    logger.info("[predict-stream] %s", msg)
                    yield {
                        "type": "progress",
                        "geojson": gj,
                        "tiles_processed": last_yielded_tile,
                        "total_tiles": total_tiles,
                        "message": msg,
                    }
                if is_final_flush and tiles_processed > last_yielded_tile:
                    last_yielded_tile = tiles_processed
                    preview_polys = [p for p, _sc, _lb in scored_instances]
                    gj = _maskrcnn_polygons_to_preview_geojson(preview_polys, crs, bounds_native)
                    nfeat = len(gj.get("features", []) or [])
                    msg = (
                        f"Tiles {tiles_processed}/{total_tiles}: final preview chunk → map ({nfeat} features)"
                    )
                    logger.info("[predict-stream] %s", msg)
                    yield {
                        "type": "progress",
                        "geojson": gj,
                        "tiles_processed": tiles_processed,
                        "total_tiles": total_tiles,
                        "message": msg,
                    }

            for spec in tile_specs:
                xoff, yoff, w, h = spec
                window = Window(col_off=xoff, row_off=yoff, width=w, height=h)
                arr = src.read(window=window)
                try:
                    rgb = prepare_rgb_uint8_for_solar(arr)
                except ValueError as e:
                    logger.warning("Solar tile skip %s: %s", spec, e)
                    tiles_processed += 1
                    _update_progress(
                        processed_chips=tiles_processed,
                        current_step=f"Tile {tiles_processed}/{total_tiles} (skipped)",
                    )
                    for ev in iter_progress_events(is_final_flush=False):
                        yield ev
                    continue
                tile_transform = rasterio.windows.transform(window, transform)
                scored_instances.extend(
                    extract_solar_instances_from_tile(
                        rgb,
                        model_solar,
                        DEVICE,
                        0.0,
                        tile_transform,
                        binary_threshold=threshold,
                    )
                )
                tiles_processed += 1
                elapsed = time.time() - _start_time
                rate = tiles_processed / elapsed if elapsed > 0 else 0
                remaining = total_tiles - tiles_processed
                eta = remaining / rate if rate > 0 else None
                _update_progress(
                    processed_chips=tiles_processed,
                    current_step=f"Tile {tiles_processed}/{total_tiles}",
                    eta_seconds=round(eta, 1) if eta else None,
                )
                for ev in iter_progress_events(is_final_flush=False):
                    yield ev

            for ev in iter_progress_events(is_final_flush=True):
                yield ev

            _update_progress(
                phase="post_processing",
                current_step="Merging polygons...",
                processed_chips=total_tiles,
                status="running",
            )

            done_payload = _package_detection_results(
                scored_instances,
                crs=crs,
                bounds_native=bounds_native,
                transform=transform,
                width=width,
                height=height,
                threshold=threshold,
                task="solar_panel",
                model_name=model_name,
                source_filename=source_filename or "",
                total_tiles=total_tiles,
                lulc_prediction_id=lulc_prediction_id,
            )

            _update_progress(
                phase="done",
                current_step="Complete",
                processed_chips=total_tiles,
                eta_seconds=0,
                status="done",
            )

            yield {"type": "done", **done_payload}
    except Exception as e:
        logger.exception("Solar streaming prediction failed: %s", e)
        _update_progress(phase="error", current_step=str(e), status="error")
        yield {"type": "error", "error": str(e)}


def _esri_streaming_events(
    raster_path: str,
    model_name: str,
    threshold: float,
    stream_tile_interval: int,
    source_filename: Optional[str] = None,
    lulc_prediction_id: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """SSE stream for Esri EMD + maskrcnn_resnet50_fpn (same envelope as Mask R-CNN stream)."""
    stream_tile_interval = max(1, min(int(stream_tile_interval), 200))
    _reset_progress()
    _update_progress(phase="loading_model", current_step="Loading Esri model...", status="running")
    try:
        model_dir = resolve_esri_model_dir(model_name)
        overrides = load_inference_overrides(model_dir)
        tile_sz = int(overrides.get("tile_size", TILE_SIZE))
        tile_ov = int(overrides.get("tile_overlap", TILE_OVERLAP))
        model_esri, cfg = load_esri_maskrcnn(model_dir, DEVICE)

        with rasterio.open(raster_path) as src:
            width = src.width
            height = src.height
            crs = src.crs
            transform = src.transform
            bounds_native = src.bounds
            band_count = src.count
            need_b = max(cfg.extract_bands) + 1
            if band_count < need_b:
                yield {
                    "type": "error",
                    "error": f"Raster has {band_count} bands; Esri model needs at least {need_b} for ExtractBands {cfg.extract_bands}.",
                }
                return

            crs_display = crs.to_string() if crs is not None else None
            if crs_display is None and bounds_look_like_wgs84_degrees(
                bounds_native.left, bounds_native.bottom, bounds_native.right, bounds_native.top
            ):
                crs_display = "EPSG:4326 (map grid)"
            extent_wgs84 = _maskrcnn_raster_extent_bounds_wgs84(crs, bounds_native)
            tile_specs = list(iter_tile_windows(width, height, tile_sz, tile_ov))
            total_tiles = len(tile_specs)
            logger.info(
                "[predict-stream] Esri: %s tiles; preview every %s tiles",
                total_tiles,
                stream_tile_interval,
            )
            yield {
                "type": "start",
                "task": "maskrcnn",
                "model_family": "esri",
                "model_name": model_name,
                "crs": crs_display,
                "overlay_bounds": extent_wgs84,
                "width": width,
                "height": height,
                "total_tiles": total_tiles,
                "total_chips": total_tiles,
                "stream_interval": stream_tile_interval,
                "message": f"Esri detection: {total_tiles} tiles — map preview every {stream_tile_interval}",
            }

            scored_instances: List[Tuple[Polygon, float, int]] = []
            tiles_processed = 0
            _start_time = time.time()
            last_yielded_tile = 0
            _update_progress(
                phase="inference",
                current_step="Starting tile inference...",
                total_chips=total_tiles,
                processed_chips=0,
                status="running",
            )

            batch_tensors: List[torch.Tensor] = []
            batch_meta: List[Tuple[int, int, int, int, Affine]] = []

            def process_batch_outputs(outputs, metas):
                nonlocal scored_instances
                for out, meta in zip(outputs, metas):
                    _x, _y, w, h, _tr = meta
                    out_native = upsample_detection_output_to_native_hw(out, int(h), int(w))
                    scored_instances.extend(
                        _extract_scored_instances_from_output(out_native, meta, MASKRCNN_SCORE_FLOOR)
                    )

            def iter_progress_events(is_final_flush: bool):
                nonlocal last_yielded_tile
                n = stream_tile_interval
                while last_yielded_tile + n <= tiles_processed:
                    last_yielded_tile += n
                    preview_polys = [p for p, sc, _lb in scored_instances if sc >= threshold]
                    gj = _maskrcnn_polygons_to_preview_geojson(preview_polys, crs, bounds_native)
                    nfeat = len(gj.get("features", []) or [])
                    msg = (
                        f"Tiles {last_yielded_tile}/{total_tiles}: merged preview → map "
                        f"({nfeat} features)"
                    )
                    logger.info("[predict-stream] Esri %s", msg)
                    yield {
                        "type": "progress",
                        "model_family": "esri",
                        "model_name": model_name,
                        "geojson": gj,
                        "tiles_processed": last_yielded_tile,
                        "total_tiles": total_tiles,
                        "chips_processed": last_yielded_tile,
                        "total_chips": total_tiles,
                        "message": msg,
                    }
                if is_final_flush and tiles_processed > last_yielded_tile:
                    last_yielded_tile = tiles_processed
                    preview_polys = [p for p, sc, _lb in scored_instances if sc >= threshold]
                    gj = _maskrcnn_polygons_to_preview_geojson(preview_polys, crs, bounds_native)
                    nfeat = len(gj.get("features", []) or [])
                    msg = (
                        f"Tiles {tiles_processed}/{total_tiles}: final preview chunk → map "
                        f"({nfeat} features)"
                    )
                    logger.info("[predict-stream] Esri %s", msg)
                    yield {
                        "type": "progress",
                        "model_family": "esri",
                        "model_name": model_name,
                        "geojson": gj,
                        "tiles_processed": tiles_processed,
                        "total_tiles": total_tiles,
                        "chips_processed": tiles_processed,
                        "total_chips": total_tiles,
                        "message": msg,
                    }

            for spec in tile_specs:
                xoff, yoff, w, h = spec
                window = Window(col_off=xoff, row_off=yoff, width=w, height=h)
                arr = src.read(window=window)
                tile_transform = rasterio.windows.transform(window, transform)
                try:
                    tile_t = raster_window_to_esri_input(arr, cfg, DEVICE)
                except (ValueError, KeyError) as e:
                    logger.warning("Esri tile skip %s: %s", spec, e)
                    tiles_processed += 1
                    _update_progress(
                        processed_chips=tiles_processed,
                        current_step=f"Tile {tiles_processed}/{total_tiles} (skipped)",
                    )
                    for ev in iter_progress_events(is_final_flush=False):
                        yield ev
                    continue

                batch_tensors.append(tile_t)
                batch_meta.append((xoff, yoff, w, h, tile_transform))

                if len(batch_tensors) >= BATCH_TILES:
                    with torch.no_grad():
                        outputs = model_esri(batch_tensors)
                    process_batch_outputs(outputs, batch_meta)
                    tiles_processed += len(batch_meta)
                    elapsed = time.time() - _start_time
                    rate = tiles_processed / elapsed if elapsed > 0 else 0
                    remaining = total_tiles - tiles_processed
                    eta = remaining / rate if rate > 0 else None
                    _update_progress(
                        processed_chips=tiles_processed,
                        current_step=f"Tile {tiles_processed}/{total_tiles}",
                        eta_seconds=round(eta, 1) if eta else None,
                    )
                    for ev in iter_progress_events(is_final_flush=False):
                        yield ev
                    batch_tensors = []
                    batch_meta = []

            if batch_tensors:
                with torch.no_grad():
                    outputs = model_esri(batch_tensors)
                process_batch_outputs(outputs, batch_meta)
                tiles_processed += len(batch_meta)
                _update_progress(
                    processed_chips=tiles_processed,
                    current_step=f"Tile {tiles_processed}/{total_tiles}",
                    eta_seconds=0,
                )
                for ev in iter_progress_events(is_final_flush=False):
                    yield ev

            for ev in iter_progress_events(is_final_flush=True):
                yield ev

            _update_progress(
                phase="post_processing",
                current_step="Merging polygons...",
                processed_chips=total_tiles,
                status="running",
            )

            done_payload = _package_detection_results(
                scored_instances,
                crs=crs,
                bounds_native=bounds_native,
                transform=transform,
                width=width,
                height=height,
                threshold=threshold,
                task="maskrcnn",
                model_name=model_name,
                source_filename=source_filename or "",
                total_tiles=total_tiles,
                lulc_prediction_id=lulc_prediction_id,
                model_family="esri",
            )

            _update_progress(
                phase="done",
                current_step="Complete",
                processed_chips=total_tiles,
                eta_seconds=0,
                status="done",
            )

            yield {"type": "done", "model_family": "esri", "model_name": model_name, **done_payload}
    except Exception as e:
        logger.exception("Esri streaming prediction failed: %s", e)
        _update_progress(phase="error", current_step=str(e), status="error")
        yield {"type": "error", "error": str(e)}


def _maskrcnn_streaming_events(
    raster_path: str,
    model_name: str,
    threshold: float,
    stream_tile_interval: int,
    source_filename: Optional[str] = None,
    lulc_prediction_id: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Yields SSE payload dicts: start, progress (cumulative geojson), done — same final fields as /predict."""
    stream_tile_interval = max(1, min(int(stream_tile_interval), 200))
    if _is_solar_panel_model(model_name):
        yield from _solar_panel_streaming_events(
            raster_path=raster_path,
            model_name=model_name,
            threshold=threshold,
            stream_tile_interval=stream_tile_interval,
            source_filename=source_filename,
            lulc_prediction_id=lulc_prediction_id,
        )
        return
    if is_esri_model_name(model_name):
        yield from _esri_streaming_events(
            raster_path=raster_path,
            model_name=model_name,
            threshold=threshold,
            stream_tile_interval=stream_tile_interval,
            source_filename=source_filename,
            lulc_prediction_id=lulc_prediction_id,
        )
        return
    _reset_progress()
    _update_progress(phase="loading_model", current_step="Loading model...", status="running")
    try:
        with rasterio.open(raster_path) as src:
            width = src.width
            height = src.height
            crs = src.crs
            transform = src.transform
            bounds_native = src.bounds
            band_count = src.count
            if band_count not in (3, 4):
                yield {"type": "error", "error": f"Unsupported band count: {band_count}. Expect 3 or 4."}
                return

            crs_display = crs.to_string() if crs is not None else None
            if crs_display is None and bounds_look_like_wgs84_degrees(
                bounds_native.left, bounds_native.bottom, bounds_native.right, bounds_native.top
            ):
                crs_display = "EPSG:4326 (map grid)"
            extent_wgs84 = _maskrcnn_raster_extent_bounds_wgs84(crs, bounds_native)
            tile_specs = list(iter_tile_windows(width, height, TILE_SIZE, TILE_OVERLAP))
            total_tiles = len(tile_specs)
            logger.info(
                "[predict-stream] Detecting: %s tiles (Mask R-CNN); incremental map update every %s tiles",
                total_tiles,
                stream_tile_interval,
            )
            yield {
                "type": "start",
                "crs": crs_display,
                "overlay_bounds": extent_wgs84,
                "width": width,
                "height": height,
                "total_tiles": total_tiles,
                "stream_interval": stream_tile_interval,
                "message": f"Detecting: {total_tiles} tiles — map preview every {stream_tile_interval}",
            }

            model = load_model(model_name, band_count)
            scored_instances: List[Tuple[Polygon, float, int]] = []
            tiles_processed = 0
            _start_time = time.time()
            last_yielded_tile = 0
            _update_progress(
                phase="inference",
                current_step="Starting tile inference...",
                total_chips=total_tiles,
                processed_chips=0,
                status="running",
            )

            batch_tensors: List[torch.Tensor] = []
            batch_meta: List[Tuple[int, int, int, int, Affine]] = []

            def process_batch_outputs(outputs, metas):
                nonlocal scored_instances
                for out, meta in zip(outputs, metas):
                    scored_instances.extend(
                        _extract_scored_instances_from_output(out, meta, MASKRCNN_SCORE_FLOOR)
                    )

            def iter_progress_events(is_final_flush: bool):
                nonlocal last_yielded_tile
                n = stream_tile_interval
                while last_yielded_tile + n <= tiles_processed:
                    last_yielded_tile += n
                    preview_polys = [
                        p for p, sc, _lb in scored_instances if sc >= threshold
                    ]
                    gj = _maskrcnn_polygons_to_preview_geojson(preview_polys, crs, bounds_native)
                    nfeat = len(gj.get("features", []) or [])
                    msg = (
                        f"Tiles {last_yielded_tile}/{total_tiles}: merged preview → map "
                        f"({nfeat} features)"
                    )
                    logger.info("[predict-stream] %s", msg)
                    yield {
                        "type": "progress",
                        "geojson": gj,
                        "tiles_processed": last_yielded_tile,
                        "total_tiles": total_tiles,
                        "message": msg,
                    }
                if is_final_flush and tiles_processed > last_yielded_tile:
                    last_yielded_tile = tiles_processed
                    preview_polys = [
                        p for p, sc, _lb in scored_instances if sc >= threshold
                    ]
                    gj = _maskrcnn_polygons_to_preview_geojson(preview_polys, crs, bounds_native)
                    nfeat = len(gj.get("features", []) or [])
                    msg = (
                        f"Tiles {tiles_processed}/{total_tiles}: final preview chunk → map "
                        f"({nfeat} features)"
                    )
                    logger.info("[predict-stream] %s", msg)
                    yield {
                        "type": "progress",
                        "geojson": gj,
                        "tiles_processed": tiles_processed,
                        "total_tiles": total_tiles,
                        "message": msg,
                    }

            for spec in tile_specs:
                xoff, yoff, w, h = spec
                window = Window(col_off=xoff, row_off=yoff, width=w, height=h)
                arr = src.read(window=window)
                if arr.dtype != np.uint8:
                    amin = arr.min()
                    amax = arr.max()
                    if amax == amin:
                        logger.warning("Window has zero dynamic range; skipping window %s", spec)
                        tiles_processed += 1
                        _update_progress(
                            processed_chips=tiles_processed,
                            current_step=f"Tile {tiles_processed}/{total_tiles} (skipped)",
                        )
                        for ev in iter_progress_events(is_final_flush=False):
                            yield ev
                        continue
                    arr = ((arr - amin) / (amax - amin) * 255).astype(np.uint8)

                tile_t = tile_to_tensor(arr)
                tile_transform = rasterio.windows.transform(window, transform)
                batch_tensors.append(tile_t)
                batch_meta.append((xoff, yoff, w, h, tile_transform))

                if len(batch_tensors) >= BATCH_TILES:
                    with torch.no_grad():
                        outputs = model(batch_tensors)
                    process_batch_outputs(outputs, batch_meta)
                    tiles_processed += len(batch_meta)
                    elapsed = time.time() - _start_time
                    rate = tiles_processed / elapsed if elapsed > 0 else 0
                    remaining = total_tiles - tiles_processed
                    eta = remaining / rate if rate > 0 else None
                    _update_progress(
                        processed_chips=tiles_processed,
                        current_step=f"Tile {tiles_processed}/{total_tiles}",
                        eta_seconds=round(eta, 1) if eta else None,
                    )
                    for ev in iter_progress_events(is_final_flush=False):
                        yield ev
                    batch_tensors = []
                    batch_meta = []

            if batch_tensors:
                with torch.no_grad():
                    outputs = model(batch_tensors)
                process_batch_outputs(outputs, batch_meta)
                tiles_processed += len(batch_meta)
                _update_progress(
                    processed_chips=tiles_processed,
                    current_step=f"Tile {tiles_processed}/{total_tiles}",
                    eta_seconds=0,
                )
                for ev in iter_progress_events(is_final_flush=False):
                    yield ev

            for ev in iter_progress_events(is_final_flush=True):
                yield ev

            _update_progress(
                phase="post_processing",
                current_step="Merging polygons...",
                processed_chips=total_tiles,
                status="running",
            )

            done_payload = _package_detection_results(
                scored_instances,
                crs=crs,
                bounds_native=bounds_native,
                transform=transform,
                width=width,
                height=height,
                threshold=threshold,
                task="maskrcnn",
                model_name=model_name,
                source_filename=source_filename or "",
                total_tiles=total_tiles,
                lulc_prediction_id=lulc_prediction_id,
            )

            _update_progress(
                phase="done",
                current_step="Complete",
                processed_chips=total_tiles,
                eta_seconds=0,
                status="done",
            )

            yield {"type": "done", **done_payload}
    except Exception as e:
        logger.exception("Streaming prediction failed: %s", e)
        _update_progress(phase="error", current_step=str(e), status="error")
        yield {"type": "error", "error": str(e)}


def _package_detection_results(
    scored_instances: List[Tuple[Polygon, float, int]],
    *,
    crs,
    bounds_native,
    transform,
    width: int,
    height: int,
    threshold: float,
    task: str,
    model_name: str,
    source_filename: str,
    total_tiles: int,
    lulc_prediction_id: Optional[str],
    model_family: Optional[str] = None,
) -> Dict[str, Any]:
    """GeoJSON/overlay/archive/LULC hook — shared by Mask R-CNN and solar panel paths."""
    score_floor_recorded = SOLAR_PANEL_SCORE_FLOOR if task == "solar_panel" else MASKRCNN_SCORE_FLOOR
    attach_lulc = task == "maskrcnn"

    if task == "solar_panel":
        filtered_scored = [
            (p, sc, lb)
            for p, sc, lb in scored_instances
            if p.is_valid and not p.is_empty
        ]
        valid_polys = [t[0] for t in filtered_scored]
        merged_list = regularize_detection_polygons(valid_polys)
    else:
        filtered_scored = [
            (p, sc, lb)
            for p, sc, lb in scored_instances
            if sc >= threshold and p.is_valid and not p.is_empty
        ]
        valid_polys = [t[0] for t in filtered_scored]
        merged_list = finalize_instance_detection_polygons(valid_polys)

    crs_gdf = crs
    if crs_gdf is None and bounds_look_like_wgs84_degrees(
        bounds_native.left, bounds_native.bottom, bounds_native.right, bounds_native.top
    ):
        crs_gdf = "EPSG:4326"
    gdf_native = gpd.GeoDataFrame(geometry=merged_list, crs=crs_gdf)

    gdf_4326 = gdf_native.copy()
    try:
        if gdf_4326.crs is not None and gdf_4326.crs.to_string() != "EPSG:4326":
            gdf_4326 = gdf_4326.to_crs("EPSG:4326")
    except Exception as e:
        logger.error("Failed to reproject to EPSG:4326: %s", e)

    if not gdf_4326.empty:
        gdf_4326["area"] = gdf_4326.geometry.area
        gdf_4326["length"] = gdf_4326.geometry.length
        gdf_4326["coords"] = gdf_4326.geometry.apply(
            lambda g: list(g.exterior.coords) if isinstance(g, Polygon) else []
        )

    total_area = float(gdf_4326["area"].sum()) if not gdf_4326.empty else 0.0
    count = len(gdf_4326)

    uid = uuid.uuid4().hex
    geojson_path, zip_path = save_geojson_and_shapefile(gdf_4326, f"detections_{uid}")
    run_id = uid
    run_id_to_files[run_id] = {
        "geojson": geojson_path,
        "shapefile": zip_path,
    }

    gdf_full_4326 = None
    if scored_instances:
        geoms_f = [t[0] for t in scored_instances]
        conf_f = [t[1] for t in scored_instances]
        lab_f = [t[2] for t in scored_instances]
        gdf_full_native = gpd.GeoDataFrame(
            {"confidence": conf_f, "label": lab_f, "geometry": geoms_f},
            crs=crs_gdf,
        )
        gdf_full_4326 = gdf_full_native.copy()
        try:
            if gdf_full_4326.crs is not None and gdf_full_4326.crs.to_string() != "EPSG:4326":
                gdf_full_4326 = gdf_full_4326.to_crs("EPSG:4326")
        except Exception as e:
            logger.error("full geojson reproject: %s", e)
            gdf_full_4326 = None

    full_geojson_path = None
    if gdf_full_4326 is not None and not gdf_full_4326.empty:
        full_geojson_path = os.path.join(OUTPUT_DIR, f"detections_{uid}_full.geojson")
        try:
            gdf_full_4326.to_file(full_geojson_path, driver="GeoJSON")
        except Exception:
            logger.exception("failed to write full scored GeoJSON")
            full_geojson_path = None
    if full_geojson_path and os.path.isfile(full_geojson_path):
        run_id_to_files[run_id]["full_geojson"] = full_geojson_path

    overlay_name = f"overlay_{uid}.png"
    overlay_path = os.path.join(OUTPUT_DIR, overlay_name)
    overlay_bounds_wgs84 = None
    try:
        if not gdf_native.empty:
            scale = 4
            out_w = max(1, width // scale)
            out_h = max(1, height // scale)
            transform_small = Affine(
                transform.a * scale,
                transform.b,
                transform.c,
                transform.d,
                transform.e * scale,
                transform.f,
            )
            shapes_iter = ((geom, 255) for geom in gdf_native.geometry)
            raster_mask = rasterio.features.rasterize(
                shapes=shapes_iter,
                out_shape=(out_h, out_w),
                transform=transform_small,
                fill=0,
                dtype="uint8",
            )
            from PIL import Image as PILImage

            im = PILImage.fromarray(raster_mask).convert("L")
            im.save(overlay_path)

            left, bottom, right, top = (
                bounds_native.left,
                bounds_native.bottom,
                bounds_native.right,
                bounds_native.top,
            )
            try:
                if crs is None and bounds_look_like_wgs84_degrees(left, bottom, right, top):
                    overlay_bounds_wgs84 = [[bottom, left], [top, right]]
                elif crs is not None:
                    minx, miny, maxx, maxy = transform_bounds(
                        crs, "EPSG:4326", left, bottom, right, top, densify_pts=21
                    )
                    overlay_bounds_wgs84 = [[miny, minx], [maxy, maxx]]
                else:
                    overlay_bounds_wgs84 = None
            except Exception as e:
                logger.error("Failed to compute overlay bounds in WGS84: %s", e)
                overlay_bounds_wgs84 = None
        else:
            open(overlay_path, "wb").close()
    except Exception:
        logger.exception("Failed to create overlay")

    if task == "solar_panel":
        write_solar_panel_manifest(
            run_id,
            model_name=model_name,
            source_filename=source_filename,
            inference_threshold=threshold,
            score_floor=score_floor_recorded,
            geojson_path=geojson_path,
            full_geojson_path=full_geojson_path,
            shapefile_path=zip_path,
            overlay_path=overlay_path if os.path.isfile(overlay_path) else None,
        )
    else:
        write_maskrcnn_manifest(
            run_id,
            model_name=model_name,
            source_filename=source_filename,
            inference_threshold=threshold,
            score_floor=score_floor_recorded,
            geojson_path=geojson_path,
            full_geojson_path=full_geojson_path,
            shapefile_path=zip_path,
            overlay_path=overlay_path if os.path.isfile(overlay_path) else None,
        )

    lulc_linked = False
    lp = (lulc_prediction_id or "").strip()
    if attach_lulc and lp:
        try:
            lulc_linked = bool(
                attach_building_detection_to_lulc(
                    lp,
                    task="maskrcnn",
                    od_run_id=run_id,
                    inference_threshold=float(threshold),
                    geojson_abs_path=geojson_path,
                    full_geojson_abs_path=full_geojson_path
                    if full_geojson_path and os.path.isfile(full_geojson_path)
                    else None,
                    confidence_npz_abs_path=None,
                    model_name=model_name,
                )
            )
        except Exception:
            logger.exception("Mask R-CNN LULC attach failed")

    crs_display = crs.to_string() if crs is not None else None
    if crs_display is None and bounds_look_like_wgs84_degrees(
        bounds_native.left, bounds_native.bottom, bounds_native.right, bounds_native.top
    ):
        crs_display = "EPSG:4326 (map grid)"

    out: Dict[str, Any] = {
        "task": task,
        "run_id": run_id,
        "count": int(count),
        "total_area": sanitize_float(total_area),
        "average_area": sanitize_float((total_area / count) if count > 0 else 0.0),
        "geojson_url": f"/outputs/{os.path.basename(geojson_path)}" if os.path.exists(geojson_path) else None,
        "full_geojson_url": f"/outputs/{os.path.basename(full_geojson_path)}"
        if full_geojson_path and os.path.isfile(full_geojson_path)
        else None,
        "shapefile_url": f"/outputs/{os.path.basename(zip_path)}" if os.path.exists(zip_path) else None,
        "overlay_url": f"/outputs/{os.path.basename(overlay_path)}" if os.path.exists(overlay_path) else None,
        "inference_threshold": threshold,
        "overlay_bounds": overlay_bounds_wgs84,
        "width": width,
        "height": height,
        "crs": crs_display,
        "lulc_prediction_linked": lulc_linked,
    }
    if task == "solar_panel":
        out["solar_panel_score_floor"] = SOLAR_PANEL_SCORE_FLOOR
    else:
        out["maskrcnn_score_floor"] = MASKRCNN_SCORE_FLOOR
    if model_family:
        out["model_family"] = model_family
    return out


# -------------------- API --------------------


@app.get('/models')
def list_models() -> Dict[str, Any]:
    try:
        seen: dict[str, None] = {}
        for d in (MODEL_DIR, LEGACY_MODEL_DIR, SOLAR_PANEL_DIR):
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.endswith(('.pth', '.pt')) and f not in seen:
                    seen[f] = None
        # Filter OUT super resolution models
        models: List[str] = []
        for file in sorted(seen.keys()):
            lower_file = file.lower()
            if not any(key in lower_file for key in ['super', 'resolution', 'srgan', 'upscale', 'generator']):
                models.append(file)
        esri_ids: List[str] = []
        try:
            esri_ids = list_esri_model_ids()
        except Exception:
            logger.exception("list_esri_model_ids failed")
        for mid in sorted(esri_ids):
            if mid not in models:
                models.append(mid)
        models.sort()

        models_detailed: List[Dict[str, Any]] = []
        for file in sorted(seen.keys()):
            lower_file = file.lower()
            if any(key in lower_file for key in ['super', 'resolution', 'srgan', 'upscale', 'generator']):
                continue
            models_detailed.append(
                {
                    "name": file,
                    "kind": "maskrcnn",
                    "model_family": "maskrcnn",
                    "display_color_hint": "maskrcnn",
                }
            )
        for mid in sorted(esri_ids):
            models_detailed.append(
                {
                    "name": mid,
                    "kind": "esri_dlpk",
                    "model_family": "esri",
                    "display_color_hint": "esri",
                }
            )
        models_detailed.sort(key=lambda x: str(x.get("name") or ""))

        return {"models": models, "models_detailed": models_detailed}
    except Exception as e:
        logger.exception("list models failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/predict')
def predict(
    image: UploadFile = File(...),
    model_name: str = Query(...),
    threshold: float = Query(0.5, ge=0.0, le=1.0),
    roi_geojson: Optional[str] = Form(None),
    roi_full_bounds_swne: Optional[str] = Form(None),
    lulc_prediction_id: Optional[str] = Form(None),
):
    tmp_name = uuid.uuid4().hex + os.path.splitext(image.filename)[1]
    upload_path = os.path.join(tempfile.gettempdir(), tmp_name)
    paths_to_delete: List[str] = []

    # basic size guard
    try:
        uploaded_bytes = image.file.read()
        if len(uploaded_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Uploaded file too large")
        with open(upload_path, 'wb') as f:
            f.write(uploaded_bytes)
        paths_to_delete.append(upload_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed saving upload: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    raster_path = upload_path
    roi_raw = (roi_geojson or "").strip()
    bounds_swne = parse_roi_full_bounds_swne((roi_full_bounds_swne or "").strip())
    if roi_raw:
        ext = os.path.splitext(upload_path)[1].lower()
        if ext not in (".tif", ".tiff"):
            for p in paths_to_delete:
                try:
                    if p and os.path.isfile(p):
                        os.unlink(p)
                except OSError:
                    pass
            raise HTTPException(status_code=400, detail="ROI polygon is only supported for GeoTIFF uploads.")
        try:
            geom = geometry_polygon_from_roi_geojson(roi_raw)
            crop_path = maskrcnn_roi_geotiff_with_fallbacks(upload_path, geom, bounds_swne)
        except json.JSONDecodeError:
            for p in paths_to_delete:
                try:
                    if p and os.path.isfile(p):
                        os.unlink(p)
                except OSError:
                    pass
            raise HTTPException(status_code=400, detail="Invalid roi_geojson (not valid JSON)")
        except ValueError as e:
            for p in paths_to_delete:
                try:
                    if p and os.path.isfile(p):
                        os.unlink(p)
                except OSError:
                    pass
            raise HTTPException(status_code=400, detail=str(e))
        paths_to_delete.append(crop_path)
        raster_path = crop_path

    try:
        with rasterio.open(raster_path) as src:
            width = src.width
            height = src.height
            crs = src.crs
            transform = src.transform
            bounds_native = src.bounds  # left, bottom, right, top

            # determine band count
            band_count = src.count
            esri_mode = is_esri_model_name(model_name)
            if esri_mode:
                md = resolve_esri_model_dir(model_name)
                emd = load_emd(md)
                ov = load_inference_overrides(md)
                cfg_pre = parse_export_config(emd, ov)
                need_b = max(cfg_pre.extract_bands) + 1
                if band_count < need_b:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Raster has {band_count} bands; Esri model needs at least {need_b} "
                            f"for ExtractBands {cfg_pre.extract_bands}."
                        ),
                    )
            elif band_count not in (3, 4):
                raise HTTPException(status_code=400, detail=f"Unsupported band count: {band_count}. Expect 3 or 4.")

            _reset_progress()
            _update_progress(phase="loading_model", current_step="Loading model...", status="running")

            scored_instances: List[Tuple[Polygon, float, int]] = []

            if _is_solar_panel_model(model_name):
                solar_w = _resolve_solar_panel_weights(model_name)
                model_solar = load_solar_model(solar_w, DEVICE)
                tile_specs_solar = list(iter_tile_windows(width, height, SOLAR_TILE_SIZE, SOLAR_TILE_OVERLAP))
                total_tiles = len(tile_specs_solar)
                tiles_processed = 0
                _start_time = time.time()
                _update_progress(
                    phase="inference",
                    current_step="Starting tile inference...",
                    total_chips=total_tiles,
                    processed_chips=0,
                    status="running",
                )
                for spec in tile_specs_solar:
                    xoff, yoff, w, h = spec
                    window = Window(col_off=xoff, row_off=yoff, width=w, height=h)
                    arr = src.read(window=window)
                    try:
                        rgb = prepare_rgb_uint8_for_solar(arr)
                    except ValueError as e:
                        logger.warning("Solar tile skip %s: %s", spec, e)
                        tiles_processed += 1
                        _update_progress(
                            processed_chips=tiles_processed,
                            current_step=f"Tile {tiles_processed}/{total_tiles} (skipped)",
                        )
                        continue
                    tile_transform = rasterio.windows.transform(window, transform)
                    scored_instances.extend(
                        extract_solar_instances_from_tile(
                            rgb,
                            model_solar,
                            DEVICE,
                            0.0,
                            tile_transform,
                            binary_threshold=threshold,
                        )
                    )
                    tiles_processed += 1
                    elapsed = time.time() - _start_time
                    rate = tiles_processed / elapsed if elapsed > 0 else 0
                    remaining = total_tiles - tiles_processed
                    eta = remaining / rate if rate > 0 else None
                    _update_progress(
                        processed_chips=tiles_processed,
                        current_step=f"Tile {tiles_processed}/{total_tiles}",
                        eta_seconds=round(eta, 1) if eta else None,
                    )

                _update_progress(
                    phase="post_processing",
                    current_step="Merging polygons...",
                    processed_chips=total_tiles,
                    status="running",
                )
                logger.info(
                    "Collected %d solar scored instances before post-processing",
                    len(scored_instances),
                )
                out_payload = _package_detection_results(
                    scored_instances,
                    crs=crs,
                    bounds_native=bounds_native,
                    transform=transform,
                    width=width,
                    height=height,
                    threshold=threshold,
                    task="solar_panel",
                    model_name=model_name,
                    source_filename=getattr(image, "filename", None) or "",
                    total_tiles=total_tiles,
                    lulc_prediction_id=lulc_prediction_id,
                )
                _update_progress(
                    phase="done",
                    current_step="Complete",
                    processed_chips=total_tiles,
                    eta_seconds=0,
                    status="done",
                )
                return JSONResponse(content=out_payload)

            if esri_mode:
                model_dir = resolve_esri_model_dir(model_name)
                overrides = load_inference_overrides(model_dir)
                tile_sz = int(overrides.get("tile_size", TILE_SIZE))
                tile_ov = int(overrides.get("tile_overlap", TILE_OVERLAP))
                model_esri, cfg = load_esri_maskrcnn(model_dir, DEVICE)
                tile_specs = list(iter_tile_windows(width, height, tile_sz, tile_ov))
                total_tiles = len(tile_specs)
                tiles_processed = 0
                _start_time = time.time()
                _update_progress(
                    phase="inference",
                    current_step="Starting tile inference...",
                    total_chips=total_tiles,
                    processed_chips=0,
                    status="running",
                )
                batch_tensors: List[torch.Tensor] = []
                batch_meta: List[Tuple[int, int, int, int, Affine]] = []

                def _flush_esri(outputs, metas):
                    for out, meta in zip(outputs, metas):
                        _x, _y, w, h, _tr = meta
                        out_native = upsample_detection_output_to_native_hw(out, int(h), int(w))
                        scored_instances.extend(
                            _extract_scored_instances_from_output(out_native, meta, MASKRCNN_SCORE_FLOOR)
                        )

                for spec in tile_specs:
                    xoff, yoff, w, h = spec
                    window = Window(col_off=xoff, row_off=yoff, width=w, height=h)
                    arr = src.read(window=window)
                    tile_transform = rasterio.windows.transform(window, transform)
                    try:
                        tile_t = raster_window_to_esri_input(arr, cfg, DEVICE)
                    except (ValueError, KeyError) as e:
                        logger.warning("Esri tile skip %s: %s", spec, e)
                        tiles_processed += 1
                        _update_progress(
                            processed_chips=tiles_processed,
                            current_step=f"Tile {tiles_processed}/{total_tiles} (skipped)",
                        )
                        continue

                    batch_tensors.append(tile_t)
                    batch_meta.append((xoff, yoff, w, h, tile_transform))

                    if len(batch_tensors) >= BATCH_TILES:
                        with torch.no_grad():
                            outputs = model_esri(batch_tensors)
                        _flush_esri(outputs, batch_meta)
                        tiles_processed += len(batch_meta)
                        elapsed = time.time() - _start_time
                        rate = tiles_processed / elapsed if elapsed > 0 else 0
                        remaining = total_tiles - tiles_processed
                        eta = remaining / rate if rate > 0 else None
                        _update_progress(
                            processed_chips=tiles_processed,
                            current_step=f"Tile {tiles_processed}/{total_tiles}",
                            eta_seconds=round(eta, 1) if eta else None,
                        )
                        batch_tensors = []
                        batch_meta = []

                if batch_tensors:
                    with torch.no_grad():
                        outputs = model_esri(batch_tensors)
                    _flush_esri(outputs, batch_meta)
                    tiles_processed += len(batch_meta)
                    _update_progress(
                        processed_chips=tiles_processed,
                        current_step=f"Tile {tiles_processed}/{total_tiles}",
                        eta_seconds=0,
                    )

                _update_progress(
                    phase="post_processing",
                    current_step="Merging polygons...",
                    processed_chips=total_tiles,
                    status="running",
                )
                logger.info("Esri: collected %d scored instances before post-processing", len(scored_instances))
                out_payload = _package_detection_results(
                    scored_instances,
                    crs=crs,
                    bounds_native=bounds_native,
                    transform=transform,
                    width=width,
                    height=height,
                    threshold=threshold,
                    task="maskrcnn",
                    model_name=model_name,
                    source_filename=getattr(image, "filename", None) or "",
                    total_tiles=total_tiles,
                    lulc_prediction_id=lulc_prediction_id,
                    model_family="esri",
                )
                _update_progress(
                    phase="done",
                    current_step="Complete",
                    processed_chips=total_tiles,
                    eta_seconds=0,
                    status="done",
                )
                return JSONResponse(content=out_payload)

            model = load_model(model_name, band_count)

            # we'll process windows in batches for model throughput
            tile_specs = list(iter_tile_windows(width, height, TILE_SIZE, TILE_OVERLAP))

            total_tiles = len(tile_specs)
            tiles_processed = 0
            _start_time = time.time()
            _update_progress(
                phase="inference", current_step="Starting tile inference...",
                total_chips=total_tiles, processed_chips=0, status="running",
            )

            # create list of tile tensors grouped by BATCH_TILES
            batch_tensors: List[torch.Tensor] = []
            batch_meta: List[Tuple[int, int, int, int, Affine]] = []  # xoff,yoff,w,h, tile_transform

            def _flush_batch_outputs(outputs, metas):
                for out, meta in zip(outputs, metas):
                    scored_instances.extend(
                        _extract_scored_instances_from_output(out, meta, MASKRCNN_SCORE_FLOOR)
                    )

            for spec in tile_specs:
                xoff, yoff, w, h = spec
                window = Window(col_off=xoff, row_off=yoff, width=w, height=h)
                # read window directly as uint8
                arr = src.read(window=window)  # shape (bands, h, w)
                # normalize to uint8 if needed
                if arr.dtype != np.uint8:
                    amin = arr.min()
                    amax = arr.max()
                    if amax == amin:
                        logger.warning("Window has zero dynamic range; skipping window %s", spec)
                        tiles_processed += 1
                        _update_progress(
                            processed_chips=tiles_processed,
                            current_step=f"Tile {tiles_processed}/{total_tiles} (skipped)",
                        )
                        continue
                    arr = ((arr - amin) / (amax - amin) * 255).astype(np.uint8)

                tile_t = tile_to_tensor(arr)
                tile_transform = rasterio.windows.transform(window, transform)

                batch_tensors.append(tile_t)
                batch_meta.append((xoff, yoff, w, h, tile_transform))

                # run a batch when we reach batch size or at the end
                if len(batch_tensors) >= BATCH_TILES:
                    # model expects list[Tensor]
                    with torch.no_grad():
                        outputs = model(batch_tensors)

                    _flush_batch_outputs(outputs, batch_meta)

                    tiles_processed += len(batch_meta)
                    elapsed = time.time() - _start_time
                    rate = tiles_processed / elapsed if elapsed > 0 else 0
                    remaining = total_tiles - tiles_processed
                    eta = remaining / rate if rate > 0 else None
                    _update_progress(
                        processed_chips=tiles_processed,
                        current_step=f"Tile {tiles_processed}/{total_tiles}",
                        eta_seconds=round(eta, 1) if eta else None,
                    )

                    batch_tensors = []
                    batch_meta = []

            # flush remaining batch
            if batch_tensors:
                with torch.no_grad():
                    outputs = model(batch_tensors)
                _flush_batch_outputs(outputs, batch_meta)

                tiles_processed += len(batch_meta)
                _update_progress(
                    processed_chips=tiles_processed,
                    current_step=f"Tile {tiles_processed}/{total_tiles}",
                    eta_seconds=0,
                )

            _update_progress(
                phase="post_processing", current_step="Merging polygons...",
                processed_chips=total_tiles, status="running",
            )

            logger.info("Collected %d scored instances before post-processing", len(scored_instances))
            out_payload = _package_detection_results(
                scored_instances,
                crs=crs,
                bounds_native=bounds_native,
                transform=transform,
                width=width,
                height=height,
                threshold=threshold,
                task="maskrcnn",
                model_name=model_name,
                source_filename=getattr(image, "filename", None) or "",
                total_tiles=total_tiles,
                lulc_prediction_id=lulc_prediction_id,
            )

            _update_progress(
                phase="done", current_step="Complete",
                processed_chips=total_tiles, eta_seconds=0, status="done",
            )

            return JSONResponse(content=out_payload)

    except HTTPException:
        _update_progress(phase="error", current_step="Failed", status="error")
        raise
    except Exception as e:
        logger.exception("Prediction failed: %s", e)
        _update_progress(phase="error", current_step=str(e), status="error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for p in paths_to_delete:
            try:
                if p and os.path.isfile(p):
                    os.unlink(p)
            except OSError:
                pass


def _cleanup_paths(paths: List[str]) -> None:
    for p in paths:
        try:
            if p and os.path.isfile(p):
                os.unlink(p)
        except OSError:
            pass


@app.post("/predict-stream")
async def predict_stream(
    image: UploadFile = File(...),
    model_name: str = Query(...),
    threshold: float = Query(0.5, ge=0.0, le=1.0),
    stream_tile_interval: int = Query(5, ge=1, le=200),
    roi_geojson: Optional[str] = Form(None),
    roi_full_bounds_swne: Optional[str] = Form(None),
    lulc_prediction_id: Optional[str] = Form(None),
):
    tmp_name = uuid.uuid4().hex + os.path.splitext(image.filename)[1]
    upload_path = os.path.join(tempfile.gettempdir(), tmp_name)
    paths_to_delete: List[str] = []

    try:
        uploaded_bytes = await image.read()
        if len(uploaded_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Uploaded file too large")
        with open(upload_path, "wb") as f:
            f.write(uploaded_bytes)
        paths_to_delete.append(upload_path)
    except HTTPException:
        _cleanup_paths(paths_to_delete)
        raise
    except Exception as e:
        logger.exception("Failed saving upload: %s", e)
        _cleanup_paths(paths_to_delete)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    raster_path = upload_path
    roi_raw = (roi_geojson or "").strip()
    bounds_swne = parse_roi_full_bounds_swne((roi_full_bounds_swne or "").strip())
    if roi_raw:
        ext = os.path.splitext(upload_path)[1].lower()
        if ext not in (".tif", ".tiff"):
            _cleanup_paths(paths_to_delete)
            raise HTTPException(status_code=400, detail="ROI polygon is only supported for GeoTIFF uploads.")
        try:
            geom = geometry_polygon_from_roi_geojson(roi_raw)
            crop_path = maskrcnn_roi_geotiff_with_fallbacks(upload_path, geom, bounds_swne)
        except json.JSONDecodeError:
            _cleanup_paths(paths_to_delete)
            raise HTTPException(status_code=400, detail="Invalid roi_geojson (not valid JSON)")
        except ValueError as e:
            _cleanup_paths(paths_to_delete)
            raise HTTPException(status_code=400, detail=str(e))
        paths_to_delete.append(crop_path)
        raster_path = crop_path

    upload_fname = getattr(image, "filename", None) or ""
    lulc_pid = (lulc_prediction_id or "").strip() or None

    def sse_body():
        try:
            for ev in _maskrcnn_streaming_events(
                raster_path,
                model_name,
                threshold,
                stream_tile_interval,
                source_filename=upload_fname,
                lulc_prediction_id=lulc_pid,
            ):
                yield "data: " + sse_json_dumps(ev) + "\n\n"
        finally:
            _cleanup_paths(paths_to_delete)

    return StreamingResponse(
        sse_body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _artifact_path_to_outputs_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    p = str(path).replace("\\", "/")
    out = OUTPUT_DIR.replace("\\", "/")
    if "/outputs/" in p:
        return p[p.index("/outputs/") :]
    if p.startswith(out + "/"):
        return "/outputs/" + p[len(out) + 1 :]
    base = os.path.basename(path)
    if base:
        candidate = os.path.join(OUTPUT_DIR, base)
        if os.path.isfile(candidate):
            return f"/outputs/{base}"
    return None


@app.get("/runs")
def list_saved_runs(limit: int = Query(100, ge=1, le=500)):
    """Saved detection runs (Mask R-CNN + solar panel) from prediction_archive manifests."""
    manifests_mc = list_manifests(task="maskrcnn", limit=limit)
    manifests_sp = list_manifests(task="solar_panel", limit=limit)
    merged = manifests_mc + manifests_sp
    merged.sort(key=lambda m: str(m.get("created_at") or ""), reverse=True)
    merged = merged[: max(1, int(limit))]
    runs: List[Dict[str, Any]] = []
    for m in merged:
        run_id = m.get("run_id")
        if not run_id:
            continue
        art = m.get("artifacts") or {}
        tk = str(m.get("task") or "maskrcnn")
        runs.append(
            {
                "run_id": run_id,
                "task": tk,
                "created_at": m.get("created_at"),
                "model_name": m.get("model_name"),
                "source_filename": m.get("source_filename"),
                "inference_threshold": m.get("inference_threshold"),
                "score_floor": m.get("score_floor"),
                "geojson_url": _artifact_path_to_outputs_url(art.get("geojson")),
                "full_geojson_url": _artifact_path_to_outputs_url(art.get("full_geojson")),
                "overlay_url": _artifact_path_to_outputs_url(art.get("overlay")),
                "shapefile_url": _artifact_path_to_outputs_url(art.get("shapefile")),
            }
        )
    return {"runs": runs}


@app.get("/runs/{run_id}")
def get_saved_run(run_id: str):
    if not archive_validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    m = read_manifest(run_id)
    if not m or m.get("task") not in ("maskrcnn", "solar_panel"):
        raise HTTPException(status_code=404, detail="Run not found")
    art = m.get("artifacts") or {}
    return {
        "run_id": run_id,
        "task": m.get("task"),
        "created_at": m.get("created_at"),
        "model_name": m.get("model_name"),
        "source_filename": m.get("source_filename"),
        "inference_threshold": m.get("inference_threshold"),
        "score_floor": m.get("score_floor"),
        "geojson_url": _artifact_path_to_outputs_url(art.get("geojson")),
        "full_geojson_url": _artifact_path_to_outputs_url(art.get("full_geojson")),
        "overlay_url": _artifact_path_to_outputs_url(art.get("overlay")),
        "shapefile_url": _artifact_path_to_outputs_url(art.get("shapefile")),
    }


@app.post("/postprocess/preview")
async def postprocess_preview(body: PostprocessLabBody):
    """Re-run post-processing on full_geojson (no file writes). Gated by ENABLE_POSTPROCESS_LAB."""
    _postprocess_lab_or_403()
    if not archive_validate_run_id(body.run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    try:
        _merged, gdf, stats = _maskrcnn_lab_load_and_process(body)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("postprocess preview failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    geojson_out = (
        json.loads(gdf.to_json())
        if not gdf.empty
        else {"type": "FeatureCollection", "features": []}
    )
    return {"geojson": geojson_out, **stats}


@app.post("/postprocess/apply")
async def postprocess_apply(body: PostprocessLabBody):
    """Persist post-processed GeoJSON/shapefile for a Mask R-CNN or solar run."""
    _postprocess_lab_or_403()
    if not archive_validate_run_id(body.run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    try:
        _merged, gdf, stats = _maskrcnn_lab_load_and_process(body)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("postprocess apply failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    geo_path, zip_path = _maskrcnn_resolve_output_paths(body.run_id)
    if not geo_path:
        raise HTTPException(status_code=404, detail="GeoJSON output path not found")
    prefix = os.path.splitext(os.path.basename(geo_path))[0]
    gp, zp = save_geojson_and_shapefile(gdf, prefix)
    if body.run_id not in run_id_to_files:
        run_id_to_files[body.run_id] = {}
    run_id_to_files[body.run_id]["geojson"] = gp
    run_id_to_files[body.run_id]["shapefile"] = zp
    m = read_manifest(body.run_id)
    task = (body.task or "").strip().lower()
    if task not in ("maskrcnn", "solar_panel") and m:
        task = str(m.get("task") or "maskrcnn")
    if task == "solar_panel":
        write_solar_panel_manifest(
            body.run_id,
            model_name=(m or {}).get("model_name") or "",
            source_filename=(m or {}).get("source_filename") or "",
            inference_threshold=float((m or {}).get("inference_threshold") or 0.0),
            score_floor=float((m or {}).get("score_floor") or SOLAR_PANEL_SCORE_FLOOR),
            geojson_path=gp,
            full_geojson_path=_maskrcnn_resolve_full_geojson_path(body.run_id),
            shapefile_path=zp,
            overlay_path=((m or {}).get("artifacts") or {}).get("overlay"),
        )
    else:
        write_maskrcnn_manifest(
            body.run_id,
            model_name=(m or {}).get("model_name") or "",
            source_filename=(m or {}).get("source_filename") or "",
            inference_threshold=float((m or {}).get("inference_threshold") or 0.0),
            score_floor=float((m or {}).get("score_floor") or MASKRCNN_SCORE_FLOOR),
            geojson_path=gp,
            full_geojson_path=_maskrcnn_resolve_full_geojson_path(body.run_id),
            shapefile_path=zp,
            overlay_path=((m or {}).get("artifacts") or {}).get("overlay"),
        )
    geojson_out = (
        json.loads(gdf.to_json())
        if not gdf.empty
        else {"type": "FeatureCollection", "features": []}
    )
    return {
        "ok": True,
        "geojson": geojson_out,
        "geojson_url": _artifact_path_to_outputs_url(gp),
        "shapefile_url": _artifact_path_to_outputs_url(zp),
        **stats,
    }


# @app.get("/download/geojson/{filename}")
# async def download_geojson(filename: str):
#     file_path = os.path.join('outputs', filename)
#     if os.path.exists(file_path):
#         return FileResponse(path=file_path, media_type='application/geo+json', filename=filename)
#     else:
#         return JSONResponse(status_code=404, content={"message": "GeoJSON file not found."})

# @app.get("/download/shapefile/{filename}")
# async def download_shapefile(filename: str):
#     file_path = os.path.join('outputs', filename)
#     if os.path.exists(file_path):
#         return FileResponse(path=file_path, media_type='application/zip', filename=filename)
#     else:
#         return JSONResponse(status_code=404, content={"message": "Shapefile zip not found."})

@app.get("/download_geojson")
async def download_geojson(run_id: str = Query(...)):
    """Match api.js: GET /download_geojson?run_id={runId}"""
    if run_id not in run_id_to_files:
        raise HTTPException(status_code=404, detail="Run ID not found")
    
    geojson_path = run_id_to_files[run_id].get("geojson")
    if not geojson_path or not os.path.exists(geojson_path):
        raise HTTPException(status_code=404, detail="GeoJSON file not found")
    
    return FileResponse(
        path=geojson_path, 
        media_type='application/geo+json', 
        filename=f"detections_{run_id}.geojson"
    )

@app.get("/download_shapefile")
async def download_shapefile(run_id: str = Query(...)):
    """Match api.js: GET /download_shapefile?run_id={runId}"""
    if run_id not in run_id_to_files:
        raise HTTPException(status_code=404, detail="Run ID not found")
    
    shapefile_path = run_id_to_files[run_id].get("shapefile")
    if not shapefile_path or not os.path.exists(shapefile_path):
        raise HTTPException(status_code=404, detail="Shapefile not found")
    
    return FileResponse(
        path=shapefile_path, 
        media_type='application/zip', 
        filename=f"detections_{run_id}.zip"
    )


@app.get("/download_full_geojson")
async def download_full_geojson(run_id: str = Query(...)):
    """Scored instances (>= score floor) for analysis / display threshold in UI."""
    if not archive_validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    path = None
    if run_id in run_id_to_files:
        path = run_id_to_files[run_id].get("full_geojson")
    if not path or not os.path.isfile(path):
        path = os.path.join(OUTPUT_DIR, f"detections_{run_id}_full.geojson")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Full GeoJSON not found")
    return FileResponse(
        path=path,
        media_type="application/geo+json",
        filename=f"detections_{run_id}_full.geojson",
    )
if __name__ == '__main__':
    #uvicorn.run('maskrcnn_api_refactor:app', host='0.0.0.0', port=8001, log_level='info')
    uvicorn.run('finalmain:app', host='0.0.0.0', port=8001, log_level='info')
