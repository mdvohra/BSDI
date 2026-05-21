"""
SAR flood segmentation helpers (UNet, same architecture as unetnew.UNet).
Weights: models/artifacts/unet or sar_flood, legacy backend/models/, or SAR_Flood/ (see unetnew discovery).
"""
from __future__ import annotations

import os

import numpy as np
import torch
from PIL import Image


def is_sar_flood_model(model_name: str, resolved_path: str | None = None) -> bool:
    """True if SAR log-preprocessing should run (name heuristics or file under SAR_Flood/)."""
    n = (model_name or "").lower()
    if "sar" in n and "flood" in n:
        return True
    if "sar" in n and "finetune" in n:
        return True
    if resolved_path:
        rp = os.path.normpath(resolved_path).replace("\\", "/").lower()
        if "sar_flood" in rp:
            return True
    return False


def raster_to_pil_l_sar(src) -> Image.Image:
    """Single-band raster → grayscale PIL (uint8 stretch) for chip tiling."""
    arr = src.read(1).astype(np.float32)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    mn, mx = np.percentile(arr, [1, 99])
    if mx <= mn:
        mn, mx = float(np.min(arr)), float(np.max(arr))
    if mx <= mn:
        u8 = np.zeros(arr.shape, dtype=np.uint8)
    else:
        u8 = np.clip((arr - mn) / (mx - mn) * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(u8, mode="L")


def preprocess_pil_chip_sar(img: Image.Image, device: torch.device, add_batch_dim: bool = True) -> torch.Tensor:
    """Match SAR_Flood/inf_sar_flood.py: log transform + percentile norm, pseudo-RGB input."""
    image = img.convert("L")
    image_resized = image.resize((256, 256), Image.BILINEAR)
    image_np = np.array(image_resized).astype(np.float32)
    image_np = 10 * np.log10(image_np + 1e-8)
    min_val = np.percentile(image_np, 1)
    max_val = np.percentile(image_np, 99)
    image_np = np.clip((image_np - min_val) / (max_val - min_val + 1e-8), 0, 1)
    image_rgb = np.stack([image_np, image_np, image_np], axis=-1)
    tensor = torch.from_numpy(image_rgb.transpose(2, 0, 1)).float().to(device)
    if add_batch_dim:
        tensor = tensor.unsqueeze(0)
    return tensor
