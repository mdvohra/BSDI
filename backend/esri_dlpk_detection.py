"""
Esri deep-learning package style exports: .emd (JSON) + flat .pth for torchvision maskrcnn_resnet50_fpn.

Discovery: subdirectories under models/artifacts/esri/<model_id>/ with matching .emd + .pth basename.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from torchvision.models.detection import maskrcnn_resnet50_fpn
from torchvision.models.detection.transform import GeneralizedRCNNTransform

from model_paths import artifact_dir, ensure_dir

_esri_lock = threading.Lock()
_esri_model_cache: Dict[str, torch.nn.Module] = {}
_esri_emd_cache: Dict[str, Dict[str, Any]] = {}
_esri_overrides_cache: Dict[str, Dict[str, Any]] = {}
_MAX_CACHED_ESRI = 2


def esri_models_root() -> str:
    override = os.environ.get("ESRI_MODELS_ROOT", "").strip()
    if override:
        return os.path.normpath(override)
    root = artifact_dir("esri")
    ensure_dir(root)
    return root


def _list_subdirs(path: str) -> List[str]:
    if not os.path.isdir(path):
        return []
    out = []
    for name in sorted(os.listdir(path)):
        p = os.path.join(path, name)
        if os.path.isdir(p) and not name.startswith("."):
            out.append(name)
    return out


def _find_emd_pth_pair(model_dir: str) -> Tuple[str, str]:
    """Return (emd_path, pth_path) with matching basename."""
    emds = [f for f in os.listdir(model_dir) if f.lower().endswith(".emd")]
    pths = [f for f in os.listdir(model_dir) if f.lower().endswith((".pth", ".pt"))]
    pairs: List[Tuple[str, str]] = []
    for e in emds:
        base = os.path.splitext(e)[0]
        for pt in pths:
            if os.path.splitext(pt)[0] == base:
                pairs.append((os.path.join(model_dir, e), os.path.join(model_dir, pt)))
    if len(pairs) == 1:
        return pairs[0][0], pairs[0][1]
    if not pairs:
        raise FileNotFoundError(f"No matching .emd/.pth pair in {model_dir}")
    bases = [os.path.basename(a) for a, _ in pairs]
    raise FileNotFoundError(f"Multiple .emd/.pth basenames in {model_dir}: {bases}")


def list_esri_model_ids() -> List[str]:
    return _list_subdirs(esri_models_root())


def resolve_esri_model_dir(model_id: str) -> str:
    model_id = os.path.basename((model_id or "").strip())
    if not model_id or model_id in (".", ".."):
        raise FileNotFoundError("Invalid Esri model id")
    d = os.path.join(esri_models_root(), model_id)
    if not os.path.isdir(d):
        raise FileNotFoundError(f"Esri model folder not found: {model_id}")
    _find_emd_pth_pair(d)
    return d


def is_esri_model_name(model_name: str) -> bool:
    name = (model_name or "").strip()
    if not name or "/" in name or "\\" in name:
        return False
    if name.lower().endswith((".pth", ".pt")):
        return False
    d = os.path.join(esri_models_root(), os.path.basename(name))
    if not os.path.isdir(d):
        return False
    try:
        _find_emd_pth_pair(d)
        return True
    except FileNotFoundError:
        return False


def load_inference_overrides(model_dir: str) -> Dict[str, Any]:
    with _esri_lock:
        if model_dir in _esri_overrides_cache:
            return dict(_esri_overrides_cache[model_dir])
    path = os.path.join(model_dir, "inference_overrides.json")
    data: Dict[str, Any] = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    with _esri_lock:
        _esri_overrides_cache[model_dir] = dict(data)
    return dict(data)


def load_emd(model_dir: str) -> Dict[str, Any]:
    with _esri_lock:
        if model_dir in _esri_emd_cache:
            return dict(_esri_emd_cache[model_dir])
    emd_path, _ = _find_emd_pth_pair(model_dir)
    with open(emd_path, encoding="utf-8") as f:
        emd = json.load(f)
    with _esri_lock:
        _esri_emd_cache[model_dir] = dict(emd)
    return dict(emd)


def apply_scaled_norm_default(overrides: Dict[str, Any]) -> bool:
    if "apply_scaled_norm" in overrides:
        return bool(overrides["apply_scaled_norm"])
    env = os.environ.get("ESRI_APPLY_SCALED_NORM_DEFAULT", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    return True


@dataclass
class EsriExportConfig:
    emd: Dict[str, Any]
    resize_to: int
    extract_bands: List[int]
    num_classes: int
    apply_scaled_norm: bool


def parse_export_config(emd: Dict[str, Any], overrides: Dict[str, Any]) -> EsriExportConfig:
    classes = [c["Name"] for c in emd.get("Classes") or []]
    num_classes = 1 + len(classes)
    resize_to = int(emd.get("resize_to", emd.get("ImageHeight", 224)))
    extract_bands = list(emd.get("ExtractBands") or [0, 1, 2])
    apply_scaled = apply_scaled_norm_default(overrides)
    return EsriExportConfig(
        emd=emd,
        resize_to=resize_to,
        extract_bands=extract_bands,
        num_classes=num_classes,
        apply_scaled_norm=apply_scaled,
    )


def preprocess_map_space(
    chw_dn: np.ndarray, stats: Dict[str, Any], apply_scaled_norm: bool
) -> torch.Tensor:
    """chw_dn: (3, H, W) float32 digital numbers. Returns float tensor (3, H, W) CPU."""
    mins = np.array(stats["band_min_values"], dtype=np.float32).reshape(3, 1, 1)
    maxs = np.array(stats["band_max_values"], dtype=np.float32).reshape(3, 1, 1)
    x = (chw_dn.astype(np.float32) - mins) / (maxs - mins + 1e-8)
    x = np.clip(x, 0.0, 1.0)
    if apply_scaled_norm:
        sm = np.array(stats["scaled_mean_values"], dtype=np.float32).reshape(3, 1, 1)
        ss = np.array(stats["scaled_std_values"], dtype=np.float32).reshape(3, 1, 1)
        x = (x - sm) / (ss + 1e-8)
    return torch.from_numpy(np.ascontiguousarray(x))


def window_array_to_chw_dn(
    arr: np.ndarray, extract_bands: List[int]
) -> np.ndarray:
    """
    arr: rasterio read shape (bands, h, w), any numeric dtype.
    Returns float32 (3, h, w) for selected 0-based bands.
    """
    need = max(extract_bands) + 1
    if arr.shape[0] < need:
        raise ValueError(f"Raster has {arr.shape[0]} bands; need at least {need} for ExtractBands {extract_bands}")
    stacked = np.stack([arr[b].astype(np.float32) for b in extract_bands], axis=0)
    if stacked.shape[0] != 3:
        raise ValueError("This build supports exactly 3 ExtractBands for Esri MAP_SPACE models.")
    return stacked


def chw_resize_bilinear(chw: torch.Tensor, size: int) -> torch.Tensor:
    """chw (3,H,W) -> (3,size,size)"""
    t = chw.unsqueeze(0)
    out = F.interpolate(t, size=(size, size), mode="bilinear", align_corners=False)
    return out.squeeze(0)


def load_esri_maskrcnn(model_dir: str, device: torch.device) -> Tuple[torch.nn.Module, EsriExportConfig]:
    """Load or return cached Esri FPN model + config."""
    with _esri_lock:
        if model_dir in _esri_model_cache:
            cfg = parse_export_config(load_emd(model_dir), load_inference_overrides(model_dir))
            return _esri_model_cache[model_dir], cfg

    overrides = load_inference_overrides(model_dir)
    emd = load_emd(model_dir)
    cfg = parse_export_config(emd, overrides)
    _, pth_path = _find_emd_pth_pair(model_dir)

    model = maskrcnn_resnet50_fpn(weights=None, weights_backbone=None, num_classes=cfg.num_classes)
    try:
        state = torch.load(pth_path, map_location=device, weights_only=True)
    except TypeError:
        state = torch.load(pth_path, map_location=device)
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing or unexpected:
        raise RuntimeError(f"Esri checkpoint load mismatch: missing={missing!r} unexpected={unexpected!r}")

    rt = cfg.resize_to
    model.transform = GeneralizedRCNNTransform(
        min_size=rt,
        max_size=rt,
        image_mean=[0.0, 0.0, 0.0],
        image_std=[1.0, 1.0, 1.0],
    )
    model.to(device)
    model.eval()

    with _esri_lock:
        if len(_esri_model_cache) >= _MAX_CACHED_ESRI:
            k = next(iter(_esri_model_cache))
            del _esri_model_cache[k]
        _esri_model_cache[model_dir] = model

    return model, cfg


def raster_window_to_esri_input(
    arr_bhw: np.ndarray,
    cfg: EsriExportConfig,
    device: torch.device,
) -> torch.Tensor:
    """
    arr_bhw: (bands, tile_h, tile_w) from rasterio read(window=...).
    Returns tensor on device, shape (3, resize_to, resize_to) ready for model([t]).
    """
    chw = window_array_to_chw_dn(arr_bhw, cfg.extract_bands)
    stats = cfg.emd.get("NormalizationStats") or {}
    t = preprocess_map_space(chw, stats, cfg.apply_scaled_norm)
    t = chw_resize_bilinear(t, cfg.resize_to)
    return t.to(device)


def upsample_detection_output_to_native_hw(
    output: Dict[str, Any], native_h: int, native_w: int
) -> Dict[str, Any]:
    """Resize instance masks from model space to native tile pixels for geo vectorization."""
    masks = output.get("masks")
    if masks is None or masks.numel() == 0:
        return output
    if masks.shape[-2] == native_h and masks.shape[-1] == native_w:
        return output
    m_up = F.interpolate(masks.float(), size=(native_h, native_w), mode="nearest")
    out = dict(output)
    out["masks"] = m_up
    return out
