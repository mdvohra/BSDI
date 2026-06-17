import os
import io
import sys
import uuid
import tempfile
import zipfile
import logging
import json
import base64
import shutil
import math
from typing import Dict, List, Optional, Any, Generator, Tuple
import numpy as np
import cv2
import torch
import torch.nn as nn
import torch.nn.functional as TF
from PIL import Image
import rasterio
from rasterio.transform import Affine
from shapely import affinity
from shapely.geometry import Polygon
import geopandas as gpd
from scipy import ndimage as ndi
from skimage.segmentation import watershed
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, Response, Form
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds
import mercantile
import math
from PIL import Image
import io
import PIL
import threading
import time
import asyncio
PIL.Image.MAX_IMAGE_PIXELS = None

from sse_json import sse_json_dumps
from prediction_archive import (
    list_manifests,
    read_manifest,
    validate_run_id as archive_validate_run_id,
    write_unet_manifest,
)
from lulc_detection_attach import attach_building_detection_to_lulc
from sar_flood import is_sar_flood_model, raster_to_pil_l_sar, preprocess_pil_chip_sar
from model_paths import (
    artifact_dir,
    legacy_backend_models_dir,
    legacy_eg_files_dir,
    sample_dir,
    sar_flood_repo_dir,
    ensure_dir,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.makedirs('uploads', exist_ok=True)
os.makedirs('outputs', exist_ok=True)
os.makedirs('exports', exist_ok=True)
os.makedirs("sessions", exist_ok=True)

ENABLE_POSTPROCESS_LAB = os.environ.get("ENABLE_POSTPROCESS_LAB", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _unet_straighten_mask_enabled() -> bool:
    return (os.environ.get("UNET_STRAIGHTEN_MASK") or "").strip().lower() in ("1", "true", "yes")


def _unet_straighten_close_size() -> int:
    """Morphological close kernel size (0 = skip). If positive and even, bumped to the next odd value."""
    try:
        v = int((os.environ.get("UNET_STRAIGHTEN_CLOSE") or "0").strip())
    except ValueError:
        return 0
    return max(0, v)


def _unet_straighten_min_area_px() -> float:
    try:
        return max(0.0, float((os.environ.get("UNET_STRAIGHTEN_MIN_AREA") or "50").strip()))
    except ValueError:
        return 50.0


def _unet_straighten_max_mar_area_px() -> float:
    """If > 0, contours with pixel area above this keep their original shape instead of MAR."""
    try:
        return max(0.0, float((os.environ.get("UNET_STRAIGHTEN_MAX_MAR_AREA") or "0").strip()))
    except ValueError:
        return 0.0


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from proj_runtime import clear_bad_proj_env

clear_bad_proj_env()

from roi_geotiff_clip import (
    geometry_polygon_from_roi_geojson,
    parse_roi_full_bounds_swne,
    unet_roi_geotiff_with_fallbacks,
)
from detection_postprocess import (
    dedupe_detection_polygons,
    merge_chip_seam_polygons,
    regularize_detection_polygons,
)

UNET_ARTIFACTS_DIR = artifact_dir("unet")
SAR_FLOOD_ARTIFACTS_DIR = artifact_dir("sar_flood")
LEGACY_MODEL_DIR = legacy_backend_models_dir()
for _d in (UNET_ARTIFACTS_DIR, SAR_FLOOD_ARTIFACTS_DIR, LEGACY_MODEL_DIR):
    ensure_dir(_d)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"Using device: {DEVICE}")

SAR_FLOOD_DIR = sar_flood_repo_dir()
DEMO_ORTHO_SEARCH_DIRS = (sample_dir("demo_ortho"), legacy_eg_files_dir())
_SR_KEYS = ("super", "resolution", "srgan", "upscale", "generator")


def _is_weight_filename(name: str) -> bool:
    return bool(name) and name.endswith((".pth", ".pt", ".pkl"))


def _sr_excluded(lower_name: str) -> bool:
    return any(k in lower_name for k in _SR_KEYS)


def _collect_unet_weights_flat(dirpath: str) -> list[str]:
    if not os.path.isdir(dirpath):
        return []
    out: list[str] = []
    for f in sorted(os.listdir(dirpath)):
        fp = os.path.join(dirpath, f)
        if os.path.isfile(fp) and _is_weight_filename(f) and not _sr_excluded(f.lower()):
            out.append(fp)
    return out


def discover_unet_model_basenames() -> list[str]:
    """List weights: models/artifacts/unet, sar_flood, legacy backend/models, then SAR_Flood tree."""
    order_paths: list[str] = []
    order_paths.extend(_collect_unet_weights_flat(UNET_ARTIFACTS_DIR))
    order_paths.extend(_collect_unet_weights_flat(SAR_FLOOD_ARTIFACTS_DIR))
    order_paths.extend(_collect_unet_weights_flat(LEGACY_MODEL_DIR))
    if os.path.isdir(SAR_FLOOD_DIR):
        for f in sorted(os.listdir(SAR_FLOOD_DIR)):
            fp = os.path.join(SAR_FLOOD_DIR, f)
            if os.path.isfile(fp) and _is_weight_filename(f) and not _sr_excluded(f.lower()):
                order_paths.append(fp)
            elif os.path.isdir(fp):
                try:
                    for f2 in sorted(os.listdir(fp)):
                        fp2 = os.path.join(fp, f2)
                        if os.path.isfile(fp2) and _is_weight_filename(f2) and not _sr_excluded(f2.lower()):
                            order_paths.append(fp2)
                except OSError as e:
                    logger.warning("Could not scan SAR_Flood subdir %s: %s", fp, e)
    seen: dict[str, None] = {}
    for p in order_paths:
        b = os.path.basename(p)
        if b not in seen:
            seen[b] = None
    return sorted(seen.keys())


def resolve_unet_model_path(model_name: str) -> str:
    """Prefer artifacts/unet, artifacts/sar_flood, legacy backend/models, then SAR_Flood tree."""
    base = os.path.basename(model_name.strip())
    if not _is_weight_filename(base):
        base = base + ".pth"
    candidates: list[str] = [
        os.path.join(UNET_ARTIFACTS_DIR, base),
        os.path.join(SAR_FLOOD_ARTIFACTS_DIR, base),
        os.path.join(LEGACY_MODEL_DIR, base),
    ]
    if os.path.isdir(SAR_FLOOD_DIR):
        candidates.append(os.path.join(SAR_FLOOD_DIR, base))
        try:
            for sub in os.listdir(SAR_FLOOD_DIR):
                subp = os.path.join(SAR_FLOOD_DIR, sub)
                if os.path.isdir(subp):
                    candidates.append(os.path.join(subp, base))
        except OSError as e:
            logger.warning("Could not scan SAR_Flood for %s: %s", base, e)
    for c in candidates:
        if os.path.isfile(c):
            return os.path.normpath(os.path.abspath(c))
    raise FileNotFoundError(
        f"Model not found: {base} (searched models/artifacts/unet, sar_flood, legacy backend/models, SAR_Flood/)"
    )

app = FastAPI(title="Building Detection API")


@app.on_event("startup")
async def _log_unet_model_discovery():
    try:
        names = discover_unet_model_basenames()
        logger.info(
            "UNet /models: %d file(s); unet_dir=%s; sar_artifacts=%s; legacy=%s; SAR_Flood=%s (exists=%s)",
            len(names),
            UNET_ARTIFACTS_DIR,
            SAR_FLOOD_ARTIFACTS_DIR,
            LEGACY_MODEL_DIR,
            SAR_FLOOD_DIR,
            os.path.isdir(SAR_FLOOD_DIR),
        )
        if names:
            logger.info("UNet model filenames: %s", names)
        else:
            logger.warning(
                "No weights found. Add .pth under models/artifacts/unet or sar_flood, "
                "or legacy backend/models/, or SAR_Flood/ (one subfolder level)."
            )
    except Exception as e:
        logger.warning("UNet model discovery at startup failed: %s", e)


origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Global progress tracking (same shape as maskrcnn for shared ProgressTracker UI)
progress_data = {
    "progress": 0,
    "phase": "idle",
    "current_step": "",
    "total_chips": 0,
    "processed_chips": 0,
    "eta_seconds": 0,
    "status": "idle",
}
progress_lock = threading.Lock()


def reset_unet_progress():
    with progress_lock:
        progress_data.update(
            {
                "progress": 0,
                "phase": "idle",
                "current_step": "",
                "total_chips": 0,
                "processed_chips": 0,
                "eta_seconds": 0,
                "status": "idle",
            }
        )


def update_progress(
    progress=None,
    phase=None,
    current_step=None,
    total_chips=None,
    processed_chips=None,
    eta_seconds=None,
    status=None,
):
    """Thread-safe progress update. Bar % = processed_chips/total_chips when total_chips > 0 (like maskrcnn)."""
    with progress_lock:
        if phase is not None:
            progress_data["phase"] = phase
        if current_step is not None:
            progress_data["current_step"] = current_step
        if total_chips is not None:
            progress_data["total_chips"] = total_chips
        if processed_chips is not None:
            progress_data["processed_chips"] = processed_chips
        if eta_seconds is not None:
            progress_data["eta_seconds"] = eta_seconds
        if status is not None:
            progress_data["status"] = status
        total = progress_data["total_chips"]
        done = progress_data["processed_chips"]
        if progress is not None:
            progress_data["progress"] = max(0, min(100, int(progress)))
        elif total > 0:
            progress_data["progress"] = min(100, int((done / total) * 100))
# Enhanced progress endpoint
@app.get("/progress")
async def get_progress():
    with progress_lock:
        return progress_data.copy()

# ------------------- UNet definition -------------------
class DoubleConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, 1, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, 1, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
    def forward(self, x):
        return self.conv(x)

class UNet(nn.Module):
    def __init__(self, in_channels=3, out_channels=1, features=[64,128,256,512]):
        super().__init__()
        self.ups, self.downs = nn.ModuleList(), nn.ModuleList()
        self.pool = nn.MaxPool2d(2,2)
        for feature in features:
            self.downs.append(DoubleConv(in_channels, feature))
            in_channels = feature
        for feature in reversed(features):
            self.ups.append(nn.ConvTranspose2d(feature*2, feature, 2, 2))
            self.ups.append(DoubleConv(feature*2, feature))
        self.bottleneck = DoubleConv(features[-1], features[-1]*2)
        self.final_conv = nn.Conv2d(features[0], out_channels, kernel_size=1)
    def forward(self, x):
        skips = []
        for down in self.downs:
            x = down(x); skips.append(x); x = self.pool(x)
        x = self.bottleneck(x)
        skips = skips[::-1]
        for idx in range(0, len(self.ups), 2):
            x = self.ups[idx](x)
            skip = skips[idx//2]
            if x.shape != skip.shape:
                x = TF.interpolate(x, size=skip.shape[2:])
            x = self.ups[idx+1](torch.cat((skip, x), dim=1))
        return torch.sigmoid(self.final_conv(x))

loaded_models = {}
# Per resolved weights path: whether to apply ImageNet normalize (opt-in; default legacy is 0–1 only).
_preprocess_uses_imagenet: Dict[str, bool] = {}
# Resolved .pth paths loaded as segmentation_models_pytorch.Unet (water); forward uses logits → sigmoid.
_water_smp_resolved_paths: set[str] = set()

# Trained in water-segmentation-pretrained-unet.ipynb: smp.Unet(resnet50), 4 ch, 224², BCEWithLogitsLoss
WATER_SMP_MODEL_BASENAMES = frozenset({"water_segmentation.pth"})
WATER_SMP_INFER_SIZE = 224
WATER_BODY_MODEL_BASENAMES = frozenset(
    {
        "water_body.pth",
        "best_resunet_finetuned.pth",
    }
)
WATER_BODY_INFER_SIZE = 512
WATER_BODY_DEFAULT_THRESHOLD = 0.4


def _water_body_chip_overlap_px() -> int:
    """Overlap between 512² tiles (seams). Env WATER_BODY_CHIP_OVERLAP default 64."""
    try:
        v = int((os.environ.get("WATER_BODY_CHIP_OVERLAP") or "64").strip())
    except ValueError:
        v = 64
    return max(32, min(v, 256))


def is_water_smp_model(model_name: str) -> bool:
    b = os.path.basename((model_name or "").strip())
    return b.lower() in {x.lower() for x in WATER_SMP_MODEL_BASENAMES}


def is_water_body_model(model_name: str) -> bool:
    b = os.path.basename((model_name or "").strip())
    allow = os.environ.get("WATER_BODY_MODEL_NAMES", "").strip()
    if allow:
        allowed = {x.strip().lower() for x in allow.split(",") if x.strip()}
        if b.lower() in allowed:
            return True
    return b.lower() in {x.lower() for x in WATER_BODY_MODEL_BASENAMES}


class ResidualConvBlock(nn.Module):
    """Notebook-aligned residual block for water_body.pth."""

    def __init__(self, in_channels, out_channels, stride=1):
        super().__init__()
        self.conv1 = nn.Conv2d(
            in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False
        )
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)

        self.skip_connection = nn.Sequential()
        if stride != 1 or in_channels != out_channels:
            self.skip_connection = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels),
            )

    def forward(self, x):
        identity = self.skip_connection(x)
        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)
        out = self.conv2(out)
        out = self.bn2(out)
        out += identity
        out = self.relu(out)
        return out


class ASPPModule(nn.Module):
    """Notebook-aligned ASPP module for water_body.pth."""

    def __init__(self, in_channels, out_channels=256):
        super().__init__()
        self.conv1x1 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.conv3x3_1 = nn.Sequential(
            nn.Conv2d(
                in_channels, out_channels, kernel_size=3, padding=6, dilation=6, bias=False
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.conv3x3_2 = nn.Sequential(
            nn.Conv2d(
                in_channels, out_channels, kernel_size=3, padding=12, dilation=12, bias=False
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.conv3x3_3 = nn.Sequential(
            nn.Conv2d(
                in_channels, out_channels, kernel_size=3, padding=18, dilation=18, bias=False
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.global_avg_pool = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.conv1x1_out = nn.Sequential(
            nn.Conv2d(out_channels * 5, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        _, _, h, w = x.size()
        branch1 = self.conv1x1(x)
        branch2 = self.conv3x3_1(x)
        branch3 = self.conv3x3_2(x)
        branch4 = self.conv3x3_3(x)
        branch5 = self.global_avg_pool(x)
        branch5 = TF.interpolate(branch5, size=(h, w), mode="bilinear", align_corners=True)
        out = torch.cat([branch1, branch2, branch3, branch4, branch5], dim=1)
        out = self.conv1x1_out(out)
        return out


class AttentionGate(nn.Module):
    """Notebook-aligned attention gate for water_body.pth."""

    def __init__(self, F_g, F_l, F_int):
        super().__init__()
        self.W_g = nn.Sequential(
            nn.Conv2d(F_g, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int),
        )
        self.W_x = nn.Sequential(
            nn.Conv2d(F_l, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int),
        )
        self.psi = nn.Sequential(
            nn.Conv2d(F_int, 1, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(1),
            nn.Sigmoid(),
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, g, x):
        g1 = self.W_g(g)
        x1 = self.W_x(x)
        if g1.shape[2:] != x1.shape[2:]:
            g1 = TF.interpolate(g1, size=x1.shape[2:], mode="bilinear", align_corners=True)
        psi = self.relu(g1 + x1)
        psi = self.psi(psi)
        return x * psi


class ResUNetA(nn.Module):
    """Notebook-aligned ResUNet-a architecture for water_body.pth."""

    def __init__(self, in_channels=3, out_channels=1, features=[64, 128, 256, 512, 1024]):
        super().__init__()
        self.encoder1 = ResidualConvBlock(in_channels, features[0])
        self.pool1 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.encoder2 = ResidualConvBlock(features[0], features[1])
        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.encoder3 = ResidualConvBlock(features[1], features[2])
        self.pool3 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.encoder4 = ResidualConvBlock(features[2], features[3])
        self.pool4 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.bridge = ResidualConvBlock(features[3], features[4])
        self.aspp = ASPPModule(features[4], features[4] // 2)

        self.attention4 = AttentionGate(
            F_g=features[4] // 2, F_l=features[3], F_int=features[3] // 2
        )
        self.up_conv4 = nn.ConvTranspose2d(features[4] // 2, features[3], kernel_size=2, stride=2)
        self.decoder4 = ResidualConvBlock(features[3] * 2, features[3])

        self.attention3 = AttentionGate(F_g=features[3], F_l=features[2], F_int=features[2] // 2)
        self.up_conv3 = nn.ConvTranspose2d(features[3], features[2], kernel_size=2, stride=2)
        self.decoder3 = ResidualConvBlock(features[2] * 2, features[2])

        self.attention2 = AttentionGate(F_g=features[2], F_l=features[1], F_int=features[1] // 2)
        self.up_conv2 = nn.ConvTranspose2d(features[2], features[1], kernel_size=2, stride=2)
        self.decoder2 = ResidualConvBlock(features[1] * 2, features[1])

        self.attention1 = AttentionGate(F_g=features[1], F_l=features[0], F_int=features[0] // 2)
        self.up_conv1 = nn.ConvTranspose2d(features[1], features[0], kernel_size=2, stride=2)
        self.decoder1 = ResidualConvBlock(features[0] * 2, features[0])

        self.final_conv = nn.Sequential(
            nn.Conv2d(features[0], out_channels, kernel_size=1),
            nn.Sigmoid(),
        )
        self._initialize_weights()

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def forward(self, x):
        e1 = self.encoder1(x)
        e2 = self.encoder2(self.pool1(e1))
        e3 = self.encoder3(self.pool2(e2))
        e4 = self.encoder4(self.pool3(e3))

        bridge = self.bridge(self.pool4(e4))
        bridge = self.aspp(bridge)

        a4 = self.attention4(g=bridge, x=e4)
        d4 = self.up_conv4(bridge)
        d4 = torch.cat((a4, d4), dim=1)
        d4 = self.decoder4(d4)

        d3 = self.up_conv3(d4)
        a3 = self.attention3(g=d4, x=e3)
        d3 = torch.cat((a3, d3), dim=1)
        d3 = self.decoder3(d3)

        d2 = self.up_conv2(d3)
        a2 = self.attention2(g=d3, x=e2)
        d2 = torch.cat((a2, d2), dim=1)
        d2 = self.decoder2(d2)

        d1 = self.up_conv1(d2)
        a1 = self.attention1(g=d2, x=e1)
        d1 = torch.cat((a1, d1), dim=1)
        d1 = self.decoder1(d1)

        return self.final_conv(d1)


def _import_smp():
    try:
        import segmentation_models_pytorch as smp
    except ImportError as e:
        py = sys.executable or "python"
        raise ImportError(
            "segmentation_models_pytorch is required for water_segmentation.pth. "
            f"Install it in the same environment as the API server, e.g.:\n"
            f'  "{py}" -m pip install "segmentation-models-pytorch>=0.3.3"\n'
            "or: pip install -r backend/requirements.txt"
        ) from e
    return smp


def raster_to_hwc4_water(src) -> np.ndarray:
    """(H,W,4) float32 from GeoTIFF — first four bands, or pad to four (matches training band count)."""
    n = int(src.count)
    if n >= 4:
        planes = [np.asarray(src.read(i), dtype=np.float32) for i in range(1, 5)]
        return np.stack(planes, axis=-1)
    if n == 3:
        b = np.stack([np.asarray(src.read(i), dtype=np.float32) for i in range(1, 4)], axis=-1)
        return np.concatenate([b, b[:, :, 2:3]], axis=-1)
    if n == 1:
        b = np.asarray(src.read(1), dtype=np.float32)
        return np.stack([b, b, b, b], axis=-1)
    b1 = np.asarray(src.read(1), dtype=np.float32)
    b2 = np.asarray(src.read(2), dtype=np.float32)
    return np.stack([b1, b2, b1, b2], axis=-1)


def _water_scale_hwc(arr: np.ndarray) -> np.ndarray:
    """Map reflectance/DN to ~[0, 1] (training used raw floats + Albumentations ToTensorV2, no ImageNet norm)."""
    a = np.nan_to_num(arr.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    mx = float(np.nanmax(a)) if a.size else 0.0
    if mx <= 1.5:
        return np.clip(a, 0.0, 1.0)
    if mx <= 255.5:
        return np.clip(a / 255.0, 0.0, 1.0)
    return np.clip(a / 10000.0, 0.0, 1.0)


def pil_rgb_to_hwc4(pil_img: Image.Image) -> np.ndarray:
    """RGB uploads → 4th channel = green (approximation for non-multispectral tests)."""
    rgb = np.array(pil_img.convert("RGB")).astype(np.float32) / 255.0
    g = rgb[:, :, 1:2]
    return np.concatenate([rgb, g], axis=-1)


def create_chips_hwc4(arr_hwc: np.ndarray, chip_size: int = 1024, overlap: int = 32):
    """Chip the raster. Overlap is raised to at least ``UNET_CHIP_EDGE_TRIM`` so seam strips
    trimmed in ``polygons_from_chips`` stay covered by neighboring chips (avoids grid gaps)."""
    trim = _chip_edge_trim_pixels()
    overlap = max(int(overlap), trim)
    h, w, c = arr_hwc.shape
    if c != 4:
        raise ValueError(f"Expected 4 channels, got {c}")
    nx = (w + chip_size - 1) // chip_size
    ny = (h + chip_size - 1) // chip_size
    chips: List[np.ndarray] = []
    coords: List[tuple] = []
    chip_counter = 0
    total_chips = nx * ny
    for i in range(nx):
        for j in range(ny):
            chip_counter += 1
            xs, ys = max(0, i * chip_size - overlap), max(0, j * chip_size - overlap)
            xe, ye = min(w, (i + 1) * chip_size + overlap), min(h, (j + 1) * chip_size + overlap)
            chips.append(arr_hwc[ys:ye, xs:xe, :].copy())
            coords.append((xs, ys, xe, ye))
            logger.info(
                f"Created chip {chip_counter}/{total_chips}: position ({i},{j}) -> bounds ({xs},{ys},{xe},{ye})"
            )
    return chips, coords


def preprocess_water_chip_hwc(chip_hwc: np.ndarray) -> torch.Tensor:
    """Resize to WATER_SMP_INFER_SIZE (matches notebook image_size=224), NCHW on DEVICE."""
    scaled = _water_scale_hwc(chip_hwc)
    resized = cv2.resize(
        scaled,
        (WATER_SMP_INFER_SIZE, WATER_SMP_INFER_SIZE),
        interpolation=cv2.INTER_LINEAR,
    )
    chw = np.transpose(resized, (2, 0, 1))
    t = torch.from_numpy(chw).to(DEVICE).unsqueeze(0)
    return t

# Same as Albumentations A.Normalize when input is scaled to [0, 1]
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


def _wants_imagenet_preprocess(model_path: str, checkpoint) -> bool:
    """Opt-in only: env, sidecar JSON, or checkpoint metadata. Default False = legacy /255 inputs."""
    base = os.path.basename(model_path)
    stem = os.path.splitext(base)[0]
    env_raw = (os.environ.get("UNET_IMAGENET_NORM_MODELS") or "").strip()
    for token in env_raw.split(","):
        t = token.strip()
        if not t:
            continue
        if t == base or t == stem:
            return True
    stem_path = os.path.splitext(model_path)[0]
    for meta_path in (stem_path + ".unet_meta.json", stem_path + ".meta.json"):
        if not os.path.isfile(meta_path):
            continue
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            v = meta.get("normalize") or meta.get("input_normalize")
            if isinstance(v, bool) and v:
                return True
            if str(v).lower() in ("imagenet", "image_net", "1", "true", "yes"):
                return True
        except Exception as e:
            logger.warning("Could not read %s: %s", meta_path, e)
    if isinstance(checkpoint, dict) and any(
        k in checkpoint for k in ("model_state_dict", "state_dict", "model")
    ):
        v = checkpoint.get("input_normalize") or checkpoint.get("normalize")
        if v is True:
            return True
        if isinstance(v, str) and v.lower() in ("imagenet", "image_net"):
            return True
    return False


def load_model_by_name(model_name: str):
    model_path = resolve_unet_model_path(model_name)
    if model_path in loaded_models:
        return loaded_models[model_path]
    if is_water_body_model(model_name):
        model = ResUNetA().to(DEVICE)
        try:
            checkpoint = torch.load(model_path, map_location=DEVICE, weights_only=False)
        except TypeError:
            checkpoint = torch.load(model_path, map_location=DEVICE)
        state = checkpoint
        if isinstance(state, dict):
            if "model_state_dict" in state:
                state = state["model_state_dict"]
            elif "state_dict" in state:
                state = state["state_dict"]
            elif "model" in state:
                state = state["model"]
        if isinstance(state, dict):
            state = {k.replace("module.", ""): v for k, v in state.items()}
        try:
            model.load_state_dict(state, strict=True)
        except Exception as e:
            logger.warning("Water body strict load failed (%s); retrying strict=False", e)
            model.load_state_dict(state, strict=False)
        model.eval()
        loaded_models[model_path] = model
        logger.info("Loaded water body ResUNet-a model: %s", os.path.basename(model_path))
        return model
    if is_water_smp_model(model_name):
        smp = _import_smp()
        model = smp.Unet(
            encoder_name="resnet50",
            encoder_weights=None,
            in_channels=4,
            classes=1,
        ).to(DEVICE)
        try:
            checkpoint = torch.load(model_path, map_location=DEVICE, weights_only=False)
        except TypeError:
            checkpoint = torch.load(model_path, map_location=DEVICE)
        state = checkpoint
        if isinstance(state, dict):
            if "model_state_dict" in state:
                state = state["model_state_dict"]
            elif "state_dict" in state:
                state = state["state_dict"]
            elif "model" in state:
                state = state["model"]
        if isinstance(state, dict):
            state = {k.replace("module.", ""): v for k, v in state.items()}
        try:
            model.load_state_dict(state, strict=True)
        except Exception as e:
            logger.warning("Water SMP strict load failed (%s); retrying strict=False", e)
            model.load_state_dict(state, strict=False)
        model.eval()
        loaded_models[model_path] = model
        _water_smp_resolved_paths.add(os.path.normpath(os.path.abspath(model_path)))
        logger.info("Loaded water SMP U-Net (4 ch, 224²): %s", os.path.basename(model_path))
        return model

    model = UNet(in_channels=3, out_channels=1).to(DEVICE)
    try:
        checkpoint = torch.load(model_path, map_location=DEVICE, weights_only=False)
    except TypeError:
        checkpoint = torch.load(model_path, map_location=DEVICE)
    use_imagenet = _wants_imagenet_preprocess(model_path, checkpoint)
    _preprocess_uses_imagenet[model_path] = use_imagenet
    logger.info(
        "UNet input preprocess: %s (%s)",
        "ImageNet mean/std" if use_imagenet else "legacy [0,1] (/255)",
        os.path.basename(model_path),
    )

    state = checkpoint
    if isinstance(state, dict):
        if "model_state_dict" in state:
            state = state["model_state_dict"]
        elif "state_dict" in state:
            state = state["state_dict"]
        elif "model" in state:
            state = state["model"]
    if isinstance(state, dict):
        state = {k.replace("module.", ""): v for k, v in state.items()}
    try:
        model.load_state_dict(state, strict=True)
    except Exception as e:
        logger.warning(f"Strict load failed ({e}); retrying with strict=False")
        model.load_state_dict(state, strict=False)
    model.eval()
    loaded_models[model_path] = model
    return model

def _stretch_to_uint8_hwc(arr_chw: np.ndarray) -> np.ndarray:
    """(3, H, W) -> (H, W, 3) uint8, per-channel min-max stretch."""
    _, h, w = arr_chw.shape
    out = np.zeros((h, w, 3), dtype=np.uint8)
    for c in range(3):
        ch = arr_chw[c].astype(np.float32)
        ch = np.nan_to_num(ch, nan=0.0, posinf=0.0, neginf=0.0)
        mn, mx = float(np.min(ch)), float(np.max(ch))
        if mx > mn:
            out[:, :, c] = np.clip((ch - mn) / (mx - mn) * 255.0, 0, 255).astype(np.uint8)
    return out


def raster_to_pil_rgb(src) -> Image.Image:
    """Build RGB PIL image from an open rasterio dataset (GeoTIFF / multi-band)."""
    if src.count >= 3:
        arr = src.read((1, 2, 3))
    elif src.count == 1:
        band = src.read(1)
        arr = np.stack([band, band, band], axis=0)
    else:
        b1, b2 = src.read(1), src.read(2)
        arr = np.stack([b1, b2, b1], axis=0)

    if arr.dtype == np.uint8:
        hwc = np.moveaxis(arr, 0, -1)
        return Image.fromarray(hwc, mode="RGB")
    hwc = _stretch_to_uint8_hwc(arr)
    return Image.fromarray(hwc, mode="RGB")


def create_chips(image: Image.Image, chip_size=256, overlap=32):
    trim = _chip_edge_trim_pixels()
    overlap = max(int(overlap), trim)
    w, h = image.size
    nx, ny = (w + chip_size - 1) // chip_size, (h + chip_size - 1) // chip_size
    
    total_chips = nx * ny
    logger.info(f"Image dimensions: {w}x{h} pixels")
    logger.info(f"Grid layout: {nx}x{ny} = {total_chips} total chips")
    logger.info(f"Chip size: {chip_size}x{chip_size} with {overlap}px overlap (min {trim} to match seam trim)")
    
    chips, coords = [], []
    chip_counter = 0
    
    for i in range(nx):
        for j in range(ny):
            chip_counter += 1
            xs, ys = max(0, i * chip_size - overlap), max(0, j * chip_size - overlap)
            xe, ye = min(w, (i + 1) * chip_size + overlap), min(h, (j + 1) * chip_size + overlap)
            
            chip = image.crop((xs, ys, xe, ye)).resize((chip_size, chip_size), Image.BILINEAR)
            chips.append(chip)
            coords.append((xs, ys, xe, ye))
            
            logger.info(f"Created chip {chip_counter}/{total_chips}: position ({i},{j}) -> bounds ({xs},{ys},{xe},{ye}) -> size {xe-xs}x{ye-ys}")
    
    logger.info(f"Successfully created all {total_chips} chips")
    return chips, coords

def preprocess_image_pil_for_model(img: Image.Image, add_batch_dim=True, use_imagenet: bool = False):
    """RGB resize 256×256. If use_imagenet, apply ImageNet mean/std (Albumentations-style); else legacy [0,1]."""
    arr = np.array(img.convert("RGB").resize((256, 256), Image.BILINEAR)).astype(np.float32) / 255.0
    chw = arr.transpose(2, 0, 1)
    if use_imagenet:
        chw = (chw - _IMAGENET_MEAN) / _IMAGENET_STD
    tensor = torch.from_numpy(chw).to(DEVICE)

    if add_batch_dim:
        tensor = tensor.unsqueeze(0)

    return tensor

def predict_mask(model, tensor, resolved_model_path: str):
    with torch.no_grad():
        out = model(tensor)
        if resolved_model_path in _water_smp_resolved_paths:
            out = torch.sigmoid(out)
        return out.squeeze().cpu().numpy()


def _water_body_predict_notebook_parity(
    model,
    pil_img: Image.Image,
    threshold: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Notebook parity: RGB -> resize 512 -> tensor -> model -> threshold -> nearest resize back."""
    image = pil_img.convert("RGB")
    orig_size = image.size
    image_resized = image.resize((WATER_BODY_INFER_SIZE, WATER_BODY_INFER_SIZE))
    image_np = np.array(image_resized)
    image_tensor = (
        torch.from_numpy(np.transpose(image_np, (2, 0, 1)))
        .float()
        .unsqueeze(0)
        .to(DEVICE)
    )
    with torch.no_grad():
        pred = model(image_tensor)
    pred_np = pred.squeeze().cpu().numpy().astype(np.float32)
    mask_small = (pred_np > float(threshold)).astype(np.uint8)
    mask = cv2.resize(mask_small, orig_size, interpolation=cv2.INTER_NEAREST)
    conf = cv2.resize(pred_np, orig_size, interpolation=cv2.INTER_LINEAR)
    return mask, conf


def _water_body_forward_chip_prob(model, pil_chip: Image.Image) -> np.ndarray:
    """One 512² chip (from create_chips): forward only → (512,512) probabilities.

    Same tensor convention as _water_body_predict_notebook_parity (RGB float tensor, no /255).
    """
    image = pil_chip.convert("RGB").resize((WATER_BODY_INFER_SIZE, WATER_BODY_INFER_SIZE))
    image_np = np.array(image)
    image_tensor = (
        torch.from_numpy(np.transpose(image_np, (2, 0, 1)))
        .float()
        .unsqueeze(0)
        .to(DEVICE)
    )
    with torch.no_grad():
        pred = model(image_tensor)
    return pred.squeeze().cpu().numpy().astype(np.float32)


def _unet_post_mask_response_dict(
    run_id: str,
    mask_binary: np.ndarray,
    confidence_map: Optional[np.ndarray],
    size,
    img_crs,
    transform_raster,
    threshold: float,
    geo_bbox,
    model_name: str = "",
    source_filename: Optional[str] = None,
    lulc_prediction_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build UNet response from a full-image binary mask (no tiling)."""
    binary = _unet_refine_binary_mask((np.asarray(mask_binary) > 0).astype(np.uint8))
    pix_polys = mask_to_polygons_from_binary(binary, min_area=20)
    geo_polys = (
        [transform_polygon_to_geo(p, size, transform_raster) for p in pix_polys]
        if transform_raster
        else pix_polys
    )
    geo_polys = _unet_postprocess_poly_chain(geo_polys)

    run_dir = os.path.join("outputs", run_id)
    os.makedirs(run_dir, exist_ok=True)

    saved_npz: Optional[str] = None
    saved_meta: Optional[str] = None
    if confidence_map is not None and confidence_map.size > 0:
        try:
            sp, mp = _save_unet_confidence_bundle(
                run_id,
                confidence_map.astype(np.float32),
                img_crs,
                transform_raster,
                geo_bbox,
                (int(size[0]), int(size[1])),
                model_name,
            )
            saved_npz, saved_meta = sp, mp
        except Exception as e:
            logger.warning("Water body: could not save confidence bundle: %s", e)

    gdf_original = gpd.GeoDataFrame(geometry=geo_polys, crs=img_crs)
    if not gdf_original.empty:
        if gdf_original.crs is not None and gdf_original.crs.to_string() != "EPSG:4326":
            gdf_wgs84 = gdf_original.to_crs(epsg=4326)
        else:
            gdf_wgs84 = gdf_original
            if gdf_wgs84.crs is None:
                gdf_wgs84.crs = "EPSG:4326"
    else:
        gdf_wgs84 = gdf_original
        if gdf_wgs84.crs is None:
            gdf_wgs84.crs = "EPSG:4326"

    geojson_path, shp_zip_path = save_geojson_and_shapefile(
        gdf_wgs84.geometry.tolist(),
        "EPSG:4326",
        run_dir,
    )

    overlay_filename = f"overlay_{run_id}.png"
    overlay_path = os.path.join("outputs", overlay_filename)
    mask_img = (binary * 255).astype(np.uint8)
    rgba_arr = np.zeros((mask_img.shape[0], mask_img.shape[1], 4), dtype=np.uint8)
    rgba_arr[..., 0] = 255
    rgba_arr[..., 3] = mask_img
    Image.fromarray(rgba_arr).save(overlay_path, format="PNG")

    overlay_bounds_wgs84 = [[0.0, 0.0], [0.0, 0.0]]
    total_area_original = 0.0
    avg_area_original = 0.0

    if not gdf_wgs84.empty:
        try:
            bounds = gdf_wgs84.total_bounds
            if len(bounds) == 4 and all(math.isfinite(b) for b in bounds):
                overlay_bounds_wgs84 = [
                    [float(bounds[1]), float(bounds[0])],
                    [float(bounds[3]), float(bounds[2])],
                ]

            if gdf_original.crs is not None and gdf_original.crs.is_projected:
                total_area_original = float(gdf_original.geometry.area.sum())
                avg_area_original = float(gdf_original.geometry.area.mean())
            else:
                centroid = gdf_wgs84.unary_union.centroid
                lon, lat = centroid.x, centroid.y
                utm_zone = int((lon + 180) / 6) + 1
                epsg_code = 32600 + utm_zone if lat >= 0 else 32700 + utm_zone
                try:
                    gdf_projected = gdf_wgs84.to_crs(epsg=epsg_code)
                    total_area_original = float(gdf_projected.geometry.area.sum())
                    avg_area_original = float(gdf_projected.geometry.area.mean())
                except Exception:
                    total_area_original = float(gdf_wgs84.geometry.area.sum())
                    avg_area_original = float(gdf_wgs84.geometry.area.mean())
        except Exception as e:
            logger.error("Failed to compute bounds/stats: %s", e, exc_info=True)

    if overlay_bounds_wgs84 == [[0.0, 0.0], [0.0, 0.0]]:
        fb = raster_extent_bounds_wgs84(img_crs, geo_bbox)
        if fb:
            overlay_bounds_wgs84 = fb

    geojson_url = f"/outputs/{run_id}/buildings.geojson"
    shapefile_url = f"/outputs/{run_id}/building_polygons.zip"
    overlay_url = f"/outputs/{overlay_filename}"

    write_unet_manifest(
        run_id,
        model_name=model_name or "",
        source_filename=source_filename or "",
        inference_threshold=threshold,
        geojson_path=os.path.abspath(geojson_path),
        shapefile_path=os.path.abspath(shp_zip_path),
        overlay_path=os.path.abspath(overlay_path),
        confidence_npz_path=os.path.abspath(saved_npz) if saved_npz else None,
        meta_json_path=os.path.abspath(saved_meta) if saved_meta else None,
        width=int(size[0]),
        height=int(size[1]),
    )

    linked_lulc = False
    if (lulc_prediction_id or "").strip():
        try:
            linked_lulc = attach_building_detection_to_lulc(
                (lulc_prediction_id or "").strip(),
                task="unet",
                od_run_id=run_id,
                inference_threshold=float(threshold),
                geojson_abs_path=os.path.abspath(geojson_path),
                full_geojson_abs_path=None,
                confidence_npz_abs_path=os.path.abspath(saved_npz)
                if saved_npz and os.path.isfile(saved_npz)
                else None,
                model_name=model_name or "",
            )
        except Exception as e:
            logger.warning("UNet LULC attach skipped: %s", e)

    return {
        "task": "unet",
        "count": int(len(gdf_wgs84)),
        "total_area": float(total_area_original) if math.isfinite(total_area_original) else 0.0,
        "average_area": float(avg_area_original) if math.isfinite(avg_area_original) else 0.0,
        "geojson_url": geojson_url,
        "shapefile_url": shapefile_url,
        "overlay_url": overlay_url,
        "overlay_bounds": overlay_bounds_wgs84,
        "width": int(size[0]),
        "height": int(size[1]),
        "crs": "EPSG:4326",
        "run_id": run_id,
        "inference_threshold": threshold,
        "confidence_bundle_saved": bool(saved_npz and os.path.isfile(saved_npz)),
        "lulc_prediction_linked": linked_lulc,
    }

def _unet_overlap_fusion_mode() -> str:
    """Blend overlapping chip predictions into one raster.

    ``mean`` averages overlapping tiles (legacy). Along chip seams both tiles often have weaker
    boundary scores, so the mean can dip below threshold and produce vertical/horizontal gaps.

    ``max`` uses the per-pixel maximum (recommended): if any tile is confident at a pixel, it stays.

    UNET_OVERLAP_FUSION: ``mean`` | ``max`` (default ``max``).
    """
    v = (os.environ.get("UNET_OVERLAP_FUSION") or "max").strip().lower()
    if v in ("mean", "average", "avg"):
        return "mean"
    return "max"


def reassemble_predictions(preds, coords, size):
    h, w = int(size[1]), int(size[0])
    if _unet_overlap_fusion_mode() == "max":
        full = np.zeros((h, w), np.float32)
        for pred, (xs, ys, xe, ye) in zip(preds, coords):
            chip = cv2.resize(
                np.asarray(pred, dtype=np.float32),
                (xe - xs, ye - ys),
                interpolation=cv2.INTER_LINEAR,
            )
            slot = full[ys:ye, xs:xe]
            np.maximum(slot, chip, out=slot)
        return full
    full = np.zeros((h, w), np.float32)
    counts = np.zeros_like(full)
    for pred, (xs, ys, xe, ye) in zip(preds, coords):
        chip = cv2.resize(pred, (xe - xs, ye - ys), interpolation=cv2.INTER_LINEAR)
        full[ys:ye, xs:xe] += chip
        counts[ys:ye, xs:xe] += 1
    counts[counts == 0] = 1
    return full / counts


def _reassemble_running_init(size_wh: Tuple[int, int]) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    w, h = int(size_wh[0]), int(size_wh[1])
    full = np.zeros((h, w), np.float32)
    if _unet_overlap_fusion_mode() == "max":
        return full, None
    return full, np.zeros((h, w), np.float32)


def _reassemble_running_add(
    full: np.ndarray,
    counts: Optional[np.ndarray],
    pred,
    coord: Tuple[int, int, int, int],
) -> None:
    xs, ys, xe, ye = coord
    chip = cv2.resize(
        np.asarray(pred, dtype=np.float32),
        (xe - xs, ye - ys),
        interpolation=cv2.INTER_LINEAR,
    )
    if counts is None:
        slot = full[ys:ye, xs:xe]
        np.maximum(slot, chip, out=slot)
        return
    full[ys:ye, xs:xe] += chip
    counts[ys:ye, xs:xe] += 1.0


def _unet_chip_only_pixel_limit() -> int:
    return int(os.environ.get("UNET_CHIP_ONLY_PIXELS", "100000000"))


def _stream_use_fused_preview(npx: int) -> bool:
    """Fused SSE preview — same vectorization as saved GeoJSON when under UNET_CHIP_ONLY_PIXELS."""
    if (os.environ.get("UNET_STREAM_FUSED_PREVIEW") or "1").strip().lower() in ("0", "false", "no"):
        return False
    return npx <= _unet_chip_only_pixel_limit()


def _unet_stream_preview_downsample() -> int:
    """Mask downsample before contouring (fused SSE preview and saved GeoJSON use the same factor).

    UNET_STREAM_PREVIEW_DOWNSAMPLE: 1 = full resolution, 2–8 = coarser/faster (default 2).
    """
    try:
        v = int(os.environ.get("UNET_STREAM_PREVIEW_DOWNSAMPLE", "2"))
    except ValueError:
        v = 2
    return max(1, min(v, 8))


def _unet_final_match_stream_preview_opt_out() -> bool:
    """If true, fused-path GeoJSON uses full-resolution contours instead of the preview pipeline.

    Set UNET_FINAL_MATCH_STREAM_PREVIEW=0 only if you need legacy full-res vectors.
    """
    return (os.environ.get("UNET_FINAL_MATCH_STREAM_PREVIEW") or "").strip().lower() in (
        "0",
        "false",
        "no",
    )


def _unet_fused_conf_to_geo_polygons(
    conf: np.ndarray,
    threshold: float,
    size,
    transform_raster,
    *,
    preview_downsample: int = 1,
) -> List:
    """Vectorize fused confidence grid; optional mask downsample matches SSE fused preview."""
    binary = (conf > threshold).astype(np.uint8)
    binary = _unet_refine_binary_mask(binary)
    wpx, hpx = int(size[0]), int(size[1])
    ds = max(1, min(int(preview_downsample), 8))
    if ds > 1:
        smw, smh = max(1, wpx // ds), max(1, hpx // ds)
        binary = cv2.resize(binary, (smw, smh), interpolation=cv2.INTER_NEAREST)
        min_area_px = max(1, int(round(20.0 / float(ds * ds))))
        sx = float(wpx) / float(smw)
        sy = float(hpx) / float(smh)
    else:
        min_area_px = 20
        sx = sy = 1.0
    pix_polys = mask_to_polygons_from_binary(binary, min_area=min_area_px)
    if sx != 1.0 or sy != 1.0:
        pix_polys = [
            affinity.scale(p, xfact=sx, yfact=sy, origin=(0, 0)) for p in pix_polys
        ]
    geo_polys = (
        [transform_polygon_to_geo(p, size, transform_raster) for p in pix_polys]
        if transform_raster
        else pix_polys
    )
    geo_polys = dedupe_detection_polygons(geo_polys)
    geo_polys = merge_chip_seam_polygons(geo_polys)
    geo_polys = filter_unet_seam_sliver_polygons(geo_polys)
    geo_polys = regularize_detection_polygons(geo_polys)
    return geo_polys


def _chip_edge_trim_pixels() -> int:
    """Strip this many pixels from each tile side that borders another tile (not the raster edge).

    Suppresses spurious rectangles along chip seams from CNN boundary effects. Set UNET_CHIP_EDGE_TRIM=0 to disable.
    """
    try:
        return max(0, int(os.environ.get("UNET_CHIP_EDGE_TRIM", "48")))
    except ValueError:
        return 48


def filter_unet_seam_sliver_polygons(polygons: List[Polygon]) -> List[Polygon]:
    """Drop thin, very elongated axis-aligned slivers (common chip-boundary junk).

    UNET_SLIVER_MAX_THIN (default 72): max short side of bbox in pixels to qualify.
    UNET_SLIVER_MIN_ASPECT (default 6): min long/short for bbox.
    UNET_FILTER_SEAM_SLIVERS=0 disables.
    """
    if not polygons:
        return []
    if (os.environ.get("UNET_FILTER_SEAM_SLIVERS") or "1").strip().lower() in ("0", "false", "no"):
        return polygons
    try:
        max_thin = float(os.environ.get("UNET_SLIVER_MAX_THIN", "72"))
        min_ar = float(os.environ.get("UNET_SLIVER_MIN_ASPECT", "6"))
    except ValueError:
        max_thin, min_ar = 72.0, 6.0
    if max_thin <= 0:
        return polygons
    out: List[Polygon] = []
    dropped = 0
    for poly in polygons:
        try:
            minx, miny, maxx, maxy = poly.bounds
            bw, bh = maxx - minx, maxy - miny
            if bw <= 0 or bh <= 0:
                continue
            short, long = min(bw, bh), max(bw, bh)
            ar = long / max(short, 1e-9)
            fill = poly.area / (bw * bh + 1e-9)
            if short <= max_thin and ar >= min_ar and fill > 0.6:
                dropped += 1
                continue
        except Exception:
            pass
        out.append(poly)
    if dropped:
        logger.info("Filtered %s seam-sliver polygons (thin elongated bbox)", dropped)
    return out


def _trim_tile_seam_u8(
    m: np.ndarray,
    xs: int,
    ys: int,
    xe: int,
    ye: int,
    img_w: int,
    img_h: int,
    margin: int,
) -> np.ndarray:
    """Zero out overlap-border strips so only tile interiors contribute (neighbor tiles cover seams)."""
    if margin <= 0:
        return m
    ch, cw = int(m.shape[0]), int(m.shape[1])
    if ch < 4 or cw < 4:
        return m
    margin = min(margin, max(1, cw // 4), max(1, ch // 4))
    out = np.array(m, copy=True)
    if xs > 0:
        out[:, :margin] = 0
    if xe < img_w:
        out[:, cw - margin :] = 0
    if ys > 0:
        out[:margin, :] = 0
    if ye < img_h:
        out[ch - margin :, :] = 0
    return out


def straighten_mask_binary(mask: np.ndarray) -> np.ndarray:
    """Minimum-area rotated rectangle (MAR) per connected component: straight edges in pixel space.

    Controlled only by env (``UNET_STRAIGHTEN_MASK`` etc.); when disabled, returns ``mask`` unchanged.
    ``mask`` is uint8 with foreground >0 (0/1 or 0/255). Returns the same scale.
    """
    if not _unet_straighten_mask_enabled():
        return np.asarray(mask, dtype=np.uint8)
    m = np.asarray(mask, dtype=np.uint8)
    if not m.any():
        return m
    scale255 = bool(m.max() > 1)
    mask_255 = ((m > 0).astype(np.uint8)) * 255

    close_sz = _unet_straighten_close_size()
    if close_sz > 0:
        k = max(3, int(close_sz) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        mask_255 = cv2.morphologyEx(mask_255, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask_255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    straightened = np.zeros_like(mask_255)
    min_area = _unet_straighten_min_area_px()
    max_mar = _unet_straighten_max_mar_area_px()

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        if max_mar > 0 and area > max_mar:
            cv2.drawContours(straightened, [cnt], -1, 255, thickness=-1)
        else:
            rect = cv2.minAreaRect(cnt)
            box = cv2.boxPoints(rect)
            box = np.int32(box)
            cv2.fillPoly(straightened, [box], 255)

    out01 = (straightened > 0).astype(np.uint8)
    return (out01 * 255).astype(np.uint8) if scale255 else out01


def _unet_refine_binary_mask(mask: np.ndarray) -> np.ndarray:
    """Optional MAR straighten (env)."""
    m = np.asarray(mask, dtype=np.uint8)
    return straighten_mask_binary(m)


def polygons_from_chips(
    preds,
    coords,
    threshold: float,
    min_area: int = 20,
    image_wh: Optional[Tuple[int, int]] = None,
):
    """Contours per chip, global pixel coords — avoids full-image float32 buffers and watershed OOM.

    When ``image_wh`` is set, masks are trimmed at inner tile seams (see ``_chip_edge_trim_pixels``) to reduce
    false rectangular detections aligned with the chip grid.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    trim_px = _chip_edge_trim_pixels() if image_wh is not None else 0
    img_w, img_h = (image_wh[0], image_wh[1]) if image_wh else (10**9, 10**9)
    out = []
    for pred, (xs, ys, xe, ye) in zip(preds, coords):
        cw, ch = xe - xs, ye - ys
        if cw < 2 or ch < 2:
            continue
        p = cv2.resize(np.asarray(pred, dtype=np.float32), (cw, ch), interpolation=cv2.INTER_LINEAR)
        m = ((p > threshold) * 255).astype(np.uint8)
        if not m.any():
            continue
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel, iterations=1)
        if not m.any():
            continue
        if trim_px > 0 and image_wh is not None:
            m = _trim_tile_seam_u8(m, xs, ys, xe, ye, img_w, img_h, trim_px)
        if not m.any():
            continue
        m = _unet_refine_binary_mask(m)
        if not m.any():
            continue
        contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            if len(cnt) < 4:
                continue
            coords_xy = [(int(pt[0][0]) + xs, int(pt[0][1]) + ys) for pt in cnt]
            poly = Polygon(coords_xy)
            if poly.is_valid and poly.area >= min_area:
                out.append(poly)
    return filter_unet_seam_sliver_polygons(out)


def save_downsampled_overlay_png(preds, coords, threshold, size_wh, out_path: str, max_side: int = 8192):
    """Merge chip masks into a small RGBA PNG (preview only; GeoJSON is authoritative)."""
    w, h = size_wh[0], size_wh[1]
    sc = min(1.0, float(max_side) / max(w, h))
    tw, th = max(1, int(round(w * sc))), max(1, int(round(h * sc)))
    alpha = np.zeros((th, tw), dtype=np.uint8)
    for pred, (xs, ys, xe, ye) in zip(preds, coords):
        cw, ch = xe - xs, ye - ys
        if cw < 1 or ch < 1:
            continue
        p = cv2.resize(np.asarray(pred, dtype=np.float32), (cw, ch), interpolation=cv2.INTER_LINEAR)
        bm = ((p > threshold) * 255).astype(np.uint8)
        if not bm.any():
            continue
        x0, y0 = int(xs * sc), int(ys * sc)
        x1, y1 = int(np.ceil(xe * sc)), int(np.ceil(ye * sc))
        x1, y1 = max(x0 + 1, min(tw, x1)), max(y0 + 1, min(th, y1))
        bw, bh = x1 - x0, y1 - y0
        if bw < 1 or bh < 1:
            continue
        bs = cv2.resize(bm, (bw, bh), interpolation=cv2.INTER_NEAREST)
        alpha[y0:y1, x0:x1] = np.maximum(alpha[y0:y1, x0:x1], bs)
    rgba = np.zeros((th, tw, 4), dtype=np.uint8)
    rgba[:, :, 0] = 255
    rgba[:, :, 3] = alpha
    Image.fromarray(rgba).save(out_path, format="PNG")

def _mask_to_polygons_watershed(mask_uint8: np.ndarray, min_area: int) -> List[Polygon]:
    """Legacy: separate touching instances via distance transform + watershed (can split one roof into two)."""
    _, binary = cv2.threshold(mask_uint8, 0, 255, cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)
    dist = cv2.distanceTransform(opened, cv2.DIST_L2, 5)
    if dist.max() == 0:
        return []
    local = (dist > 0.4 * dist.max()).astype(np.uint8)
    markers, _ = ndi.label(local)
    labels = watershed(-dist, markers, mask=opened)
    polys: List[Polygon] = []
    for lab in np.unique(labels):
        if lab == 0:
            continue
        m = np.uint8(labels == lab)
        contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            if len(cnt) > 3:
                coords = [(int(p[0][0]), int(p[0][1])) for p in cnt]
                poly = Polygon(coords)
                if poly.is_valid and poly.area > min_area:
                    polys.append(poly)
    return polys


def _mask_to_polygons_connected_components(mask_uint8: np.ndarray, min_area: int) -> List[Polygon]:
    """One exterior polygon per 4-connected component — avoids splitting one building across two watershed basins."""
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    opened = cv2.morphologyEx(mask_uint8, cv2.MORPH_OPEN, kernel, iterations=1)
    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polys: List[Polygon] = []
    for cnt in contours:
        if len(cnt) < 4:
            continue
        coords = [(int(p[0][0]), int(p[0][1])) for p in cnt]
        poly = Polygon(coords)
        if poly.is_valid and poly.area >= min_area:
            polys.append(poly)
    return polys


def mask_to_polygons_from_binary(mask, min_area=20):
    """Vectorize binary building mask. Default: one polygon per connected region (no watershed splitting).

    Set UNET_MASK_WATERSHED=1 to restore watershed-based instance splitting (can duplicate/split roofs).
    """
    try:
        img = (np.asarray(mask) * 255).astype(np.uint8)
        if not img.any():
            return []
        use_ws = (os.environ.get("UNET_MASK_WATERSHED") or "").strip().lower() in ("1", "true", "yes")
        if use_ws:
            return _mask_to_polygons_watershed(img, min_area)
        return _mask_to_polygons_connected_components(img, min_area)
    except Exception:
        return []

def transform_polygon_to_geo(poly, size, transform: Optional[Affine]):
    if transform is None: return poly
    try:
        def px2geo(x,y): return transform*(x,y)
        ext=[px2geo(x,y) for x,y in poly.exterior.coords]
        ints=[[px2geo(x,y) for x,y in ring.coords] for ring in poly.interiors]
        return Polygon(ext,ints)
    except: return poly

def save_geojson_and_shapefile(polys, crs, out_dir):
    gdf = gpd.GeoDataFrame(geometry=polys, crs=crs)
    if len(gdf) > 0:
        gdf["building_id"] = range(1, len(gdf) + 1)
        try:
            if gdf.crs is not None and getattr(gdf.crs, "is_geographic", False):
                gdf["area"] = gdf.to_crs(gdf.estimate_utm_crs()).geometry.area
            else:
                gdf["area"] = gdf.geometry.area
        except Exception as ex:
            logger.warning("Could not compute footprint areas: %s", ex)
    geojson = os.path.join(out_dir, "buildings.geojson")
    gdf.to_file(geojson, driver="GeoJSON")
    shp_dir = os.path.join(out_dir, "shp")
    os.makedirs(shp_dir, exist_ok=True)
    gdf.to_file(os.path.join(shp_dir, "buildings.shp"))
    zip_path = os.path.join(out_dir, "building_polygons.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in os.listdir(shp_dir):
            zf.write(os.path.join(shp_dir, f), arcname=f)
    return geojson, zip_path


def raster_extent_bounds_wgs84(img_crs, geo_bbox) -> Optional[list]:
    """[[south, west], [north, east]] for Leaflet when there are no detection polygons."""
    if img_crs is None or geo_bbox is None or len(geo_bbox) < 4:
        return None
    try:
        left, bottom, right, top = geo_bbox[0], geo_bbox[1], geo_bbox[2], geo_bbox[3]
        w, s, e, n = transform_bounds(img_crs, "EPSG:4326", left, bottom, right, top)
        return [[float(s), float(w)], [float(n), float(e)]]
    except Exception as e:
        logger.warning("raster_extent_bounds_wgs84 failed: %s", e)
        return None


def _save_unet_confidence_bundle(
    run_id: str,
    conf: np.ndarray,
    img_crs,
    transform_raster,
    geo_bbox,
    size_wh: Tuple[int, int],
    model_name: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Persist fused probability grid for /runs/{run_id}/geojson re-thresholding."""
    run_dir = os.path.join("outputs", run_id)
    try:
        os.makedirs(run_dir, exist_ok=True)
        npz_path = os.path.join(run_dir, "confidence_fp16.npz")
        np.savez_compressed(npz_path, conf=conf.astype(np.float16), h=int(conf.shape[0]), w=int(conf.shape[1]))
        tr = None
        if transform_raster is not None:
            tr = [
                float(transform_raster.a),
                float(transform_raster.b),
                float(transform_raster.c),
                float(transform_raster.d),
                float(transform_raster.e),
                float(transform_raster.f),
            ]
        meta = {
            "run_id": run_id,
            "model_name": model_name,
            "width": int(size_wh[0]),
            "height": int(size_wh[1]),
            "crs": str(img_crs) if img_crs is not None else None,
            "transform": tr,
            "geo_bbox": [float(x) for x in geo_bbox] if geo_bbox is not None else None,
            "confidence_npz": os.path.basename(npz_path),
        }
        meta_path = os.path.join(run_dir, "unet_run_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return npz_path, meta_path
    except Exception as e:
        logger.warning("UNet: could not save confidence bundle: %s", e)
        return None, None


def _unet_postprocess_poly_chain(
    geo_polys: List,
    *,
    iou_threshold: Optional[float] = None,
    seam_merge_gap: Optional[float] = None,
    regularize_mode: Optional[str] = None,
    regularize_tolerance: Optional[float] = None,
) -> List:
    """UNet footprint chain: dedupe → seam merge → sliver filter → regularize (env or overrides)."""
    geo_polys = dedupe_detection_polygons(geo_polys, iou_threshold=iou_threshold)
    geo_polys = merge_chip_seam_polygons(geo_polys, max_gap=seam_merge_gap)
    geo_polys = filter_unet_seam_sliver_polygons(geo_polys)
    geo_polys = regularize_detection_polygons(
        geo_polys,
        mode=regularize_mode,
        tolerance=regularize_tolerance,
    )
    return geo_polys


def _unet_geojson_from_conf_threshold(
    conf: np.ndarray,
    threshold: float,
    size,
    img_crs,
    transform_raster,
    postprocess_kwargs: Optional[Dict[str, Any]] = None,
) -> dict:
    """Fused-path vectorization (matches small-raster branch in _unet_post_chips_response_dict)."""
    binary = (conf > threshold).astype(np.uint8)
    binary = _unet_refine_binary_mask(binary)
    pix_polys = mask_to_polygons_from_binary(binary, min_area=20)
    geo_polys = (
        [transform_polygon_to_geo(p, size, transform_raster) for p in pix_polys]
        if transform_raster
        else pix_polys
    )
    pp = postprocess_kwargs or {}
    geo_polys = _unet_postprocess_poly_chain(
        geo_polys,
        iou_threshold=pp.get("iou_threshold"),
        seam_merge_gap=pp.get("seam_merge_gap"),
        regularize_mode=pp.get("regularize_mode"),
        regularize_tolerance=pp.get("regularize_tolerance"),
    )
    if not geo_polys:
        return {"type": "FeatureCollection", "features": []}
    crs_u = img_crs or "EPSG:4326"
    gdf = gpd.GeoDataFrame(geometry=geo_polys, crs=crs_u)
    try:
        if gdf.crs is not None and gdf.crs.to_string() != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
    except Exception:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(gdf.to_json())


def _load_unet_conf_and_meta(run_id: str) -> Tuple[Optional[np.ndarray], Optional[dict]]:
    run_dir = os.path.join("outputs", run_id)
    meta_path = os.path.join(run_dir, "unet_run_meta.json")
    if not os.path.isfile(meta_path):
        return None, None
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    npz_name = meta.get("confidence_npz") or "confidence_fp16.npz"
    npz_path = os.path.join(run_dir, npz_name)
    if not os.path.isfile(npz_path):
        return None, meta
    z = np.load(npz_path)
    conf = z["conf"].astype(np.float32)
    return conf, meta

@app.get("/models")
async def list_models():
    """Get available AI models"""
    try:
        models = discover_unet_model_basenames()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        return {"models": []}

def predict_mask_batch(model, chips, batch_size=8, use_imagenet: bool = False):
    '''Process multiple chips in batches for improved performance'''
    predictions = []
    total_batches = (len(chips) + batch_size - 1) // batch_size
    
    logger.info(f"Processing {len(chips)} chips in {total_batches} batches of size {batch_size}")
    
    for batch_idx in range(0, len(chips), batch_size):
        batch_chips = chips[batch_idx:batch_idx + batch_size]
        current_batch_size = len(batch_chips)
        
        # Preprocess all chips in the batch
        batch_tensors = []
        for chip in batch_chips:
            tensor = preprocess_image_pil_for_model(chip, add_batch_dim=False, use_imagenet=use_imagenet)
            batch_tensors.append(tensor)
        
        # Stack tensors into a single batch
        batch_tensor = torch.stack(batch_tensors).to(DEVICE)
        
        # Run inference on the batch (UNet.forward already applies sigmoid)
        with torch.no_grad():
            batch_predictions = model(batch_tensor)
        
        # Convert predictions back to numpy arrays
        for i in range(current_batch_size):
            pred = batch_predictions[i].squeeze().cpu().numpy()
            predictions.append(pred)
        
        batch_num = (batch_idx // batch_size) + 1
        logger.info(f"Completed batch {batch_num}/{total_batches}")
    
    return predictions


def _unet_fused_preview_geojson(
    run_full: np.ndarray,
    run_counts: Optional[np.ndarray],
    threshold: float,
    size,
    transform_raster,
    img_crs,
    preview_downsample: int = 1,
) -> dict:
    """Incremental fused mask → GeoJSON (optional downsample; matches final save when stream-aligned)."""
    if run_counts is None:
        conf = run_full
    else:
        mask = run_counts > 0
        conf = np.zeros_like(run_full, dtype=np.float32)
        conf[mask] = run_full[mask] / run_counts[mask]
    geo_polys = _unet_fused_conf_to_geo_polygons(
        conf,
        threshold,
        size,
        transform_raster,
        preview_downsample=preview_downsample,
    )
    if not geo_polys:
        return {"type": "FeatureCollection", "features": []}
    crs_u = img_crs or "EPSG:4326"
    gdf = gpd.GeoDataFrame(geometry=geo_polys, crs=crs_u)
    try:
        if gdf.crs is not None and gdf.crs.to_string() != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
    except Exception:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(gdf.to_json())


def _unet_chips_preview_geojson(
    preds,
    coords,
    threshold: float,
    size,
    transform_raster,
    img_crs,
) -> dict:
    pix_polys = polygons_from_chips(
        preds,
        coords,
        threshold,
        min_area=20,
        image_wh=(int(size[0]), int(size[1])),
    )
    geo_polys = (
        [transform_polygon_to_geo(p, size, transform_raster) for p in pix_polys]
        if transform_raster
        else pix_polys
    )
    geo_polys = dedupe_detection_polygons(geo_polys)
    geo_polys = merge_chip_seam_polygons(geo_polys)
    geo_polys = filter_unet_seam_sliver_polygons(geo_polys)
    geo_polys = regularize_detection_polygons(geo_polys)
    if not geo_polys:
        return {"type": "FeatureCollection", "features": []}
    crs_u = img_crs or "EPSG:4326"
    gdf = gpd.GeoDataFrame(geometry=geo_polys, crs=crs_u)
    try:
        if gdf.crs is not None and gdf.crs.to_string() != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
    except Exception:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(gdf.to_json())


def _unet_post_chips_response_dict(
    run_id: str,
    preds,
    coords,
    size,
    img_crs,
    transform_raster,
    threshold: float,
    geo_bbox,
    model_name: str = "",
    source_filename: Optional[str] = None,
    lulc_prediction_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Vectorize, save artifacts, and build the same response dict as /predict (no progress updates)."""
    wpx, hpx = int(size[0]), int(size[1])
    npx = wpx * hpx
    # Above this, use per-chip contours (cheap RAM); below, fuse overlapping tiles then vectorize once
    # (fixes buildings split across chip seams). Default 100 Mpix ≈ 400 MB float32 — lower if OOM.
    chip_only_limit = _unet_chip_only_pixel_limit()

    saved_npz: Optional[str] = None
    saved_meta: Optional[str] = None
    conf_fused: Optional[np.ndarray] = None
    try:
        conf_fused = reassemble_predictions(preds, coords, size)
        sp, mp = _save_unet_confidence_bundle(
            run_id, conf_fused, img_crs, transform_raster, geo_bbox, size, model_name
        )
        saved_npz, saved_meta = sp, mp
    except Exception as e:
        logger.warning("UNet: fuse/save confidence grid: %s", e)
        conf_fused = None

    if npx > chip_only_limit:
        logger.info(
            "Large raster (~%.1f Mpix > UNET_CHIP_ONLY_PIXELS=%s): chip-wise polygons + downsampled overlay "
            "(raise limit or set UNET_CHIP_ONLY_PIXELS to fuse + single vectorization if RAM allows)",
            npx / 1e6,
            chip_only_limit,
        )
        if conf_fused is not None:
            del conf_fused
            conf_fused = None
        pix_polys = polygons_from_chips(
            preds,
            coords,
            threshold,
            min_area=20,
            image_wh=(wpx, hpx),
        )
        geo_polys = (
            [transform_polygon_to_geo(p, size, transform_raster) for p in pix_polys]
            if transform_raster
            else pix_polys
        )
        binary = None
    else:
        logger.info(
            "Fused tile predictions + connected-component vectorization (~%.1f Mpix < limit %s); "
            "overlap fusion=%s",
            npx / 1e6,
            chip_only_limit,
            _unet_overlap_fusion_mode(),
        )
        if conf_fused is None:
            conf_fused = reassemble_predictions(preds, coords, size)
        # Full-res refined mask for overlay PNG (always full resolution).
        binary = (conf_fused > threshold).astype(np.uint8)
        binary = _unet_refine_binary_mask(binary)

        if _unet_final_match_stream_preview_opt_out():
            pix_polys = mask_to_polygons_from_binary(binary, min_area=20)
            geo_polys = (
                [transform_polygon_to_geo(p, size, transform_raster) for p in pix_polys]
                if transform_raster
                else pix_polys
            )
            geo_polys = dedupe_detection_polygons(geo_polys)
            geo_polys = merge_chip_seam_polygons(geo_polys)
            geo_polys = filter_unet_seam_sliver_polygons(geo_polys)
            geo_polys = regularize_detection_polygons(geo_polys)
        else:
            preview_ds = _unet_stream_preview_downsample()
            geo_polys = _unet_fused_conf_to_geo_polygons(
                conf_fused,
                threshold,
                size,
                transform_raster,
                preview_downsample=preview_ds,
            )
            logger.info(
                "Fused GeoJSON uses the same vectorization as stream preview (UNET_STREAM_PREVIEW_DOWNSAMPLE=%s)",
                preview_ds,
            )

        del conf_fused
        conf_fused = None

    if npx > chip_only_limit:
        geo_polys = dedupe_detection_polygons(geo_polys)
        geo_polys = merge_chip_seam_polygons(geo_polys)
        geo_polys = filter_unet_seam_sliver_polygons(geo_polys)
        geo_polys = regularize_detection_polygons(geo_polys)

    run_dir = os.path.join("outputs", run_id)
    os.makedirs(run_dir, exist_ok=True)

    gdf_original = gpd.GeoDataFrame(geometry=geo_polys, crs=img_crs)
    logger.info("Created GeoDataFrame with %d polygons in CRS: %s", len(gdf_original), gdf_original.crs)

    if not gdf_original.empty:
        if gdf_original.crs is not None and gdf_original.crs.to_string() != "EPSG:4326":
            logger.info("Converting from %s to EPSG:4326 for GeoJSON", gdf_original.crs)
            gdf_wgs84 = gdf_original.to_crs(epsg=4326)
        else:
            logger.info("Already in EPSG:4326 or no CRS defined")
            gdf_wgs84 = gdf_original
            if gdf_wgs84.crs is None:
                gdf_wgs84.crs = "EPSG:4326"
    else:
        gdf_wgs84 = gdf_original
        if gdf_wgs84.crs is None:
            gdf_wgs84.crs = "EPSG:4326"

    geojson_path, shp_zip_path = save_geojson_and_shapefile(
        gdf_wgs84.geometry.tolist(),
        "EPSG:4326",
        run_dir,
    )
    logger.info("Saved GeoJSON in EPSG:4326 at %s", geojson_path)

    overlay_filename = f"overlay_{run_id}.png"
    overlay_path = os.path.join("outputs", overlay_filename)
    if binary is not None:
        mask_img = (binary * 255).astype(np.uint8)
        rgba_arr = np.zeros((mask_img.shape[0], mask_img.shape[1], 4), dtype=np.uint8)
        rgba_arr[..., 0] = 255
        rgba_arr[..., 3] = mask_img
        Image.fromarray(rgba_arr).save(overlay_path, format="PNG")
    else:
        save_downsampled_overlay_png(preds, coords, threshold, size, overlay_path, max_side=8192)

    overlay_bounds_wgs84 = [[0.0, 0.0], [0.0, 0.0]]
    total_area_original = 0.0
    avg_area_original = 0.0

    if not gdf_wgs84.empty:
        try:
            bounds = gdf_wgs84.total_bounds
            if len(bounds) == 4 and all(math.isfinite(b) for b in bounds):
                overlay_bounds_wgs84 = [
                    [float(bounds[1]), float(bounds[0])],
                    [float(bounds[3]), float(bounds[2])],
                ]
                logger.info("Overlay bounds: %s", overlay_bounds_wgs84)

            if gdf_original.crs is not None and gdf_original.crs.is_projected:
                logger.info("Using original projected CRS for area calculations")
                total_area_original = float(gdf_original.geometry.area.sum())
                avg_area_original = float(gdf_original.geometry.area.mean())
            else:
                logger.info("Projecting to UTM for area calculations")
                centroid = gdf_wgs84.unary_union.centroid
                lon, lat = centroid.x, centroid.y
                utm_zone = int((lon + 180) / 6) + 1
                epsg_code = 32600 + utm_zone if lat >= 0 else 32700 + utm_zone

                try:
                    gdf_projected = gdf_wgs84.to_crs(epsg=epsg_code)
                    total_area_original = float(gdf_projected.geometry.area.sum())
                    avg_area_original = float(gdf_projected.geometry.area.mean())
                    logger.info("Areas calculated in EPSG:%s", epsg_code)
                except Exception:
                    import warnings

                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore")
                        total_area_original = float(gdf_wgs84.geometry.area.sum())
                        avg_area_original = float(gdf_wgs84.geometry.area.mean())
                        logger.warning("Using WGS84 for areas (less accurate)")

        except Exception as e:
            logger.error(" Failed to compute bounds/stats: %s", e, exc_info=True)

    if overlay_bounds_wgs84 == [[0.0, 0.0], [0.0, 0.0]]:
        fb = raster_extent_bounds_wgs84(img_crs, geo_bbox)
        if fb:
            overlay_bounds_wgs84 = fb
            logger.info("No (or empty) detection bounds; using GeoTIFF extent for map overlay_bounds")

    geojson_url = f"/outputs/{run_id}/buildings.geojson"
    shapefile_url = f"/outputs/{run_id}/building_polygons.zip"
    overlay_url = f"/outputs/{overlay_filename}"

    write_unet_manifest(
        run_id,
        model_name=model_name or "",
        source_filename=source_filename or "",
        inference_threshold=threshold,
        geojson_path=os.path.abspath(geojson_path),
        shapefile_path=os.path.abspath(shp_zip_path),
        overlay_path=os.path.abspath(overlay_path),
        confidence_npz_path=os.path.abspath(saved_npz) if saved_npz else None,
        meta_json_path=os.path.abspath(saved_meta) if saved_meta else None,
        width=int(size[0]),
        height=int(size[1]),
    )

    linked_lulc = False
    if (lulc_prediction_id or "").strip():
        try:
            linked_lulc = attach_building_detection_to_lulc(
                (lulc_prediction_id or "").strip(),
                task="unet",
                od_run_id=run_id,
                inference_threshold=float(threshold),
                geojson_abs_path=os.path.abspath(geojson_path),
                full_geojson_abs_path=None,
                confidence_npz_abs_path=os.path.abspath(saved_npz)
                if saved_npz and os.path.isfile(saved_npz)
                else None,
                model_name=model_name or "",
            )
        except Exception as e:
            logger.warning("UNet LULC attach skipped: %s", e)

    return {
        "task": "unet",
        "count": int(len(gdf_wgs84)),
        "total_area": float(total_area_original) if math.isfinite(total_area_original) else 0.0,
        "average_area": float(avg_area_original) if math.isfinite(avg_area_original) else 0.0,
        "geojson_url": geojson_url,
        "shapefile_url": shapefile_url,
        "overlay_url": overlay_url,
        "overlay_bounds": overlay_bounds_wgs84,
        "width": int(size[0]),
        "height": int(size[1]),
        "crs": "EPSG:4326",
        "run_id": run_id,
        "inference_threshold": threshold,
        "confidence_bundle_saved": bool(saved_npz and os.path.isfile(saved_npz)),
        "lulc_prediction_linked": linked_lulc,
    }


def _unet_streaming_events(
    run_id: str,
    raster_path: str,
    model_name: str,
    threshold: float,
    stream_chip_interval: int,
    lulc_prediction_id: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    stream_chip_interval = max(1, min(int(stream_chip_interval), 200))
    reset_unet_progress()
    update_progress(phase="loading_model", current_step="Preparing image...", status="running")
    try:
        resolved_model_path = resolve_unet_model_path(model_name)
        water_smp = is_water_smp_model(model_name)
        water_body_mode = is_water_body_model(model_name)
        sar_mode = is_sar_flood_model(model_name, resolved_model_path) and not (water_smp or water_body_mode)

        update_progress(current_step="Reading raster...")
        img_crs, transform_raster, geo_bbox = None, None, None
        pil_img = None
        hwc4 = None
        if raster_path.lower().endswith((".tif", ".tiff")):
            with rasterio.open(raster_path) as src:
                img_crs, transform_raster = src.crs, src.transform
                geo_bbox = (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top)
                if water_smp:
                    hwc4 = raster_to_hwc4_water(src)
                    size = (int(src.width), int(src.height))
                elif water_body_mode:
                    try:
                        pil_img = Image.open(raster_path).convert("RGB")
                    except Exception:
                        pil_img = raster_to_pil_rgb(src)
                    size = pil_img.size
                elif sar_mode:
                    pil_img = raster_to_pil_l_sar(src)
                    size = pil_img.size
                else:
                    pil_img = raster_to_pil_rgb(src)
                    size = pil_img.size
        else:
            if water_smp:
                pil_img = Image.open(raster_path).convert("RGB")
                hwc4 = pil_rgb_to_hwc4(pil_img)
                size = pil_img.size
            elif water_body_mode:
                pil_img = Image.open(raster_path).convert("RGB")
                size = pil_img.size
            else:
                pil_img = (
                    Image.open(raster_path).convert("L")
                    if sar_mode
                    else Image.open(raster_path).convert("RGB")
                )
                size = pil_img.size

        infer_th = float(threshold)
        if water_body_mode and abs(infer_th - 0.5) < 1e-9:
            infer_th = WATER_BODY_DEFAULT_THRESHOLD
        threshold = infer_th

        update_progress(current_step="Creating tiles...")
        if water_smp:
            assert hwc4 is not None
            chips, coords = create_chips_hwc4(hwc4, chip_size=1024, overlap=32)
        elif water_body_mode:
            assert pil_img is not None
            _wb_ov = _water_body_chip_overlap_px()
            chips, coords = create_chips(
                pil_img, chip_size=WATER_BODY_INFER_SIZE, overlap=_wb_ov
            )
            logger.info(
                "Water body: %s tiles @ %s² px, overlap=%s px (fused preview + streaming)",
                len(chips),
                WATER_BODY_INFER_SIZE,
                _wb_ov,
            )
        else:
            assert pil_img is not None
            chips, coords = create_chips(pil_img, chip_size=1024, overlap=32)

        update_progress(current_step=f"Loading model: {model_name}...")
        model = load_model_by_name(model_name)
        use_imagenet_rgb = _preprocess_uses_imagenet.get(resolved_model_path, False)

        total_chips = len(chips)
        npx = int(size[0]) * int(size[1])
        use_fused_preview = _stream_use_fused_preview(npx)
        run_full: Optional[np.ndarray] = None
        run_counts: Optional[np.ndarray] = None
        stream_preview_ds = _unet_stream_preview_downsample()
        if use_fused_preview:
            run_full, run_counts = _reassemble_running_init(size)
            fusion = _unet_overlap_fusion_mode()
            fused_bufs = 1 if fusion == "max" else 2
            logger.info(
                "[predict-stream] Fused raster preview (overlap=%s, same as final output, no chip-grid seams); "
                "~%.1f Mpix, +~%.0f MB RAM — set UNET_STREAM_FUSED_PREVIEW=0 to use chip-wise preview; "
                "UNET_OVERLAP_FUSION=mean restores legacy averaging (can cause seam gaps)",
                fusion,
                npx / 1e6,
                fused_bufs * npx * 4 / (1024 * 1024),
            )
            if stream_preview_ds > 1:
                logger.info(
                    "[predict-stream] Preview downsample=%sx (UNET_STREAM_PREVIEW_DOWNSAMPLE) — "
                    "saved buildings.geojson uses the same",
                    stream_preview_ds,
                )
        extent_bounds = raster_extent_bounds_wgs84(img_crs, geo_bbox)
        logger.info(
            "[predict-stream] Detecting: %s chips (UNet); incremental map update every %s chips",
            total_chips,
            stream_chip_interval,
        )
        yield {
            "type": "start",
            "overlay_bounds": extent_bounds,
            "width": int(size[0]),
            "height": int(size[1]),
            "total_chips": total_chips,
            "crs": "EPSG:4326",
            "stream_interval": stream_chip_interval,
            "message": f"Detecting: {total_chips} chips — map preview every {stream_chip_interval}",
        }

        preds = []
        _infer_t0 = time.time()
        update_progress(
            phase="inference",
            current_step="Starting tile inference...",
            total_chips=total_chips,
            processed_chips=0,
            status="running",
        )

        last_yielded = 0
        for i, chip in enumerate(chips, 1):
            if water_body_mode:
                pred = _water_body_forward_chip_prob(model, chip)
            elif water_smp:
                tensor = preprocess_water_chip_hwc(chip)
                pred = predict_mask(model, tensor, resolved_model_path)
            elif sar_mode:
                tensor = preprocess_pil_chip_sar(chip, DEVICE, add_batch_dim=True)
                pred = predict_mask(model, tensor, resolved_model_path)
            else:
                tensor = preprocess_image_pil_for_model(chip, use_imagenet=use_imagenet_rgb)
                pred = predict_mask(model, tensor, resolved_model_path)
            preds.append(pred)
            if use_fused_preview and run_full is not None:
                _reassemble_running_add(run_full, run_counts, pred, coords[i - 1])
            elapsed = time.time() - _infer_t0
            rate = i / elapsed if elapsed > 0 else 0.0
            remaining = total_chips - i
            eta = remaining / rate if rate > 0 else None
            update_progress(
                processed_chips=i,
                current_step=f"Tile {i}/{total_chips}",
                eta_seconds=round(eta, 1) if eta is not None else 0,
            )
            while last_yielded + stream_chip_interval <= i:
                last_yielded += stream_chip_interval
                if use_fused_preview and run_full is not None:
                    gj = _unet_fused_preview_geojson(
                        run_full,
                        run_counts,
                        threshold,
                        size,
                        transform_raster,
                        img_crs,
                        preview_downsample=stream_preview_ds,
                    )
                else:
                    gj = _unet_chips_preview_geojson(
                        preds,
                        coords[: len(preds)],
                        threshold,
                        size,
                        transform_raster,
                        img_crs,
                    )
                nfeat = len(gj.get("features", []) or [])
                msg = (
                    f"Chips {last_yielded}/{total_chips}: merged preview → map "
                    f"({nfeat} features)"
                )
                logger.info("[predict-stream] %s", msg)
                yield {
                    "type": "progress",
                    "geojson": gj,
                    "chips_processed": last_yielded,
                    "total_chips": total_chips,
                    "message": msg,
                }

        if total_chips > last_yielded:
            last_yielded = total_chips
            if use_fused_preview and run_full is not None:
                gj = _unet_fused_preview_geojson(
                    run_full,
                    run_counts,
                    threshold,
                    size,
                    transform_raster,
                    img_crs,
                    preview_downsample=stream_preview_ds,
                )
            else:
                gj = _unet_chips_preview_geojson(
                    preds,
                    coords,
                    threshold,
                    size,
                    transform_raster,
                    img_crs,
                )
            nfeat = len(gj.get("features", []) or [])
            msg = (
                f"Chips {total_chips}/{total_chips}: final preview chunk → map "
                f"({nfeat} features)"
            )
            logger.info("[predict-stream] %s", msg)
            yield {
                "type": "progress",
                "geojson": gj,
                "chips_processed": total_chips,
                "total_chips": total_chips,
                "message": msg,
            }

        update_progress(
            phase="post_processing",
            current_step="Vectorizing detections and saving outputs...",
            processed_chips=total_chips,
            eta_seconds=0,
            status="running",
        )

        response = _unet_post_chips_response_dict(
            run_id,
            preds,
            coords,
            size,
            img_crs,
            transform_raster,
            threshold,
            geo_bbox,
            model_name=model_name,
            source_filename=os.path.basename(raster_path) if raster_path else None,
            lulc_prediction_id=lulc_prediction_id,
        )
        logger.info("Response prepared with %s detections", response["count"])
        logger.info("Overlay bounds: %s", response["overlay_bounds"])

        update_progress(
            phase="done",
            current_step="Complete",
            processed_chips=total_chips,
            eta_seconds=0,
            status="done",
        )
        yield {"type": "done", **response}
    except Exception as e:
        logger.exception("UNet streaming failed")
        update_progress(phase="error", current_step=str(e), status="error")
        yield {"type": "error", "error": str(e)}


def _cleanup_unet_paths(paths: List[str]) -> None:
    for p in paths:
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


def _unet_predict_sync(
    run_id: str,
    tmp_path: str,
    model_name: str,
    threshold: float,
    roi_raw: str,
    roi_full_bounds_swne_raw: str,
    paths_to_delete: List[str],
    lulc_prediction_id: Optional[str] = None,
) -> JSONResponse:
    """Runs the full UNet pipeline synchronously in a worker thread so the async server can answer /progress."""
    reset_unet_progress()
    update_progress(phase="loading_model", current_step="Preparing image...", status="running")
    bounds_swne = parse_roi_full_bounds_swne((roi_full_bounds_swne_raw or "").strip())
    try:
        resolved_model_path = resolve_unet_model_path(model_name)
        water_smp = is_water_smp_model(model_name)
        water_body_mode = is_water_body_model(model_name)
        sar_mode = is_sar_flood_model(model_name, resolved_model_path) and not (water_smp or water_body_mode)

        raster_path = tmp_path
        if roi_raw:
            if not tmp_path.lower().endswith((".tif", ".tiff")):
                raise HTTPException(
                    status_code=400,
                    detail="ROI polygon is only supported for GeoTIFF uploads.",
                )
            try:
                geom = geometry_polygon_from_roi_geojson(roi_raw)
                crop_path = unet_roi_geotiff_with_fallbacks(
                    tmp_path, geom, bounds_swne, sar_mode, prefer_four_bands=water_smp
                )
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid roi_geojson (not valid JSON)")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            paths_to_delete.append(crop_path)
            raster_path = crop_path
            logger.info("UNet: using ROI-cropped GeoTIFF for inference (%s)", raster_path)

        update_progress(current_step="Reading raster...")
        img_crs, transform_raster, geo_bbox = None, None, None
        pil_img = None
        hwc4 = None
        if raster_path.lower().endswith((".tif", ".tiff")):
            with rasterio.open(raster_path) as src:
                img_crs, transform_raster = src.crs, src.transform
                geo_bbox = (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top)
                if water_smp:
                    hwc4 = raster_to_hwc4_water(src)
                    size = (int(src.width), int(src.height))
                elif water_body_mode:
                    try:
                        pil_img = Image.open(raster_path).convert("RGB")
                    except Exception:
                        pil_img = raster_to_pil_rgb(src)
                    size = pil_img.size
                elif sar_mode:
                    pil_img = raster_to_pil_l_sar(src)
                    size = pil_img.size
                else:
                    pil_img = raster_to_pil_rgb(src)
                    size = pil_img.size
        else:
            if water_smp:
                pil_img = Image.open(tmp_path).convert("RGB")
                hwc4 = pil_rgb_to_hwc4(pil_img)
                size = pil_img.size
            elif water_body_mode:
                pil_img = Image.open(tmp_path).convert("RGB")
                size = pil_img.size
            else:
                pil_img = (
                    Image.open(tmp_path).convert("L")
                    if sar_mode
                    else Image.open(tmp_path).convert("RGB")
                )
                size = pil_img.size

        infer_th = float(threshold)
        if water_body_mode and abs(infer_th - 0.5) < 1e-9:
            infer_th = WATER_BODY_DEFAULT_THRESHOLD
        threshold = infer_th

        if sar_mode:
            logger.info("SAR flood mode: grayscale / log preprocessing, UNet chips 1024→256")
        if water_smp:
            logger.info(
                "Water SMP mode: 4-channel ResNet50 UNet, %s² chips → %s² infer (notebook-aligned)",
                1024,
                WATER_SMP_INFER_SIZE,
            )
        if water_body_mode:
            logger.info(
                "Water body mode: %s² tiling + overlap fusion + streaming (same tensor path per tile)",
                WATER_BODY_INFER_SIZE,
            )

        logger.info("--- CHIP CREATION PHASE ---")
        update_progress(current_step="Creating tiles...")
        if water_smp:
            assert hwc4 is not None
            chips, coords = create_chips_hwc4(hwc4, chip_size=1024, overlap=32)
        elif water_body_mode:
            assert pil_img is not None
            _wb_ov = _water_body_chip_overlap_px()
            chips, coords = create_chips(
                pil_img, chip_size=WATER_BODY_INFER_SIZE, overlap=_wb_ov
            )
            logger.info(
                "Water body: %s tiles @ %s² px, overlap=%s px",
                len(chips),
                WATER_BODY_INFER_SIZE,
                _wb_ov,
            )
        else:
            assert pil_img is not None
            chips, coords = create_chips(pil_img, chip_size=1024, overlap=32)

        logger.info("--- MODEL LOADING PHASE ---")
        update_progress(current_step=f"Loading model: {model_name}...")
        logger.info(f"Loading model: {model_name}")
        model = load_model_by_name(model_name)
        use_imagenet_rgb = _preprocess_uses_imagenet.get(resolved_model_path, False)
        logger.info(f"Model loaded successfully on device: {DEVICE}")

        logger.info("--- CHIP PREDICTION PHASE ---")
        preds = []
        total_chips = len(chips)
        _infer_t0 = time.time()
        update_progress(
            phase="inference",
            current_step="Starting tile inference...",
            total_chips=total_chips,
            processed_chips=0,
            status="running",
        )

        for i, chip in enumerate(chips, 1):
            logger.info(f"Processing chip {i}/{total_chips} (coordinates: {coords[i-1]})")
            if water_body_mode:
                pred = _water_body_forward_chip_prob(model, chip)
            elif water_smp:
                tensor = preprocess_water_chip_hwc(chip)
                pred = predict_mask(model, tensor, resolved_model_path)
            elif sar_mode:
                tensor = preprocess_pil_chip_sar(chip, DEVICE, add_batch_dim=True)
                pred = predict_mask(model, tensor, resolved_model_path)
            else:
                tensor = preprocess_image_pil_for_model(chip, use_imagenet=use_imagenet_rgb)
                pred = predict_mask(model, tensor, resolved_model_path)
            preds.append(pred)
            pred_min, pred_max, pred_mean = pred.min(), pred.max(), pred.mean()
            logger.info(f"Chip {i} prediction stats - Min: {pred_min:.4f}, Max: {pred_max:.4f}, Mean: {pred_mean:.4f}")
            elapsed = time.time() - _infer_t0
            rate = i / elapsed if elapsed > 0 else 0.0
            remaining = total_chips - i
            eta = remaining / rate if rate > 0 else None
            update_progress(
                processed_chips=i,
                current_step=f"Tile {i}/{total_chips}",
                eta_seconds=round(eta, 1) if eta is not None else 0,
            )

        logger.info(f"Completed predictions for all {total_chips} chips")
        update_progress(
            phase="post_processing",
            current_step="Vectorizing detections and saving outputs...",
            processed_chips=total_chips,
            eta_seconds=0,
            status="running",
        )

        response = _unet_post_chips_response_dict(
            run_id,
            preds,
            coords,
            size,
            img_crs,
            transform_raster,
            threshold,
            geo_bbox,
            model_name=model_name,
            source_filename=os.path.basename(tmp_path) if tmp_path else None,
            lulc_prediction_id=lulc_prediction_id,
        )
        logger.info(f"✅ Response prepared with {response['count']} detections")
        logger.info(f"Overlay bounds: {response['overlay_bounds']}")

        update_progress(
            phase="done",
            current_step="Complete",
            processed_chips=total_chips,
            eta_seconds=0,
            status="done",
        )
        return JSONResponse(content=response)

    except HTTPException as he:
        update_progress(phase="error", current_step=str(he.detail), status="error")
        raise
    except Exception as e:
        logger.exception("predict failed")
        update_progress(phase="error", current_step=str(e), status="error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict")
async def predict(
    image: UploadFile = File(...),
    model_name: str = Query(...),
    threshold: float = Query(0.5, ge=0, le=1),
    roi_geojson: Optional[str] = Form(None),
    roi_full_bounds_swne: Optional[str] = Form(None),
    lulc_prediction_id: Optional[str] = Form(None),
):
    run_id = str(uuid.uuid4())
    logger.info(f"Starting prediction {run_id} for {image.filename}")
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(image.filename or ".tif")[1])
    os.close(tmp_fd)
    paths_to_delete: List[str] = [tmp_path]
    try:
        with open(tmp_path, "wb") as f:
            f.write(await image.read())
        return await asyncio.to_thread(
            _unet_predict_sync,
            run_id,
            tmp_path,
            model_name,
            threshold,
            (roi_geojson or "").strip(),
            (roi_full_bounds_swne or "").strip(),
            paths_to_delete,
            (lulc_prediction_id or "").strip() or None,
        )
    finally:
        for p in paths_to_delete:
            try:
                if p and os.path.isfile(p):
                    os.remove(p)
            except OSError:
                pass


@app.post("/predict-stream")
async def predict_stream(
    image: UploadFile = File(...),
    model_name: str = Query(...),
    threshold: float = Query(0.5, ge=0, le=1),
    stream_chip_interval: int = Query(5, ge=1, le=200),
    roi_geojson: Optional[str] = Form(None),
    roi_full_bounds_swne: Optional[str] = Form(None),
    lulc_prediction_id: Optional[str] = Form(None),
):
    run_id = str(uuid.uuid4())
    logger.info("Starting streaming prediction %s for %s", run_id, image.filename)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(image.filename or ".tif")[1])
    os.close(tmp_fd)
    paths_to_delete: List[str] = [tmp_path]
    try:
        with open(tmp_path, "wb") as f:
            f.write(await image.read())
    except Exception as e:
        _cleanup_unet_paths(paths_to_delete)
        raise HTTPException(status_code=500, detail=str(e))

    roi_raw = (roi_geojson or "").strip()
    bounds_swne = parse_roi_full_bounds_swne((roi_full_bounds_swne or "").strip())
    raster_path = tmp_path
    if roi_raw:
        if not tmp_path.lower().endswith((".tif", ".tiff")):
            _cleanup_unet_paths(paths_to_delete)
            raise HTTPException(
                status_code=400,
                detail="ROI polygon is only supported for GeoTIFF uploads.",
            )
        try:
            resolved_model_path = resolve_unet_model_path(model_name)
            water_smp = is_water_smp_model(model_name)
            water_body_mode = is_water_body_model(model_name)
            sar_mode = is_sar_flood_model(model_name, resolved_model_path) and not (
                water_smp or water_body_mode
            )
            geom = geometry_polygon_from_roi_geojson(roi_raw)
            crop_path = unet_roi_geotiff_with_fallbacks(
                tmp_path, geom, bounds_swne, sar_mode, prefer_four_bands=water_smp
            )
        except json.JSONDecodeError:
            _cleanup_unet_paths(paths_to_delete)
            raise HTTPException(status_code=400, detail="Invalid roi_geojson (not valid JSON)")
        except ValueError as e:
            _cleanup_unet_paths(paths_to_delete)
            raise HTTPException(status_code=400, detail=str(e))
        paths_to_delete.append(crop_path)
        raster_path = crop_path

    lulc_pid = (lulc_prediction_id or "").strip() or None

    def sse_body():
        try:
            for ev in _unet_streaming_events(
                run_id,
                raster_path,
                model_name,
                threshold,
                stream_chip_interval,
                lulc_prediction_id=lulc_pid,
            ):
                yield "data: " + sse_json_dumps(ev) + "\n\n"
        finally:
            _cleanup_unet_paths(paths_to_delete)

    return StreamingResponse(
        sse_body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Demo GeoTIFF: prefer models/samples/demo_ortho, then legacy Eg_files/
_DEMO_ORTHO_FILENAMES = ("TPG_22-23_ortho.tif.tif", "TPG_22-23_ortho.tif")


def _resolve_demo_ortho_path() -> Optional[str]:
    for root in DEMO_ORTHO_SEARCH_DIRS:
        for name in _DEMO_ORTHO_FILENAMES:
            p = os.path.join(root, name)
            if os.path.isfile(p):
                return p
    return None


@app.get("/demo-sample-ortho")
def serve_demo_building_ortho():
    """Serves bundled sample ortho for demos (Object Detection page)."""
    path = _resolve_demo_ortho_path()
    if not path:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Demo ortho not found. Add one of {_DEMO_ORTHO_FILENAMES} under "
                f"{sample_dir('demo_ortho')} or {legacy_eg_files_dir()}"
            ),
        )
    return FileResponse(
        path,
        media_type="image/tiff",
        filename=os.path.basename(path),
    )


def _artifact_path_to_outputs_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    p = str(path).replace("\\", "/")
    if "/outputs/" in p:
        return p[p.index("/outputs/") :]
    return None


@app.get("/runs")
def list_saved_runs(limit: int = Query(100, ge=1, le=500)):
    manifests = list_manifests(task="unet", limit=limit)
    runs: List[Dict[str, Any]] = []
    for m in manifests:
        run_id = m.get("run_id")
        if not run_id:
            continue
        art = m.get("artifacts") or {}
        runs.append(
            {
                "run_id": run_id,
                "task": "unet",
                "created_at": m.get("created_at"),
                "model_name": m.get("model_name"),
                "source_filename": m.get("source_filename"),
                "inference_threshold": m.get("inference_threshold"),
                "width": m.get("width"),
                "height": m.get("height"),
                "geojson_url": _artifact_path_to_outputs_url(art.get("geojson")),
                "shapefile_url": _artifact_path_to_outputs_url(art.get("shapefile")),
                "overlay_url": _artifact_path_to_outputs_url(art.get("overlay")),
                "confidence_bundle_saved": bool(art.get("confidence_npz")),
            }
        )
    return {"runs": runs}


@app.get("/runs/{run_id}")
def get_saved_run(run_id: str):
    if not archive_validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    m = read_manifest(run_id)
    if not m or m.get("task") != "unet":
        raise HTTPException(status_code=404, detail="Run not found")
    art = m.get("artifacts") or {}
    return {
        "run_id": run_id,
        "task": "unet",
        "created_at": m.get("created_at"),
        "model_name": m.get("model_name"),
        "source_filename": m.get("source_filename"),
        "inference_threshold": m.get("inference_threshold"),
        "width": m.get("width"),
        "height": m.get("height"),
        "geojson_url": _artifact_path_to_outputs_url(art.get("geojson")),
        "shapefile_url": _artifact_path_to_outputs_url(art.get("shapefile")),
        "overlay_url": _artifact_path_to_outputs_url(art.get("overlay")),
        "confidence_bundle_saved": bool(art.get("confidence_npz")),
    }


def _unet_vectorize_context(run_id: str) -> Tuple[np.ndarray, dict, Any, Optional[Affine], Tuple[int, int]]:
    """Load confidence + meta for fused-path re-vectorization (GET /geojson and post-process lab)."""
    if not archive_validate_run_id(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    run_dir = os.path.join("outputs", run_id)
    if not os.path.isdir(run_dir):
        raise HTTPException(status_code=404, detail="Run not found")
    conf, meta = _load_unet_conf_and_meta(run_id)
    if conf is None or meta is None:
        raise HTTPException(
            status_code=404,
            detail="No saved confidence grid for this run (inference may have failed to fuse/save).",
        )
    try:
        from rasterio.crs import CRS

        img_crs = CRS.from_string(meta["crs"]) if meta.get("crs") else None
    except Exception:
        img_crs = None
    tr = meta.get("transform")
    transform_raster = Affine(*tr) if isinstance(tr, list) and len(tr) >= 6 else None
    size = (int(meta.get("width", conf.shape[1])), int(meta.get("height", conf.shape[0])))
    return conf, meta, img_crs, transform_raster, size


class UnetPostprocessLabBody(BaseModel):
    run_id: str
    task: str = "unet"
    inference_threshold: float = 0.5
    regularize_mode: Optional[str] = None
    regularize_tolerance: Optional[float] = None
    iou_threshold: Optional[float] = None
    seam_merge_gap: Optional[float] = None


def _unet_pp_lab_guard() -> None:
    if not ENABLE_POSTPROCESS_LAB:
        raise HTTPException(
            status_code=403,
            detail="Post-process lab is disabled (set ENABLE_POSTPROCESS_LAB=1).",
        )


@app.post("/postprocess/preview")
def unet_postprocess_preview(body: UnetPostprocessLabBody):
    """UNet post-process preview (no writes). Gated by ENABLE_POSTPROCESS_LAB."""
    _unet_pp_lab_guard()
    if (body.task or "unet").strip().lower() != "unet":
        raise HTTPException(status_code=400, detail="task must be unet")
    try:
        conf, meta, img_crs, transform_raster, size = _unet_vectorize_context(body.run_id)
    except HTTPException:
        raise
    pp = {
        k: v
        for k, v in (
            ("iou_threshold", body.iou_threshold),
            ("seam_merge_gap", body.seam_merge_gap),
            ("regularize_mode", body.regularize_mode),
            ("regularize_tolerance", body.regularize_tolerance),
        )
        if v is not None
    }
    gj = _unet_geojson_from_conf_threshold(
        conf,
        body.inference_threshold,
        size,
        img_crs,
        transform_raster,
        postprocess_kwargs=pp or None,
    )
    feats = gj.get("features") or []
    n = len(feats)
    total_area = 0.0
    if n:
        try:
            tdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
            if not tdf.empty and tdf.crs is not None and getattr(tdf.crs, "is_geographic", False):
                tdf = tdf.to_crs(tdf.estimate_utm_crs())
            total_area = float(tdf.geometry.area.sum()) if not tdf.empty else 0.0
        except Exception:
            total_area = 0.0
    return {"geojson": gj, "count": n, "total_area": total_area}


@app.post("/postprocess/apply")
def unet_postprocess_apply(body: UnetPostprocessLabBody):
    """Write post-processed buildings.geojson + shapefile for a UNet run (overlay unchanged)."""
    _unet_pp_lab_guard()
    if (body.task or "unet").strip().lower() != "unet":
        raise HTTPException(status_code=400, detail="task must be unet")
    try:
        conf, meta, img_crs, transform_raster, size = _unet_vectorize_context(body.run_id)
    except HTTPException:
        raise
    pp = {
        k: v
        for k, v in (
            ("iou_threshold", body.iou_threshold),
            ("seam_merge_gap", body.seam_merge_gap),
            ("regularize_mode", body.regularize_mode),
            ("regularize_tolerance", body.regularize_tolerance),
        )
        if v is not None
    }
    gj = _unet_geojson_from_conf_threshold(
        conf,
        body.inference_threshold,
        size,
        img_crs,
        transform_raster,
        postprocess_kwargs=pp or None,
    )
    run_dir = os.path.join("outputs", body.run_id)
    os.makedirs(run_dir, exist_ok=True)
    feats = gj.get("features") or []
    if not feats:
        polys: List = []
    else:
        tdf0 = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
        polys = tdf0.geometry.tolist()
    geojson_path, shp_zip_path = save_geojson_and_shapefile(polys, "EPSG:4326", run_dir)
    m = read_manifest(body.run_id) or {}
    art = m.get("artifacts") or {}
    write_unet_manifest(
        body.run_id,
        model_name=m.get("model_name") or "",
        source_filename=m.get("source_filename") or "",
        inference_threshold=float(body.inference_threshold),
        geojson_path=os.path.abspath(geojson_path),
        shapefile_path=os.path.abspath(shp_zip_path),
        overlay_path=art.get("overlay"),
        confidence_npz_path=art.get("confidence_npz"),
        meta_json_path=art.get("unet_run_meta"),
        width=int(m.get("width") or size[0]),
        height=int(m.get("height") or size[1]),
    )
    n = len(feats)
    total_area = 0.0
    if n:
        try:
            tdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
            if tdf.crs is not None and getattr(tdf.crs, "is_geographic", False):
                tdf = tdf.to_crs(tdf.estimate_utm_crs())
            total_area = float(tdf.geometry.area.sum())
        except Exception:
            pass
    return {
        "ok": True,
        "geojson": gj,
        "geojson_url": f"/outputs/{body.run_id}/buildings.geojson",
        "shapefile_url": f"/outputs/{body.run_id}/building_polygons.zip",
        "count": n,
        "total_area": total_area,
    }


@app.get("/runs/{run_id}/geojson")
def unet_geojson_at_threshold(
    run_id: str,
    threshold: float = Query(0.5, ge=0.0, le=1.0),
):
    """Re-vectorize from saved fused confidence grid without full re-inference."""
    try:
        conf, meta, img_crs, transform_raster, size = _unet_vectorize_context(run_id)
    except HTTPException:
        raise
    gj = _unet_geojson_from_conf_threshold(
        conf,
        threshold,
        size,
        img_crs,
        transform_raster,
    )
    return JSONResponse(content=gj)


@app.get("/download_geojson")
def download_geojson(run_id: str = Query(...)):
    path = os.path.join("outputs", run_id, "buildings.geojson")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="GeoJSON not found")
    return FileResponse(path, media_type="application/geo+json", filename="buildings.geojson")

@app.get("/download_shapefile")
def download_shapefile(run_id: str = Query(...)):
    path = os.path.join("outputs", run_id, "building_polygons.zip")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Shapefile not found")
    return FileResponse(path, media_type="application/zip", filename="building_polygons.zip")


app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

if __name__=="__main__":
    uvicorn.run("unetnew:app", host="0.0.0.0", port=8000)

# # uvicorn unetnew:app --host 0.0.0.0 --port 8000