import os
import io
import uuid
import tempfile
import logging
import math
from typing import Optional
import numpy as np
import PIL
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
import rasterio
from rasterio.transform import Affine
from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import threading
import time
from fastapi.responses import FileResponse
from skimage.metrics import peak_signal_noise_ratio as psnr, structural_similarity as ssim
from fastapi import Query

from model_paths import artifact_dir, legacy_backend_models_dir, ensure_dir

PIL.Image.MAX_IMAGE_PIXELS = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.makedirs('uploads', exist_ok=True)
os.makedirs('outputs', exist_ok=True)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = artifact_dir("srgan")
LEGACY_MODEL_DIR = legacy_backend_models_dir()
ensure_dir(MODEL_DIR)
ensure_dir(LEGACY_MODEL_DIR)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"Using device: {DEVICE}")
run_id_to_files = {}

app = FastAPI(title="SRGAN Super-Resolution API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Progress tracking
progress_data = {
    "progress": 0,
    "phase": "idle",
    "current_step": "",
    "status": "idle"
}
progress_lock = threading.Lock()

def update_progress(progress=None, phase=None, current_step=None, status=None):
    with progress_lock:
        if progress is not None:
            progress_data["progress"] = progress
        if phase is not None:
            progress_data["phase"] = phase
        if current_step is not None:
            progress_data["current_step"] = current_step
        if status is not None:
            progress_data["status"] = status

@app.get("/progress")
async def get_progress():
    with progress_lock:
        return progress_data.copy()

class ResidualBlock(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(channels, channels, 3, 1, 1),
            nn.BatchNorm2d(channels),
            nn.PReLU(),
            nn.Conv2d(channels, channels, 3, 1, 1),
            nn.BatchNorm2d(channels)
        )
    
    def forward(self, x):
        return x + self.block(x)

class Generator(nn.Module):
    def __init__(self, scale_factor=4, num_blocks=8):
        super().__init__()
        self.scale_factor = scale_factor
        
        self.conv1 = nn.Sequential(
            nn.Conv2d(3, 64, 9, 1, 4),
            nn.PReLU()
        )
        self.res_blocks = nn.Sequential(*[ResidualBlock(64) for _ in range(num_blocks)])
        self.conv2 = nn.Sequential(
            nn.Conv2d(64, 64, 3, 1, 1),
            nn.BatchNorm2d(64)
        )
        
        upsample_layers = []
        n_upsamples = int(np.log2(scale_factor))
        for _ in range(n_upsamples):
            upsample_layers += [
                nn.Conv2d(64, 256, 3, 1, 1),
                nn.PixelShuffle(2),
                nn.PReLU()
            ]
        self.upsample = nn.Sequential(*upsample_layers)
        self.conv3 = nn.Conv2d(64, 3, 9, 1, 4)
    
    def forward(self, x):
        out1 = self.conv1(x)
        out = self.res_blocks(out1)
        out = self.conv2(out)
        out = out + out1
        out = self.upsample(out)
        
        _, _, H_in, W_in = x.shape
        expected_H = int(H_in * self.scale_factor)
        expected_W = int(W_in * self.scale_factor)
        out = F.interpolate(out, size=(expected_H, expected_W), mode='bicubic', align_corners=False)
        out = self.conv3(out)
        return torch.clamp(out, 0.0, 1.0)

# Model loading
loaded_models = {}

_SR_KEYS = ("super", "resolution", "srgan", "upscale", "generator")


def _resolve_srgan_weight_path(filename: str) -> str:
    primary = os.path.join(MODEL_DIR, filename)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(LEGACY_MODEL_DIR, filename)
    if os.path.isfile(legacy):
        return legacy
    raise FileNotFoundError(
        f"Model not found: {filename} (expected under {MODEL_DIR} or legacy {LEGACY_MODEL_DIR})"
    )


def load_model_by_name(model_name: str, scale_factor: int = 4):
    filename = model_name if model_name.endswith(".pth") else model_name + ".pth"
    model_path = _resolve_srgan_weight_path(filename)
    
    model_key = f"{filename}_{scale_factor}"
    if model_key in loaded_models:
        return loaded_models[model_key]
    
    model = Generator(scale_factor=scale_factor, num_blocks=8).to(DEVICE)
    state = torch.load(model_path, map_location=DEVICE)
    if isinstance(state, dict) and 'state_dict' in state:
        state = state['state_dict']
    
    model.load_state_dict(state)
    model.eval()
    loaded_models[model_key] = model
    return model

# ===============================================================
# Helper Functions
# ===============================================================
def create_chips(image: Image.Image, chip_size=512, overlap=32):
    w, h = image.size
    nx, ny = (w + chip_size - 1) // chip_size, (h + chip_size - 1) // chip_size
    total_chips = nx * ny
    
    chips, coords = [], []
    for i in range(nx):
        for j in range(ny):
            xs, ys = max(0, i * chip_size - overlap), max(0, j * chip_size - overlap)
            xe, ye = min(w, (i + 1) * chip_size + overlap), min(h, (j + 1) * chip_size + overlap)
            chip = image.crop((xs, ys, xe, ye))
            chips.append(chip)
            coords.append((xs, ys, xe, ye))
    
    return chips, coords

def preprocess_image_for_model(img: Image.Image):
    arr = np.array(img.convert("RGB")).astype(np.float32) / 255.0
    return torch.from_numpy(arr.transpose(2, 0, 1)).unsqueeze(0).to(DEVICE)

def process_chip(model, chip):
    with torch.no_grad():
        tensor = preprocess_image_for_model(chip)
        sr_tensor = model(tensor)
        return sr_tensor.squeeze().cpu().numpy()

def reassemble_chips(sr_chips, coords, original_size, scale_factor):
    output_w = int(original_size[0] * scale_factor)
    output_h = int(original_size[1] * scale_factor)
    
    full = np.zeros((3, output_h, output_w), np.float32)
    counts = np.zeros((output_h, output_w), np.float32)
    
    for sr_chip, (xs, ys, xe, ye) in zip(sr_chips, coords):
        xs_out = int(xs * scale_factor)
        ys_out = int(ys * scale_factor)
        chip_h, chip_w = sr_chip.shape[1], sr_chip.shape[2]
        
        full[:, ys_out:ys_out+chip_h, xs_out:xs_out+chip_w] += sr_chip
        counts[ys_out:ys_out+chip_h, xs_out:xs_out+chip_w] += 1
    
    counts[counts == 0] = 1
    full = full / counts
    return full

def tensor_to_image(tensor):
    img_array = tensor.transpose(1, 2, 0)
    img_array = np.clip(img_array * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(img_array)

def calculate_metrics(lr_img, sr_img):
    metrics = {}
    lr_upscaled = lr_img.resize(sr_img.size, Image.BICUBIC)
    lr_up_np = np.array(lr_upscaled).astype(np.float32) / 255.0
    sr_np = np.array(sr_img).astype(np.float32) / 255.0
    
    try:
        metrics['psnr_improvement'] = float(psnr(lr_up_np, sr_np, data_range=1.0))
        metrics['ssim_improvement'] = float(ssim(lr_up_np, sr_np, channel_axis=2, data_range=1.0))
    except:
        metrics['psnr_improvement'] = 0.0
        metrics['ssim_improvement'] = 0.0
    
    return metrics

@app.post("/predict")
async def predict(
    image: UploadFile = File(...),
    model_name: str = Query(...),
    scale_factor: int = Query(4, ge=2, le=8)
):
    start_time = time.time()
    run_id = str(uuid.uuid4())
    logger.info(f"Starting prediction {run_id} for {image.filename}")
    
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(image.filename)[1])
    os.close(tmp_fd)
    
    update_progress(progress=0, phase="initializing", current_step="Starting...", status="running")
    
    try:
        # Load image
        update_progress(progress=10, phase="loading", current_step="Loading image...")
        with open(tmp_path, "wb") as f:
            f.write(await image.read())
        
        pil_img = Image.open(tmp_path).convert("RGB")
        original_size = pil_img.size
        
        # Check geospatial metadata
        img_crs, transform_raster, geo_bounds = None, None, None
        if tmp_path.lower().endswith((".tif", ".tiff")):
            try:
                with rasterio.open(tmp_path) as src:
                    img_crs = src.crs
                    transform_raster = src.transform
                    bounds = src.bounds
                    geo_bounds = (bounds.left, bounds.bottom, bounds.right, bounds.top)
                    logger.info(f"Detected CRS: {img_crs}, Bounds: {geo_bounds}")
            except:
                pass
        
        # Create chips
        update_progress(progress=20, phase="preprocessing", current_step="Creating chips...")
        chips, coords = create_chips(pil_img, chip_size=512, overlap=32)
        total_chips = len(chips)
        
        # Load model
        update_progress(progress=30, phase="model_loading", current_step=f"Loading {model_name}...")
        model = load_model_by_name(model_name, scale_factor=scale_factor)
        
        # Process chips
        update_progress(progress=40, phase="upscaling", current_step="Processing chips...")
        sr_chips = []
        for i, chip in enumerate(chips, 1):
            sr_chip = process_chip(model, chip)
            sr_chips.append(sr_chip)
            progress = 40 + ((i / total_chips) * 40)
            update_progress(progress=int(progress), current_step=f"Chip {i}/{total_chips}")
        
        # Reassemble
        update_progress(progress=85, phase="postprocessing", current_step="Reassembling...")
        sr_full = reassemble_chips(sr_chips, coords, original_size, scale_factor)
        sr_image = tensor_to_image(sr_full)
        output_size = sr_image.size
        
        # Calculate metrics
        update_progress(progress=90, current_step="Calculating metrics...")
        metrics = calculate_metrics(pil_img, sr_image)
        
        # Save outputs
        update_progress(progress=93, phase="exporting", current_step="Saving outputs...")
        run_dir = os.path.join("outputs", run_id)
        os.makedirs(run_dir, exist_ok=True)
        
        # Save super-resolved image AS PNG for web overlay (IMPORTANT!)
        sr_filename = f"sr_{run_id}.png"
        sr_path = os.path.join(run_dir, sr_filename)
        sr_image.save(sr_path, format='PNG')
        
        # Also save as GeoTIFF for download
        sr_tiff_filename = f"sr_{run_id}.tif"
        sr_tiff_path = os.path.join(run_dir, sr_tiff_filename)
        
        if img_crs and transform_raster:
            # Save as GeoTIFF with scaled transform
            scaled_transform = Affine(
                transform_raster.a / scale_factor, transform_raster.b, transform_raster.c,
                transform_raster.d, transform_raster.e / scale_factor, transform_raster.f
            )
            sr_array = np.array(sr_image).transpose(2, 0, 1)
            with rasterio.open(
                sr_tiff_path, 'w', driver='GTiff',
                height=output_size[1], width=output_size[0], count=3,
                dtype=rasterio.uint8, crs=img_crs, transform=scaled_transform
            ) as dst:
                dst.write(sr_array)
        else:
            sr_image.save(sr_tiff_path, format='TIFF')
        
        run_id_to_files[run_id] = {
            "tiff": sr_tiff_path  # PNG is for overlay, TIFF is for download
                }
        # Calculate overlay bounds in WGS84 (for Leaflet)

        overlay_bounds_wgs84 = [[0.0, 0.0], [0.0, 0.0]]

        if geo_bounds and img_crs:
            try:
                from rasterio.warp import transform_bounds
        
                # ALWAYS convert to WGS84, even if already in WGS84
                logger.info(f"Original CRS: {img_crs}")
                logger.info(f"Original bounds: {geo_bounds}")
        
                # Check if already WGS84
                if img_crs.to_string() == "EPSG:4326":
                    # Already WGS84 - use directly
                    overlay_bounds_wgs84 = [
                        [float(geo_bounds[1]), float(geo_bounds[0])],  # [south, west]
                        [float(geo_bounds[3]), float(geo_bounds[2])]   # [north, east]
                    ]
                    logger.info(f"✅ Already in WGS84, bounds: {overlay_bounds_wgs84}")
                else:
                    # Convert from source CRS to WGS84
                    wgs84_bounds = transform_bounds(
                        img_crs, 
                        "EPSG:4326",
                        geo_bounds[0], geo_bounds[1], geo_bounds[2], geo_bounds[3]
                    )
                    # Format: transform_bounds returns (minx, miny, maxx, maxy)
                    overlay_bounds_wgs84 = [
                        [float(wgs84_bounds[1]), float(wgs84_bounds[0])],  # [south, west]
                        [float(wgs84_bounds[3]), float(wgs84_bounds[2])]   # [north, east]
                    ]
                    logger.info(f"✅ Converted {img_crs} to WGS84")
                    logger.info(f"WGS84 bounds: {overlay_bounds_wgs84}")
            
            except Exception as e:
                logger.error(f"❌ Failed to calculate/convert bounds: {e}")
                # Fallback: assume already in WGS84
                overlay_bounds_wgs84 = [
                    [float(geo_bounds[1]), float(geo_bounds[0])],
                    [float(geo_bounds[3]), float(geo_bounds[2])]
                ]

        sr_url = f"/outputs/{run_id}/{sr_filename}"
        sr_tiff_url = f"/outputs/{run_id}/{sr_tiff_filename}"
        
        response = {
            "status": "success",
            "run_id": run_id,
            "original_width": original_size[0],
            "original_height": original_size[1],
            "output_width": output_size[0],
            "output_height": output_size[1],
            "scale_factor": scale_factor,
            "psnr_improvement": round(metrics['psnr_improvement'], 2),
            "ssim_improvement": round(metrics['ssim_improvement'], 4),
            "overlay_url": sr_url,  # PNG for Leaflet overlay (like building detection!)
            "download_url": sr_tiff_url,  # GeoTIFF for download
            "overlay_bounds": overlay_bounds_wgs84,  # Same format as building detection!
            "crs": "EPSG:4326",
            "width": output_size[0], 
            "height": output_size[1],
            "processing_time": round(time.time() - start_time, 2)
        }
        
        update_progress(progress=100, phase="completed", current_step="Completed!", status="completed")
        logger.info(f"✅ Processing completed: {response}")
        
        return JSONResponse(content=response)
    
    except Exception as e:
        update_progress(progress=0, phase="error", current_step=f"Error: {str(e)}", status="error")
        logger.exception("Prediction failed")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        try:
            os.remove(tmp_path)
        except:
            pass
# @app.get("/export")

@app.get("/download_output")
async def download_sr_image(run_id: str = Query(...)):
    """Match api.js: GET /download_output?run_id={runId}"""
    if run_id not in run_id_to_files:
        raise HTTPException(status_code=404, detail="Run ID not found")
    
    sr_tiff_path = run_id_to_files[run_id].get("tiff")
    if not sr_tiff_path or not os.path.exists(sr_tiff_path):
        raise HTTPException(status_code=404, detail="SR image not found")
    
    return FileResponse(
        path=sr_tiff_path, 
        media_type='image/tiff',
        filename=f"sr_{run_id}.tif"
    )

@app.get("/download_geojson")
async def download_geojson_srgam(run_id: str = Query(...)):
    """Dummy endpoint - redirect to SR TIFF download"""
    return await download_sr_image(run_id)

@app.get("/download_shapefile")
async def download_shapefile_srgam(run_id: str = Query(...)):
    """Dummy endpoint - redirect to SR TIFF download"""
    return await download_sr_image(run_id)
@app.get("/super_resolution_model")
async def list_models():
    try:
        seen: dict[str, None] = {}
        for d in (MODEL_DIR, LEGACY_MODEL_DIR):
            if not os.path.isdir(d):
                continue
            for file in os.listdir(d):
                if file.endswith(('.pth', '.pt')) and file not in seen:
                    seen[file] = None
        models = []
        for file in sorted(seen.keys()):
            lower_file = file.lower()
            if any(key in lower_file for key in _SR_KEYS):
                models.append(file)
        return {"models": models} # Return empty list if none found
    except Exception as e:
        logger.error(f"Error listing SR models: {e}")
        return {"models": []}


# Mount static files
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

if __name__ == "__main__":
    uvicorn.run("super_resolution:app", host="0.0.0.0", port=8002, reload=True)
