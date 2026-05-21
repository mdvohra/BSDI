"""
ResUNet-A solar panel segmentation inference (GeoTIFF tiles).

Raster windows are read at SOLAR_TILE_SIZE (e.g. 1024); network input is fixed at 256×256.
"""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import List, Tuple

import cv2
import numpy as np
import rasterio.features
import torch
import torch.nn as nn
import torch.nn.functional as F
from affine import Affine
from PIL import Image

import albumentations as A
from albumentations.pytorch import ToTensorV2
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.validation import make_valid

logger = logging.getLogger(__name__)

SOLAR_INFERENCE_SIZE = 256
# Default mask threshold when the API does not pass one (same role as ``predict_mask(..., threshold=)``).
SOLAR_PANEL_BINARY_THRESHOLD = float(os.environ.get("SOLAR_PANEL_BINARY_THRESHOLD", "0.5"))

_solar_cache: dict[str, nn.Module] = {}
_solar_cache_lock = Lock()
MAX_CACHED_SOLAR_MODELS = 2


def prepare_rgb_uint8_for_solar(arr: np.ndarray) -> np.ndarray:
    """
    Convert a rasterio window ``(bands, h, w)`` to RGB uint8 ``(3, h, w)``.

    Your notebook uses PIL ``Image.open(...).convert('RGB')`` + Albumentations on the **whole**
    chip — roughly fixed scaling to 8-bit. The Mask R-CNN tile path used **per-tile min–max**
    stretch, which changes local contrast and often kills solar segmentation.

    Env ``SOLAR_PANEL_RGB_MODE``:
      - ``pilsafe`` (default): uint8 passthrough; uint16 → /65535×255; float → heuristics like [0,1].
      - ``per_tile_stretch``: legacy min–max per window (same idea as old detection tiling).
    """
    if arr.ndim != 3 or arr.shape[0] < 3:
        raise ValueError("solar expects at least 3 bands in shape (bands, h, w)")
    mode = os.environ.get("SOLAR_PANEL_RGB_MODE", "pilsafe").strip().lower()
    _, h, w = arr.shape
    a = np.ascontiguousarray(arr[:3])

    if a.dtype == np.uint8:
        return a

    if mode in ("per_tile_stretch", "minmax", "maskrcnn"):
        amin = float(a.min())
        amax = float(a.max())
        if amax <= amin:
            return np.zeros((3, h, w), dtype=np.uint8)
        out = (a.astype(np.float32) - amin) / (amax - amin) * 255.0
        return np.clip(out, 0, 255).astype(np.uint8)

    if a.dtype == np.uint16:
        return np.clip(a.astype(np.float32) / 65535.0 * 255.0, 0, 255).astype(np.uint8)

    f = a.astype(np.float32)
    fmax = float(f.max()) if f.size else 0.0
    if fmax <= 1.5:
        return np.clip(f * 255.0, 0, 255).astype(np.uint8)
    p99 = float(np.percentile(f, 99)) if f.size else fmax
    denom = max(p99, 1e-6)
    return np.clip(f / denom * 255.0, 0, 255).astype(np.uint8)


class ResidualConvBlock(nn.Module):
    def __init__(self, in_channels, out_channels, stride=1):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False)
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
    def __init__(self, in_channels, out_channels=256):
        super().__init__()
        self.conv1x1 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.conv3x3_1 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=6, dilation=6, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.conv3x3_2 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=12, dilation=12, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.conv3x3_3 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=18, dilation=18, bias=False),
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
        b, c, h, w = x.size()
        branch1 = self.conv1x1(x)
        branch2 = self.conv3x3_1(x)
        branch3 = self.conv3x3_2(x)
        branch4 = self.conv3x3_3(x)
        branch5 = self.global_avg_pool(x)
        branch5 = F.interpolate(branch5, size=(h, w), mode="bilinear", align_corners=True)
        out = torch.cat([branch1, branch2, branch3, branch4, branch5], dim=1)
        out = self.conv1x1_out(out)
        return out


class AttentionGate(nn.Module):
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
            g1 = F.interpolate(g1, size=x1.shape[2:], mode="bilinear", align_corners=True)
        psi = self.relu(g1 + x1)
        psi = self.psi(psi)
        return x * psi


class ResUNetA(nn.Module):
    def __init__(self, in_channels=3, out_channels=1, features=(64, 128, 256, 512, 1024)):
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
        self.attention4 = AttentionGate(F_g=features[4] // 2, F_l=features[3], F_int=features[3] // 2)
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
        self.final_conv = nn.Sequential(nn.Conv2d(features[0], out_channels, kernel_size=1), nn.Sigmoid())
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


def load_solar_model(weights_path: str, device: torch.device) -> nn.Module:
    key = os.path.abspath(weights_path)
    with _solar_cache_lock:
        if key in _solar_cache:
            return _solar_cache[key]
    if not os.path.isfile(weights_path):
        raise FileNotFoundError(f"Solar model not found: {weights_path}")
    model = ResUNetA(in_channels=3, out_channels=1).to(device)
    try:
        state = torch.load(weights_path, map_location=device, weights_only=True)
    except Exception:
        state = torch.load(weights_path, map_location=device)
    if isinstance(state, dict) and "model" in state:
        state = state["model"]
    if isinstance(state, dict):
        try:
            model.load_state_dict(state, strict=True)
        except Exception:
            model.load_state_dict(state, strict=False)
    else:
        raise ValueError("Unexpected checkpoint format for solar model")
    model.eval()
    with _solar_cache_lock:
        if len(_solar_cache) >= MAX_CACHED_SOLAR_MODELS:
            old = next(iter(_solar_cache))
            del _solar_cache[old]
        _solar_cache[key] = model
    logger.info("Loaded solar panel model %s", weights_path)
    return model


def preprocess_image(arr_rgb_uint8_chw: np.ndarray, img_size: int = SOLAR_INFERENCE_SIZE):
    """Same as standalone script ``preprocess_image``: PIL RGB + Resize + ToTensorV2."""
    hwc = np.transpose(np.ascontiguousarray(arr_rgb_uint8_chw), (1, 2, 0))
    image = Image.fromarray(hwc, mode="RGB")
    original_image = np.array(image)

    transform = A.Compose(
        [
            A.Resize(img_size, img_size),
            ToTensorV2(),
        ]
    )

    augmented = transform(image=original_image)
    tensor = augmented["image"].float().unsqueeze(0)
    return original_image, tensor


def predict_mask(
    model: nn.Module,
    image_tensor: torch.Tensor,
    device: torch.device,
    threshold: float = 0.5,
    sharpen: bool = True,
):
    """Same as standalone script ``predict_mask``."""
    sharpen_kernel = np.array(
        [
            [0, -1, 0],
            [-1, 10, -1],
            [0, -1, 0],
        ],
        dtype=np.float32,
    )

    image_tensor = image_tensor.to(device)

    with torch.no_grad():
        pred = model(image_tensor)
        pred_prob = pred[0, 0].cpu().numpy()

    pred_binary = (pred_prob > threshold).astype(np.uint8)

    if sharpen:
        pred_sharp = cv2.filter2D(pred_binary * 255, -1, sharpen_kernel)
    else:
        pred_sharp = None

    return pred_prob, pred_binary, pred_sharp


def _nearest_upsample_binary(bin_small: np.ndarray, height: int, width: int) -> np.ndarray:
    """Upsample 0/1 mask with nearest neighbor (matches treating script output as crisp mask then scaling)."""
    if bin_small.shape == (height, width):
        return bin_small.astype(np.uint8)
    try:
        import cv2

        return cv2.resize(bin_small.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST)
    except Exception:
        t = torch.from_numpy(bin_small.astype(np.float32))[None, None, ...]
        u = F.interpolate(t, size=(height, width), mode="nearest")[0, 0].numpy()
        return (u > 0.5).astype(np.uint8)


def _mean_prob_in_polygon(pred_hw: np.ndarray, poly: Polygon, height: int, width: int) -> float:
    """Mean probability under polygon footprint (pixel grid)."""
    try:
        if poly.is_empty:
            return 0.0
        g = poly if poly.is_valid else make_valid(poly)
        m = rasterio.features.rasterize([(g, 1)], out_shape=(height, width), fill=0, dtype=np.uint8)
        sel = m > 0
        if not np.any(sel):
            return 0.0
        return float(np.mean(pred_hw[sel]))
    except Exception:
        return 0.0


def extract_solar_instances_from_tile(
    arr_rgb_uint8: np.ndarray,
    model: nn.Module,
    device: torch.device,
    _unused_min_mean_prob: float,
    tile_transform: Affine,
    *,
    binary_threshold: float | None = None,
    sharpen: bool | None = None,
) -> List[Tuple[Polygon, float, int]]:
    """
    arr_rgb_uint8: (3, h, w) uint8
    Returns list of (polygon native CRS, mean_prob, label=1).

    Uses the same ``preprocess_image`` + ``predict_mask`` sequence as the standalone script, then
    nearest-upsamples the resulting binary mask to tile resolution for polygonization (only extra
    step vs saving a 256 PNG). ``_unused_min_mean_prob`` is kept for call-site compatibility.
    """
    _, h, w = arr_rgb_uint8.shape
    _original_image, tensor = preprocess_image(arr_rgb_uint8, img_size=SOLAR_INFERENCE_SIZE)

    bt = float(binary_threshold if binary_threshold is not None else SOLAR_PANEL_BINARY_THRESHOLD)

    if sharpen is not None:
        do_sharpen = sharpen
    else:
        _e = os.environ.get("SOLAR_PANEL_SHARPEN", "1").strip().lower()
        do_sharpen = _e not in ("0", "false", "no", "off")

    pred_prob, pred_binary, pred_sharp = predict_mask(model, tensor, device, threshold=bt, sharpen=do_sharpen)

    if pred_sharp is not None:
        bin_small = (pred_sharp > 127).astype(np.uint8)
    else:
        bin_small = pred_binary

    bin_mask = _nearest_upsample_binary(bin_small, h, w)

    pred_full_t = torch.from_numpy(pred_prob.astype(np.float32)).unsqueeze(0).unsqueeze(0)
    pred_full = F.interpolate(pred_full_t, size=(h, w), mode="bilinear", align_corners=False)[0, 0].numpy()

    out: List[Tuple[Polygon, float, int]] = []
    for geom, val in rasterio.features.shapes(bin_mask, transform=tile_transform):
        if float(val) < 0.5:
            continue
        try:
            geom_s = shape(geom)
            if not geom_s.is_valid:
                geom_s = make_valid(geom_s)
            polys: List[Polygon] = []
            if isinstance(geom_s, Polygon) and not geom_s.is_empty:
                polys.append(geom_s)
            elif isinstance(geom_s, MultiPolygon):
                polys.extend(g for g in geom_s.geoms if isinstance(g, Polygon) and not g.is_empty)
            for poly in polys:
                if poly.area <= 0:
                    continue
                sc = _mean_prob_in_polygon(pred_full, poly, h, w)
                out.append((poly, float(sc), 1))
        except Exception:
            continue
    return out
