"""
GiD Land Cover Classification - Simple UI
Run: python app.py
Then open the URL shown (e.g. http://127.0.0.1:7860)
Supports PNG, JPG, and TIFF/GeoTIFF (e.g. Sentinel).
Uses GPU (CUDA) when available for faster predictions.

Local weights: prefer models/artifacts/lulc (see backend/model_paths.py); legacy backend/lulc/ still works.
"""
import os
import sys

_lulc_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.normpath(os.path.join(_lulc_dir, ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import io
import numpy as np
from transformers import AutoImageProcessor, SiglipForImageClassification
from PIL import Image, ImageDraw, ImageFont
import torch

# Use GPU to the fullest when available (e.g. NVIDIA A5000)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# Batch size for patch-based segmentation (tune for your GPU VRAM; A5000 24GB can handle 64+)
SEG_BATCH_SIZE = 64
# Mixed precision on GPU for faster inference (FP16 on NVIDIA)
USE_AMP = DEVICE.type == "cuda"

# Bright categorical palette — strong saturation/value for clear overlays on satellite imagery
CLASS_COLORS = [
    (34, 197, 94),    # 0 arbor woodland
    (163, 230, 53),   # 1 artificial grassland
    (251, 146, 60),   # 2 dry cropland
    (52, 211, 153),   # 3 garden plot
    (192, 38, 211),   # 4 industrial land
    (14, 165, 233),   # 5 irrigated land
    (59, 130, 246),   # 6 lake
    (132, 204, 22),   # 7 natural grassland
    (250, 204, 21),   # 8 paddy field
    (56, 189, 248),   # 9 pond
    (37, 99, 235),    # 10 river
    (244, 114, 182),  # 11 rural residential
    (101, 163, 13),   # 12 shrub land
    (253, 224, 71),   # 13 traffic land
    (239, 68, 68),    # 14 urban residential
]


def load_image_from_path(path):
    """Load image from file path. Uses rasterio for TIFF/GeoTIFF so Sentinel etc. work."""
    if path is None or (isinstance(path, list) and not path):
        return None
    if isinstance(path, list):
        path = path[0]
    path = str(path)
    lower = path.lower()
    if lower.endswith(".tif") or lower.endswith(".tiff"):
        try:
            import rasterio
            with rasterio.open(path) as src:
                # Read first 3 bands as RGB (or single band repeated)
                n = min(3, src.count)
                data = src.read(list(range(1, n + 1)))
            # (C, H, W) -> (H, W, C); normalize to 0–255 if needed
            if data.dtype in (np.float32, np.float64):
                data = (np.clip(data, 0, 1) * 255).astype(np.uint8)
            elif data.max() > 255:
                data = (np.clip(data.astype(np.float32) / data.max(), 0, 1) * 255).astype(np.uint8)
            if data.shape[0] == 1:
                data = np.repeat(data, 3, axis=0)
            data = np.transpose(data, (1, 2, 0))
            return Image.fromarray(data).convert("RGB")
        except Exception as e:
            raise RuntimeError(f"Could not read TIFF with rasterio: {e}. Install with: pip install rasterio") from e
    return Image.open(path).convert("RGB")


def raster_bands_to_pil_rgb(data):
    """Convert rasterio-style (C, H, W) ndarray to RGB PIL. Same scaling rules as TIFF branch of load_image_from_path."""
    if data is None or data.size == 0:
        return None
    data = np.asarray(data)
    if data.dtype in (np.float32, np.float64):
        data = (np.clip(data, 0, 1) * 255).astype(np.uint8)
    elif data.size and data.max() > 255:
        data = (np.clip(data.astype(np.float32) / data.max(), 0, 1) * 255).astype(np.uint8)
    if data.shape[0] == 1:
        data = np.repeat(data, 3, axis=0)
    data = np.transpose(data, (1, 2, 0))
    return Image.fromarray(data).convert("RGB")


from model_paths import resolve_lulc_pretrained_path

MODEL_PATH = resolve_lulc_pretrained_path()

# Label names (from config / README)
ID2LABEL = {
    "0": "arbor woodland",
    "1": "artificial grassland",
    "2": "dry cropland",
    "3": "garden plot",
    "4": "industrial land",
    "5": "irrigated land",
    "6": "lake",
    "7": "natural grassland",
    "8": "paddy field",
    "9": "pond",
    "10": "river",
    "11": "rural residential",
    "12": "shrub land",
    "13": "traffic land",
    "14": "urban residential",
}


def load_model():
    """Load model and processor once. Moves model to GPU when available."""
    print(f"Loading model from: {MODEL_PATH}")
    processor = AutoImageProcessor.from_pretrained(MODEL_PATH)
    model = SiglipForImageClassification.from_pretrained(MODEL_PATH)
    model = model.to(DEVICE)
    model.eval()
    if DEVICE.type == "cuda":
        print(f"Using GPU: {torch.cuda.get_device_name(0)} (batch size={SEG_BATCH_SIZE}, AMP={USE_AMP})")
    else:
        print("Using CPU")
    return processor, model


def _to_device(inputs):
    """Move processor outputs to the same device as the model."""
    return {k: v.to(DEVICE) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}


processor, model = load_model()


# Max size for display (banner/legend) when not doing segmentation
DISPLAY_MAX_PX = 1000
# Segmentation overlay
SEG_MAX_PX = 1000   # Max side length for segmentation
PATCH_SIZE = 224    # Model input size (fixed by SigLIP)
SEG_STRIDE_FAST = 112  # Larger tiles, faster
SEG_STRIDE_PIXEL = 1    # Pixel-level (slower; each pixel averaged over overlapping patches)
SEG_ALPHA = 0.82  # Strong overlay so classes read like a segmentation map
# Single-band class GeoTIFF nodata (15 classes use 0–14)
CLASS_GRID_NODATA = 255


def _class_grid_to_overlay_rgba(class_grid: np.ndarray, alpha_byte: int) -> np.ndarray:
    """Paint each pixel with its class color (no patch averaging) for crisp segmentation look."""
    seg_rgb = np.zeros((*class_grid.shape, 3), dtype=np.uint8)
    for ci in range(len(CLASS_COLORS)):
        seg_rgb[class_grid == ci] = CLASS_COLORS[ci]
    out = np.zeros((*class_grid.shape, 4), dtype=np.uint8)
    out[:, :, :3] = seg_rgb
    nodata = class_grid == CLASS_GRID_NODATA
    out[:, :, 3] = np.where(nodata, 0, alpha_byte)
    return out


def _rgba_base_hide_invalid(rgb_pil: Image.Image, valid_hw: np.ndarray) -> Image.Image:
    """RGBA copy of the base image; pixels outside valid_hw (e.g. ROI padding) are fully transparent."""
    rgba = np.array(rgb_pil.convert("RGBA"), dtype=np.uint8)
    if valid_hw.shape[:2] != rgba.shape[:2]:
        return Image.fromarray(rgba, mode="RGBA")
    rgba[~valid_hw.astype(bool), 3] = 0
    return Image.fromarray(rgba, mode="RGBA")


def class_grid_to_prediction_rgba_image(class_grid: np.ndarray) -> Image.Image:
    """Class-colored RGBA for UI: nodata is transparent (not black), so empty tile padding does not show."""
    cg = np.asarray(class_grid, dtype=np.uint8)
    h, w = cg.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for ci, color in enumerate(CLASS_COLORS):
        m = cg == ci
        if np.any(m):
            rgba[m, 0] = color[0]
            rgba[m, 1] = color[1]
            rgba[m, 2] = color[2]
            rgba[m, 3] = 255
    return Image.fromarray(rgba, mode="RGBA")


def class_grid_to_prediction_rgb_image(class_grid: np.ndarray) -> Image.Image:
    """Solid RGB class map (nodata as black). Prefer class_grid_to_prediction_rgba_image for UI exports."""
    return class_grid_to_prediction_rgba_image(class_grid).convert("RGB")


def class_grid_to_prediction_png_bytes(class_grid: np.ndarray) -> bytes:
    buf = io.BytesIO()
    class_grid_to_prediction_rgba_image(class_grid).save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def _rgb_valid_data_mask(arr_u8: np.ndarray) -> np.ndarray:
    """
    True where the RGB image has real raster data (not empty padding).
    ROI clips set exterior pixels to (0,0,0); rasterio mask fills outside with nodata=0 → same in RGB.
    """
    if arr_u8.ndim != 3 or arr_u8.shape[2] < 3:
        return np.ones(arr_u8.shape[:2], dtype=bool)
    r = arr_u8[:, :, 0].astype(np.int16)
    g = arr_u8[:, :, 1].astype(np.int16)
    b = arr_u8[:, :, 2].astype(np.int16)
    return (r | g | b) > 0


def _pil_tight_crop_to_mask(pil_img: Image.Image, mask_hw: np.ndarray) -> Image.Image:
    """Crop PIL to the bounding box of True in mask (full image if mask empty or full)."""
    if pil_img is None or mask_hw is None or mask_hw.size == 0:
        return pil_img
    rows = np.any(mask_hw, axis=1)
    cols = np.any(mask_hw, axis=0)
    if not rows.any() or not cols.any():
        return pil_img
    y0, y1 = np.argmax(rows), len(rows) - np.argmax(rows[::-1])
    x0, x1 = np.argmax(cols), len(cols) - np.argmax(cols[::-1])
    return pil_img.crop((int(x0), int(y0), int(x1), int(y1)))


def _fill_invalid_like_valid_mean(arr_u8: np.ndarray, valid_hw: np.ndarray) -> np.ndarray:
    """
    Replace invalid (False in valid_hw) pixels with the mean RGB of valid pixels.
    SigLIP often maps large black regions to water classes (e.g. pond); this keeps patch / full-image
    inputs from being dominated by nodata padding inside the ROI bounding box.
    """
    out = np.array(arr_u8, dtype=np.uint8, copy=True)
    if valid_hw.shape[:2] != out.shape[:2]:
        return out
    if not np.any(valid_hw):
        return out
    mean = out[valid_hw].reshape(-1, out.shape[2]).mean(axis=0)
    fill = np.clip(np.round(mean), 0, 255).astype(np.uint8)
    out[~valid_hw] = fill
    return out


def _patch_anchor_positions(length: int, patch: int, stride: int):
    """
    Start indices for sliding windows along one axis so the last window aligns with the
    far edge. Plain range(0, length - patch + 1, stride) misses the bottom/right strip when
    (length - patch) is not a multiple of stride.
    """
    if length <= patch:
        return [0]
    span = length - patch
    anchors = list(range(0, span + 1, stride))
    if anchors[-1] != span:
        anchors.append(span)
    return anchors


def _iter_position_batches(y_anchors, x_anchors, batch_size: int):
    """Yield patch positions in fixed-size batches without storing the full grid."""
    batch = []
    for y0 in y_anchors:
        for x0 in x_anchors:
            batch.append((y0, x0))
            if len(batch) >= batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


def _font_size(font, s="Ag"):
    """Height of font for line spacing (PIL 8+ has getbbox, else getsize)."""
    try:
        b = font.getbbox(s)
        return b[3] - b[1]
    except AttributeError:
        return font.getsize(s)[1]


def draw_predictions_on_image(image, probs, top_k=5, draw_overlay=True):
    """Build label_dict from probs. If draw_overlay, paint banner + legend on a resized copy (e.g. Gradio)."""
    label_dict = {ID2LABEL[str(i)]: round(probs[i], 4) for i in range(len(probs))}
    if not draw_overlay:
        return image.copy(), label_dict

    img = image.copy().convert("RGB")
    w, h = img.size
    # Resize to display size so banner/legend are readable (huge satellite images)
    if max(w, h) > DISPLAY_MAX_PX:
        r = DISPLAY_MAX_PX / max(w, h)
        nw, nh = int(w * r), int(h * r)
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
        w, h = img.size
    draw = ImageDraw.Draw(img)

    # Sort by probability and take top_k
    indices = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)[:top_k]

    # Fixed sizes so overlay is always readable (not tied to image size)
    banner_h = 56
    font_big = 26
    font_small = 16
    pad = 12
    try:
        font = ImageFont.truetype("arial.ttf", font_big)
        font_sm = ImageFont.truetype("arial.ttf", font_small)
    except OSError:
        font = ImageFont.load_default()
        font_sm = font
    line_h = _font_size(font_sm) + pad
    legend_h = top_k * line_h + pad * 2

    # Colored banner at top (main prediction) with dark outline for visibility
    top_class_idx = indices[0]
    top_class_name = ID2LABEL[str(top_class_idx)]
    top_pct = int(round(probs[top_class_idx] * 100))
    color = CLASS_COLORS[top_class_idx]
    draw.rectangle([0, 0, w, banner_h], fill=color)
    txt = f"Prediction: {top_class_name} ({top_pct}%)"
    bx, by = pad, (banner_h - _font_size(font)) // 2 - 1
    for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1),(0,-1),(0,1),(-1,0),(1,0)]:
        draw.text((bx + dx, by + dy), txt, fill=(0, 0, 0), font=font)
    draw.text((bx, by), txt, fill=(255, 255, 255), font=font)

    # Legend for top-k (bottom-right), keep inside image; dark outline on text
    legend_w = min(int(w * 0.5), 340)
    legend_x = max(pad, w - legend_w - pad)
    legend_y = max(pad, h - legend_h - pad)
    for i, idx in enumerate(indices):
        name = ID2LABEL[str(idx)]
        pct = int(round(probs[idx] * 100))
        c = CLASS_COLORS[idx]
        y = legend_y + pad + i * line_h
        draw.rectangle([legend_x, y, legend_x + 26, y + 22], fill=c, outline=(255, 255, 255), width=2)
        line_txt = f"{name}: {pct}%"
        for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
            draw.text((legend_x + 30 + dx, y + 2 + dy), line_txt, fill=(0, 0, 0), font=font_sm)
        draw.text((legend_x + 30, y + 2), line_txt, fill=(255, 255, 255), font=font_sm)

    return img, label_dict


def segment_and_draw(
    image_pil, processor, model, top_k=5, seg_stride=None, input_size=None, skip_downscale=False
):
    """
    Patch-based pseudo-segmentation: classify patches, overlay colored regions on the image.
    Legend/banner are not drawn on the image (web UI shows them on the map).
    seg_stride: patch step (e.g. SEG_STRIDE_FAST ~= PATCH_SIZE/2 for faster, SEG_STRIDE_PIXEL=1 for pixel-level).
    input_size: optional (width, height) forced inference size.
    skip_downscale: if True, do not apply SEG_MAX_PX global resize.
    Returns (annotated PIL image, label_dict for full-image probs).
    """
    stride = seg_stride if seg_stride is not None else SEG_STRIDE_FAST
    img = image_pil.copy().convert("RGB")
    w, h = img.size
    if input_size is not None:
        tw, th = int(input_size[0]), int(input_size[1])
        if tw > 0 and th > 0 and (w != tw or h != th):
            img = img.resize((tw, th), Image.Resampling.LANCZOS)
            w, h = img.size
    elif (not skip_downscale) and max(w, h) > SEG_MAX_PX:
        r = SEG_MAX_PX / max(w, h)
        w, h = int(w * r), int(h * r)
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    arr = np.array(img)
    data_mask = _rgb_valid_data_mask(arr)
    n_classes = len(ID2LABEL)
    uniform = [1.0 / n_classes] * n_classes
    uniform_dict = {ID2LABEL[str(i)]: round(uniform[i], 4) for i in range(n_classes)}

    if not data_mask.any():
        class_grid = np.full((h, w), CLASS_GRID_NODATA, dtype=np.uint8)
        overlay_u8 = _class_grid_to_overlay_rgba(class_grid, int(SEG_ALPHA * 255))
        overlay_pil = Image.fromarray(overlay_u8, mode="RGBA")
        base = _rgba_base_hide_invalid(img, data_mask)
        out = Image.alpha_composite(base, overlay_pil)
        return out, img, uniform_dict, uniform, class_grid

    arr_model = _fill_invalid_like_valid_mean(arr, data_mask)

    # If image smaller than one patch, do single full-image classification only (no patch grid)
    if w < PATCH_SIZE or h < PATCH_SIZE:
        cls_img = (
            _pil_tight_crop_to_mask(Image.fromarray(arr_model), data_mask)
            if not np.all(data_mask)
            else Image.fromarray(arr_model)
        )
        inputs = processor(images=cls_img, return_tensors="pt")
        inputs = _to_device(inputs)
        with torch.inference_mode():
            if USE_AMP:
                with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(**inputs).logits
            else:
                logits = model(**inputs).logits
            probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()
        label_dict = {ID2LABEL[str(i)]: round(probs[i], 4) for i in range(len(probs))}
        top_idx = int(max(range(len(probs)), key=lambda i: probs[i]))
        class_grid = np.full((h, w), CLASS_GRID_NODATA, dtype=np.uint8)
        class_grid[data_mask] = np.uint8(top_idx)
        overlay_u8 = _class_grid_to_overlay_rgba(class_grid, int(SEG_ALPHA * 255))
        overlay_pil = Image.fromarray(overlay_u8, mode="RGBA")
        base = _rgba_base_hide_invalid(img, data_mask)
        out = Image.alpha_composite(base, overlay_pil)
        return out, img, label_dict, probs, class_grid
    # Grid of patches for segmentation overlay (batched on GPU)
    y_anchors = _patch_anchor_positions(h, PATCH_SIZE, stride)
    x_anchors = _patch_anchor_positions(w, PATCH_SIZE, stride)
    total_patches = len(y_anchors) * len(x_anchors)
    total_active = sum(
        1
        for y0 in y_anchors
        for x0 in x_anchors
        if data_mask[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE].any()
    )
    print(
        f"[seg] Starting segmentation (non-streaming): image {w}x{h}, stride={stride}, "
        f"grid_patches={total_patches}, patches_with_data={total_active}, batch_size={SEG_BATCH_SIZE}",
        flush=True,
    )
    class_grid = np.full((h, w), CLASS_GRID_NODATA, dtype=np.uint8)
    patch_count = 0
    log_every = max(1, total_active // 20) if total_active else 1
    with torch.inference_mode():
        for batch_positions in _iter_position_batches(y_anchors, x_anchors, SEG_BATCH_SIZE):
            batch_positions = [
                (y0, x0)
                for y0, x0 in batch_positions
                if data_mask[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE].any()
            ]
            if not batch_positions:
                continue
            patch_pils = [
                Image.fromarray(arr_model[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE])
                for y0, x0 in batch_positions
            ]
            inputs = processor(images=patch_pils, return_tensors="pt")
            inputs = _to_device(inputs)
            if USE_AMP:
                with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(**inputs).logits
            else:
                logits = model(**inputs).logits
            pred_indices = logits.argmax(dim=1).cpu().tolist()
            for (y0, x0), pred_idx in zip(batch_positions, pred_indices):
                m = data_mask[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE]
                sl = class_grid[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE]
                sl[m] = np.uint8(pred_idx)
            patch_count += len(batch_positions)
            if patch_count % log_every < len(batch_positions) or patch_count >= total_active:
                print(f"[seg] Patch {patch_count}/{total_active} ({100.0 * patch_count / max(total_active, 1):.1f}%)", flush=True)
    print(f"[seg] Segmentation done. Patches with data: {patch_count}", flush=True)
    overlay_u8 = _class_grid_to_overlay_rgba(class_grid, int(SEG_ALPHA * 255))
    overlay_pil = Image.fromarray(overlay_u8, mode="RGBA")
    # Full-image logits: inpainted crop so padding is not classified as water (pond)
    img_cls = (
        _pil_tight_crop_to_mask(Image.fromarray(arr_model), data_mask)
        if not np.all(data_mask)
        else Image.fromarray(arr_model)
    )
    inputs = processor(images=img_cls, return_tensors="pt")
    inputs = _to_device(inputs)
    with torch.inference_mode():
        if USE_AMP:
            with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                logits = model(**inputs).logits
        else:
            logits = model(**inputs).logits
        probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()
    label_dict = {ID2LABEL[str(i)]: round(probs[i], 4) for i in range(len(probs))}
    base = _rgba_base_hide_invalid(img, data_mask)
    out = Image.alpha_composite(base, overlay_pil)
    return out, img, label_dict, probs, class_grid


def segment_and_draw_streaming(
    image_pil,
    processor,
    model,
    top_k=5,
    seg_stride=None,
    progress_patch_interval=None,
    input_size=None,
    skip_downscale=False,
    emit_partial_images=True,
    partial_overlay_only=False,
):
    """
    Same as segment_and_draw but yields (partial_overlay_pil, progress_0_to_1) as the overlay builds,
    then yields the final (out, img, label_dict, probs).
    progress_patch_interval: emit a partial frame every N patches (default 5).
    input_size: optional (width, height) forced inference size.
    skip_downscale: if True, do not apply SEG_MAX_PX global resize.
    emit_partial_images: if False, emit numeric progress only (no partial image).
    partial_overlay_only: if True, emit RGBA class overlay only (no base compositing).
    """
    stride = seg_stride if seg_stride is not None else SEG_STRIDE_FAST
    img = image_pil.copy().convert("RGB")
    w, h = img.size
    if input_size is not None:
        tw, th = int(input_size[0]), int(input_size[1])
        if tw > 0 and th > 0 and (w != tw or h != th):
            img = img.resize((tw, th), Image.Resampling.LANCZOS)
            w, h = img.size
    elif (not skip_downscale) and max(w, h) > SEG_MAX_PX:
        r = SEG_MAX_PX / max(w, h)
        w, h = int(w * r), int(h * r)
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    arr = np.array(img)
    data_mask = _rgb_valid_data_mask(arr)
    n_classes = len(ID2LABEL)
    uniform = [1.0 / n_classes] * n_classes
    uniform_dict = {ID2LABEL[str(i)]: round(uniform[i], 4) for i in range(n_classes)}

    if not data_mask.any():
        class_grid = np.full((h, w), CLASS_GRID_NODATA, dtype=np.uint8)
        overlay_u8 = _class_grid_to_overlay_rgba(class_grid, int(SEG_ALPHA * 255))
        overlay_pil = Image.fromarray(overlay_u8, mode="RGBA")
        base = _rgba_base_hide_invalid(img, data_mask)
        out = Image.alpha_composite(base, overlay_pil)
        yield (out, img, uniform_dict, uniform, class_grid)
        return

    arr_model = _fill_invalid_like_valid_mean(arr, data_mask)

    if w < PATCH_SIZE or h < PATCH_SIZE:
        print(f"[seg] Image smaller than patch ({w}x{h}), single full-image classification", flush=True)
        cls_img = (
            _pil_tight_crop_to_mask(Image.fromarray(arr_model), data_mask)
            if not np.all(data_mask)
            else Image.fromarray(arr_model)
        )
        inputs = processor(images=cls_img, return_tensors="pt")
        inputs = _to_device(inputs)
        with torch.inference_mode():
            if USE_AMP:
                with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(**inputs).logits
            else:
                logits = model(**inputs).logits
            probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()
        label_dict = {ID2LABEL[str(i)]: round(probs[i], 4) for i in range(len(probs))}
        top_idx = int(max(range(len(probs)), key=lambda i: probs[i]))
        class_grid = np.full((h, w), CLASS_GRID_NODATA, dtype=np.uint8)
        class_grid[data_mask] = np.uint8(top_idx)
        overlay_u8 = _class_grid_to_overlay_rgba(class_grid, int(SEG_ALPHA * 255))
        overlay_pil = Image.fromarray(overlay_u8, mode="RGBA")
        base = _rgba_base_hide_invalid(img, data_mask)
        out = Image.alpha_composite(base, overlay_pil)
        yield (out, img, label_dict, probs, class_grid)
        return
    y_anchors = _patch_anchor_positions(h, PATCH_SIZE, stride)
    x_anchors = _patch_anchor_positions(w, PATCH_SIZE, stride)
    total_patches = len(y_anchors) * len(x_anchors)
    total_active = sum(
        1
        for y0 in y_anchors
        for x0 in x_anchors
        if data_mask[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE].any()
    )
    n_emit = progress_patch_interval if progress_patch_interval is not None else 5
    n_emit = max(1, min(int(n_emit), 50))
    log_every = max(1, total_active // 20) if total_active else 1
    print(
        f"[seg] Starting streaming segmentation: image {w}x{h}, stride={stride}, grid_patches={total_patches}, "
        f"patches_with_data={total_active}, batch_size={SEG_BATCH_SIZE}, emit_every={n_emit} patches",
        flush=True,
    )
    class_grid = np.full((h, w), CLASS_GRID_NODATA, dtype=np.uint8)
    patch_count = 0
    def _emit_partial():
        if not emit_partial_images:
            return None, patch_count / max(total_active, 1)
        ov = _class_grid_to_overlay_rgba(class_grid, int(SEG_ALPHA * 255))
        overlay_pil = Image.fromarray(ov, mode="RGBA")
        if partial_overlay_only:
            return overlay_pil, patch_count / max(total_active, 1)
        base_rgba = _rgba_base_hide_invalid(img, data_mask)
        partial = Image.alpha_composite(base_rgba, overlay_pil)
        return partial, patch_count / max(total_active, 1)

    with torch.inference_mode():
        for batch_positions in _iter_position_batches(y_anchors, x_anchors, SEG_BATCH_SIZE):
            batch_positions = [
                (y0, x0)
                for y0, x0 in batch_positions
                if data_mask[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE].any()
            ]
            if not batch_positions:
                continue
            patch_pils = [
                Image.fromarray(arr_model[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE])
                for y0, x0 in batch_positions
            ]
            inputs = processor(images=patch_pils, return_tensors="pt")
            inputs = _to_device(inputs)
            if USE_AMP:
                with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(**inputs).logits
            else:
                logits = model(**inputs).logits
            pred_indices = logits.argmax(dim=1).cpu().tolist()
            for (y0, x0), pred_idx in zip(batch_positions, pred_indices):
                m = data_mask[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE]
                sl = class_grid[y0 : y0 + PATCH_SIZE, x0 : x0 + PATCH_SIZE]
                sl[m] = np.uint8(pred_idx)
                patch_count += 1
                if patch_count % log_every == 0 or patch_count == total_active:
                    pct = 100.0 * patch_count / max(total_active, 1)
                    print(f"[seg] Patch {patch_count}/{total_active} ({pct:.1f}%)", flush=True)
                if patch_count % n_emit == 0 or patch_count == total_active:
                    partial, prog = _emit_partial()
                    yield (partial, prog, patch_count, total_active)
    overlay_u8 = _class_grid_to_overlay_rgba(class_grid, int(SEG_ALPHA * 255))
    overlay_pil = Image.fromarray(overlay_u8, mode="RGBA")
    img_cls = (
        _pil_tight_crop_to_mask(Image.fromarray(arr_model), data_mask)
        if not np.all(data_mask)
        else Image.fromarray(arr_model)
    )
    inputs = processor(images=img_cls, return_tensors="pt")
    inputs = _to_device(inputs)
    with torch.inference_mode():
        if USE_AMP:
            with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                logits = model(**inputs).logits
        else:
            logits = model(**inputs).logits
        probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()
    label_dict = {ID2LABEL[str(i)]: round(probs[i], 4) for i in range(len(probs))}
    base = _rgba_base_hide_invalid(img, data_mask)
    out = Image.alpha_composite(base, overlay_pil)
    print(f"[seg] Streaming segmentation done. Patches with data: {patch_count}", flush=True)
    yield (out, img, label_dict, probs, class_grid)


def classify(file_in):
    """Classify land cover and return image with overlay + label dict."""
    image = load_image_from_path(file_in)
    if image is None:
        return None, {}
    image = image.convert("RGB")

    inputs = processor(images=image, return_tensors="pt")
    inputs = _to_device(inputs)

    with torch.inference_mode():
        if USE_AMP:
            with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                outputs = model(**inputs)
        else:
            outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()

    annotated_img, label_dict = draw_predictions_on_image(image, probs, top_k=5)
    return np.array(annotated_img), label_dict


if __name__ == "__main__":
    import gradio as gr
    iface = gr.Interface(
        fn=classify,
        inputs=gr.File(
            file_count="single",
            file_types=[".png", ".jpg", ".jpeg", ".tif", ".tiff"],
            label="Upload image (PNG, JPG, or TIFF/GeoTIFF e.g. Sentinel)",
        ),
        outputs=[
            gr.Image(label="Image with predictions"),
            gr.Label(num_top_classes=5, label="Land cover (top 5)"),
        ],
        title="GiD Land Cover Classification",
        description="Upload an image to classify its land cover. Predictions are shown on the image (banner + legend) and in the list below. The web app shows the legend on the map instead.",
    )
    iface.launch()
