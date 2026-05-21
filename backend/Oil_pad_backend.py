import os
import uuid
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
import torch
import math
from torchvision import transforms
import uvicorn
from PIL import Image
from torchvision.models.detection import MaskRCNN
from torchvision.models.detection.backbone_utils import resnet_fpn_backbone
import rasterio
from rasterio.transform import Affine
import numpy as np
from dotenv import load_dotenv
# Commented out since Mistral AI is not accessible in this context
from mistralai import Mistral
from torchvision.models.detection.transform import GeneralizedRCNNTransform
import cv2
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, shape
from shapely.validation import make_valid
from typing import Optional, Dict, Any, AnyStr
import tempfile
import zipfile
from fastapi.staticfiles import StaticFiles
import gc
import json  # Added for JSON handling
import rasterio.features  # Added for extracting shapes from masks
from fastapi.responses import FileResponse
import folium

from model_paths import artifact_dir, legacy_backend_models_dir, ensure_dir
from detection_postprocess import finalize_instance_detection_polygons

# Configure logging
logging.basicConfig(level=logging.DEBUG)  # Set logging level to DEBUG
logger = logging.getLogger(__name__)

load_dotenv()
api_key = os.getenv('MISTRAL_API_KEY')
if api_key is None:
    logger.warning("MISTRAL_API_KEY not set. Chat functionality will be limited.")

class ChatQuery(BaseModel):
    query: str
    tree_count: int = 0
    total_area: float = 0.0
    average_tree_area: Optional[float] = 0.0
    image_metadata: Optional[Dict[str, Any]] = {}

app = FastAPI()

# CORS settings
origins = [
    "http://localhost",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Consider restricting this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create necessary directories
os.makedirs('uploads', exist_ok=True)
os.makedirs('outputs', exist_ok=True)
os.makedirs('exports', exist_ok=True)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
logger.info(f"Using device: {device}")

# Weights: models/artifacts/oil_pad (or legacy backend/models when missing)
_MODEL_PRIMARY = artifact_dir("oil_pad")
_LEGACY = legacy_backend_models_dir()
ensure_dir(_MODEL_PRIMARY)
ensure_dir(_LEGACY)

# Cache to store loaded models to avoid reloading
loaded_models = {}

def get_detection_model(num_classes, in_channels):
    try:
        # Create a ResNet-50 backbone with FPN
        backbone = resnet_fpn_backbone(backbone_name='resnet50', weights=None)

        # Modify the conv1 layer to accept the specified number of input channels
        backbone.body.conv1 = torch.nn.Conv2d(
            in_channels=in_channels,
            out_channels=64,
            kernel_size=7,
            stride=2,
            padding=3,
            bias=False
        )

        # Create the MaskRCNN model
        model = MaskRCNN(backbone, num_classes=num_classes)
        return model
    except Exception as e:
        logger.error(f"Error creating detection model: {e}")
        raise RuntimeError("Failed to create the detection model.")

def load_model(model_name, in_channels):
    model_path = os.path.join(_MODEL_PRIMARY, model_name)
    if not os.path.exists(model_path):
        model_path = os.path.join(_LEGACY, model_name)
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"Model '{model_name}' not found in {_MODEL_PRIMARY} or legacy {_LEGACY}."
        )

    num_classes = 2  # 1 class (e.g., Oil Pad) + background
    model = get_detection_model(num_classes, in_channels)

    # Load the state_dict
    state_dict = torch.load(model_path, map_location=device)

    # If 'model' key exists in state_dict, use it
    if 'model' in state_dict:
        state_dict = state_dict['model']

    # Adjust the conv1 weights if input channels differ
    conv1_key = 'backbone.body.conv1.weight'
    if conv1_key in state_dict:
        conv1_weights = state_dict[conv1_key]
        if conv1_weights.shape[1] != in_channels:
            logger.info(f"Adjusting conv1 weights from {conv1_weights.shape[1]} to {in_channels} channels.")
            with torch.no_grad():
                if in_channels == 4 and conv1_weights.shape[1] == 3:
                    # Copy existing weights for the first 3 channels
                    weights_first3 = conv1_weights.detach().clone()
                    # Compute weights for the additional channel (e.g., mean over existing channels)
                    weights_extra = conv1_weights.mean(dim=1, keepdim=True).detach()
                    # Concatenate to form new weights
                    new_conv1_weights = torch.cat([weights_first3, weights_extra], dim=1)
                    state_dict[conv1_key] = new_conv1_weights
                elif in_channels == 3 and conv1_weights.shape[1] == 4:
                    # Reduce conv1 weights to 3 channels
                    new_conv1_weights = conv1_weights[:, :3, :, :].detach().clone()
                    state_dict[conv1_key] = new_conv1_weights
                else:
                    raise ValueError("Mismatch between model and state_dict input channels.")
    else:
        raise KeyError(f"Key '{conv1_key}' not found in state_dict.")

    # Load the adjusted state_dict into the model
    model.load_state_dict(state_dict)

    # Modify the model's internal transforms to handle the number of channels
    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]
    # Adjust mean and std for the number of channels
    if in_channels == 4:
        mean.append(0.5)  # Adjust this value based on your data
        std.append(0.25)  # Adjust this value based on your data
    model.transform = GeneralizedRCNNTransform(
        min_size=800,
        max_size=1333,
        image_mean=mean,
        image_std=std
    )
    logger.info(f"Updated model's internal transforms to handle {in_channels} channels.")

    model.to(device)
    model.eval()
    loaded_models[model_name] = model
    logger.info(f"Model '{model_name}' loaded and cached successfully.")
    return model

# Function to sanitize float values
def sanitize_float(value):
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        else:
            return None
    else:
        return value

# Function to sanitize coordinates in geometry
def sanitize_coordinates(coords):
    if isinstance(coords, (float, int)):
        if math.isfinite(coords):
            return coords
        else:
            return None
    elif isinstance(coords, (list, tuple)):
        return [sanitize_coordinates(c) for c in coords]
    else:
        return coords

def sanitize_geometry(geometry):
    if isinstance(geometry, dict):
        if 'coordinates' in geometry:
            coords = geometry['coordinates']
            sanitized_coords = sanitize_coordinates(coords)
            geometry['coordinates'] = sanitized_coords
        if 'geometries' in geometry:
            for geom in geometry['geometries']:
                sanitize_geometry(geom)
        if 'features' in geometry:
            for feature in geometry['features']:
                sanitize_geometry(feature)
    elif isinstance(geometry, list):
        for geom in geometry:
            sanitize_geometry(geom)
    return geometry

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, float):
            if math.isfinite(obj):
                return obj
            else:
                return None
        return super().default(obj)

# Custom JSONResponse class
from fastapi.responses import JSONResponse

class CustomJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,  # This will prevent NaN and Infinity values
            indent=None,
            separators=(",", ":"),
            cls=CustomJSONEncoder  # Use the custom encoder here
        ).encode("utf-8")

# Endpoint to get the list of available models
@app.get("/models")
async def list_models():
    try:
        seen: dict[str, None] = {}
        for d in (_MODEL_PRIMARY, _LEGACY):
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.endswith(".pth") and f not in seen:
                    seen[f] = None
        models = sorted(seen.keys())
        if not models:
            return JSONResponse(status_code=404, content={"message": "No models found."})
        return {"models": models}
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        return JSONResponse(status_code=500, content={"message": "Failed to list models."})

@app.post("/predict")
async def predict(
    image: UploadFile = File(...),
    model_name: str = Query(...),
    threshold: float = Query(0.5, ge=0.0, le=1.0)
):
    try:
        # Save uploaded image
        image_path = os.path.join('uploads', image.filename)
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        logger.info(f"Saved uploaded image to '{image_path}'.")
    except Exception as e:
        logger.error(f"Error saving uploaded image: {e}")
        return JSONResponse(status_code=500, content={"message": "Failed to save uploaded image."})

    try:
        # Read the image using Rasterio
        with rasterio.open(image_path) as src:
            img_array = src.read()  # Read all bands
            crs = src.crs
            transform_raster = src.transform
            original_width = src.width
            original_height = src.height
            logger.info(f"Image CRS: {crs}")
            logger.info(f"Image transform: {transform_raster}")
            logger.info(f"Original image size: {original_width} x {original_height}")
        logger.info(f"Read image '{image_path}' with Rasterio.")
    except Exception as e:
        logger.error(f"Error reading image with Rasterio: {e}")
        return JSONResponse(status_code=500, content={"message": "Failed to read image file."})

    # Determine the number of channels in the input image
    num_input_channels = img_array.shape[0]
    logger.info(f"Input image has {num_input_channels} channels.")

    # Ensure the image has either 3 or 4 channels
    if num_input_channels not in [3, 4]:
        logger.error("Input image must have 3 or 4 channels.")
        return JSONResponse(status_code=400, content={"message": "Input image must have 3 or 4 channels."})

    try:
        # Load the selected model with the correct number of input channels
        detection_model = load_model(model_name, num_input_channels)
    except FileNotFoundError as e:
        logger.error(f"Model not found: {e}")
        return JSONResponse(status_code=404, content={"message": str(e)})
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        return JSONResponse(status_code=500, content={"message": "Failed to load the selected model."})

    try:
        # Adjust the image array to have the correct number of channels
        if img_array.shape[0] > num_input_channels:
            img_array = img_array[:num_input_channels, :, :]
            logger.info(f"Truncated image to first {num_input_channels} bands.")
        elif img_array.shape[0] < num_input_channels:
            channels_needed = num_input_channels - img_array.shape[0]
            extra_channels = np.repeat(img_array[0:1, :, :], channels_needed, axis=0)
            img_array = np.concatenate((img_array, extra_channels), axis=0)
            logger.info(f"Duplicated first band to make {num_input_channels} bands.")

        # Convert NumPy array to PIL Image for compatibility with transforms
        img_array_transposed = np.transpose(img_array, (1, 2, 0))
        # Normalize the image array to uint8 if necessary
        if img_array_transposed.dtype != np.uint8:
            img_min = img_array_transposed.min()
            img_max = img_array_transposed.max()
            if img_max - img_min == 0:
                logger.error("Image has zero dynamic range.")
                return JSONResponse(status_code=400, content={"message": "Image has zero dynamic range."})
            img_array_transposed = ((img_array_transposed - img_min) / (img_max - img_min) * 255).astype(np.uint8)
            logger.info("Normalized image array to uint8.")
        img_pil = Image.fromarray(img_array_transposed)
        logger.info("Converted NumPy array to PIL Image.")
    except Exception as e:
        logger.error(f"Error processing image array: {e}")
        return JSONResponse(status_code=500, content={"message": "Failed to process image data."})

    try:
        # Image preprocessing transforms
        transform = transforms.ToTensor()
        logger.info("Defined image preprocessing transforms.")

        # Define tile size and overlap
        tile_size = 1024  # Reduced from 4096 to 1024
        overlap = 100  # Overlap between tiles to avoid edge effects

        # Calculate number of tiles in each dimension
        n_tiles_x = math.ceil((original_width - overlap) / (tile_size - overlap))
        n_tiles_y = math.ceil((original_height - overlap) / (tile_size - overlap))
        logger.info(f"Tiling image into {n_tiles_x} x {n_tiles_y} tiles.")

        # Initialize lists to store detections from all tiles
        all_polygons = []
        all_areas = []
        mask_overlay = np.zeros((original_height, original_width), dtype=np.uint8)

        # Loop over tiles
        for i in range(n_tiles_x):
            for j in range(n_tiles_y):
                # Calculate tile boundaries with overlap
                x_start = i * (tile_size - overlap)
                y_start = j * (tile_size - overlap)
                x_end = min(x_start + tile_size, original_width)
                y_end = min(y_start + tile_size, original_height)

                # Crop the tile from the image
                tile = img_pil.crop((x_start, y_start, x_end, y_end))

                # Apply transformations
                input_tensor = transform(tile).to(device)
                logger.info(f"Processing tile at position ({i}, {j}) with shape {input_tensor.shape}.")

                # Perform inference with no gradient calculation
                with torch.no_grad():
                    outputs = detection_model([input_tensor])[0]

                # Process outputs to get masks and scores
                scores = outputs['scores'].cpu().numpy()
                masks = outputs['masks']  # Keep on device

                # Filter out detections based on the dynamic threshold
                selected_indices = scores >= threshold
                scores = scores[selected_indices]
                masks = masks[selected_indices]

                for k in range(len(scores)):
                    mask = masks[k][0]  # Shape: [H, W]

                    # Move mask to CPU and convert to numpy
                    mask = mask.cpu().numpy()

                    # Threshold the mask at 0.5 and convert to uint8
                    mask = (mask >= 0.5).astype(np.uint8)

                    # Resize mask to tile size if necessary
                    mask_height, mask_width = mask.shape
                    if (mask_height, mask_width) != (tile.size[1], tile.size[0]):
                        mask = cv2.resize(mask, (tile.size[0], tile.size[1]), interpolation=cv2.INTER_NEAREST)

                    # Place the mask in the correct position in the full-size mask
                    mask_full = np.zeros((original_height, original_width), dtype=np.uint8)
                    mask_full[y_start:y_end, x_start:x_end] = mask

                    # For visualization, add the mask to the overlay
                    mask_overlay = cv2.bitwise_or(mask_overlay, mask_full * 255)

                    # **Modified code starts here**
                    # Use rasterio.features.shapes to extract geometries
                    mask_full_binary = (mask_full > 0).astype(np.uint8)
                    shapes = list(rasterio.features.shapes(mask_full_binary, transform=transform_raster))
                    logger.debug(f"Number of shapes extracted: {len(shapes)}")

                    for geom, value in shapes:
                        if value == 1:
                            try:
                                polygon = shape(geom)
                                # Validate and fix the polygon
                                if not polygon.is_valid:
                                    polygon = make_valid(polygon)
                                    if polygon.is_empty:
                                        logger.debug("Polygon is empty after validation. Skipping.")
                                        continue  # Skip invalid geometries
                                if polygon.area == 0:
                                    logger.debug("Polygon has zero area. Skipping.")
                                    continue
                                # Optionally, filter out small polygons
                                MIN_AREA_THRESHOLD = 1e-6  # Adjust as needed
                                if polygon.area < MIN_AREA_THRESHOLD:
                                    logger.debug(f"Polygon area {polygon.area} below threshold. Skipping.")
                                    continue
                                all_polygons.append(polygon)
                                all_areas.append(polygon.area)
                                logger.debug(f"Polygon added with area: {polygon.area}")
                            except Exception as e:
                                logger.error(f"Error creating polygon: {e}")
                                continue

                    # Clear variables to free memory
                    del mask, mask_full, mask_full_binary, shapes
                    gc.collect()

                # Clear outputs to free memory
                del outputs, scores, masks
                gc.collect()

        # **Modified code continues here**
        # After processing all tiles
        logger.info(f"Total number of polygons collected: {len(all_polygons)}")

        # Validate polygons; dedupe tile overlap; keep separate buildings by default
        valid_polygons = [poly for poly in all_polygons if poly.is_valid and not poly.is_empty]
        merged_polygons = finalize_instance_detection_polygons(valid_polygons)
        logger.info(f"Polygons after post-processing: {len(merged_polygons)}")

        gdf = gpd.GeoDataFrame(geometry=merged_polygons, crs=crs)

        # Calculate shape_area and shape_length
        gdf['shape_area'] = gdf.geometry.area
        gdf['shape_length'] = gdf.geometry.length

        # Extract coordinates and store them as strings to prevent them from being treated as geometry
        gdf['coordinates'] = gdf.geometry.apply(
            lambda geom: list(geom.exterior.coords) if geom.exterior else []
        )
        gdf['coordinates'] = gdf['coordinates'].apply(str)  # Convert list to string

        # Ensure only one geometry column exists
        geometry_columns = gdf.select_dtypes(include=['geometry']).columns.tolist()
        if len(geometry_columns) > 1:
            # Keep only the active geometry column
            geometry_columns.remove(gdf.geometry.name)
            gdf = gdf.drop(columns=geometry_columns)
            logger.info(f"Dropped additional geometry columns: {geometry_columns}")

        # Recalculate total_area and tree_count after merging
        total_area = gdf['shape_area'].sum()
        tree_count = len(gdf)
        logger.info(f"Calculated total area from masks: {total_area}")

        # Proceed to save the GeoDataFrame as before
        bounds = gdf.total_bounds if not gdf.empty else [0, 0, 0, 0]
        unique_id = uuid.uuid4().hex
        geojson_filename = f"detections_{unique_id}.geojson"
        shapefile_zip_filename = f"detections_{unique_id}.zip"
        image_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]  # [[south, west], [north, east]]
        detection_geojson = gdf.__geo_interface__

        # Save the GeoJSON file
        output_vector_path = os.path.join('outputs', geojson_filename)
        if not gdf.empty:
            gdf.to_file(output_vector_path, driver='GeoJSON')
            logger.info(f"Saved detections to '{output_vector_path}'.")
        else:
            logger.warning("GeoDataFrame is empty. No GeoJSON file was saved.")

        # Save and zip the Shapefile
        try:
            if not gdf.empty:
                with tempfile.TemporaryDirectory() as tmpdirname:
                    shapefile_base = f"detections_{unique_id}"
                    shapefile_path = os.path.join(tmpdirname, shapefile_base + '.shp')
                    gdf.to_file(shapefile_path)
                    shapefile_components = os.listdir(tmpdirname)
                    logger.info(f"Shapefile components: {shapefile_components}")

                    shapefile_zip_path = os.path.join('outputs', shapefile_zip_filename)
                    with zipfile.ZipFile(shapefile_zip_path, 'w') as zipf:
                        for file in shapefile_components:
                            file_path = os.path.join(tmpdirname, file)
                            zipf.write(file_path, arcname=file)
                            logger.info(f"Added '{file}' to zip.")
                    logger.info(f"Saved shapefile zip to '{shapefile_zip_path}'.")
            else:
                logger.warning("GeoDataFrame is empty. No shapefile was saved.")
        except Exception as e:
            logger.error(f"Error saving shapefile: {e}")
            # Handle error appropriately

        # For visualization, overlay the masks on the image
        img_rgb = np.array(img_pil.convert('RGB'))  # Convert to RGB
        # Create a colored mask
        colored_mask = np.zeros_like(img_rgb)
        colored_mask[:, :, 1] = mask_overlay  # Highlight in green
        # Overlay the mask on the image
        overlayed_image = cv2.addWeighted(img_rgb, 1.0, colored_mask, 0.5, 0)

        # Save the output image
        output_image_path = os.path.join('outputs', f'overlay_{image.filename}.png')
        cv2.imwrite(output_image_path, cv2.cvtColor(overlayed_image, cv2.COLOR_RGB2BGR))
        logger.info(f"Saved overlay image to '{output_image_path}'.")

        # Read image bytes
        with open(output_image_path, "rb") as image_file:
            image_bytes = image_file.read()

        # Safeguard against invalid total_area and tree_count
        if tree_count > 0 and math.isfinite(total_area):
            average_tree_area = total_area / tree_count
        else:
            average_tree_area = 0.0

        # Sanitize detection data
        sanitized_detection_data = sanitize_geometry(detection_geojson)

        # Build the response data
        response_data = {
            "tree_count": tree_count,
            "total_area": sanitize_float(total_area),
            "average_tree_area": sanitize_float(average_tree_area),
            "image": image_bytes.hex(),  # Convert bytes to hex string
            "geojson_filename": geojson_filename if not gdf.empty else None,
            "shapefile_filename": shapefile_zip_filename if not gdf.empty else None,
            "image_width": original_width,
            "image_height": original_height,
            "crs": crs.to_string() if crs else "N/A",
            "transform": str(transform_raster) if transform_raster else "N/A",
            "image_bounds": image_bounds,
            "detection_data": sanitized_detection_data if not gdf.empty else None,
        }

        # Return the response using the custom response class
        return CustomJSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"Error processing model outputs: {e}")
        return JSONResponse(status_code=500, content={"message": "Failed to process model outputs."})

@app.get("/download/geojson/{filename}")
async def download_geojson(filename: str):
    file_path = os.path.join('outputs', filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, media_type='application/geo+json', filename=filename)
    else:
        return JSONResponse(status_code=404, content={"message": "GeoJSON file not found."})

@app.get("/download/shapefile/{filename}")
async def download_shapefile(filename: str):
    file_path = os.path.join('outputs', filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, media_type='application/zip', filename=filename)
    else:
        return JSONResponse(status_code=404, content={"message": "Shapefile zip not found."})

@app.post("/chat/")
async def chat_with_model(query: ChatQuery):
    try:
        user_query = query.query.lower()
        response = ""

        # Safeguard against division by zero
        if query.tree_count > 0 and math.isfinite(query.total_area):
            average_tree_area = query.average_tree_area if query.average_tree_area else query.total_area / query.tree_count
        else:
            average_tree_area = 0.0

        # Safeguard for image_metadata
        metadata = query.image_metadata if query.image_metadata else {}

        # Handle queries about tree count
        if any(keyword in user_query for keyword in ["how many oil pads", "oil pads count", "number of oil pads"]):
            response = f"There are {query.tree_count} oil pad detected in the satellite imagery."

        # Handle queries about total area
        elif any(keyword in user_query for keyword in ["total area", "area covered", "overall area"]):
            response = f"The total area covered by the detected trees is {query.total_area:.2f} square meters."

        # Handle queries about average tree area
        elif any(keyword in user_query for keyword in ["average tree area", "average area per tree"]):
            response = f"The average area per tree is {average_tree_area:.2f} square meters."

        # Handle queries about image metadata
        elif "image metadata" in user_query or "image info" in user_query:
            response = (
                f"Image Metadata:\n"
                f"Width: {metadata.get('width', 'N/A')} pixels\n"
                f"Height: {metadata.get('height', 'N/A')} pixels\n"
                f"CRS: {metadata.get('crs', 'N/A')}\n"
                f"Transform: {metadata.get('transform', 'N/A')}"
            )
        else:
            if not api_key:
                response = "Chat functionality is not available because the API key is not set."
            else:
                client = Mistral(api_key=api_key)
                model = "mistral-large-latest"
                chat_context = (
                    f"You are an AI assistant that provides information about GeoAI and Geographic Information Systems. "
                    f"Your responses should be informative and helpful. "
                    f"Your responses should be in the form of a natural language sentence. "
                    f"Use only the following information: {query.query}"
                    f"Your response should be pretty clear and concise. "
                )
                messages = [
                    {"role": "system", "content": chat_context},
                    {"role": "user", "content": query.query}
                ]
                chat_response = client.chat.complete(
                    model=model,
                    messages=messages,
                    temperature=0.9,

                )
                response = chat_response.choices[0].message.content.strip()

        return {"query": query.query, "response": response}
        # Handle other queries
    except Exception as e:
        logger.error(f"Error in /chat endpoint: {e}")
        return JSONResponse(status_code=500, content={"message": "An error occurred during chat processing."})
        # Handle other queries
# Mount StaticFiles to serve the outputs directory
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
# app.mount("/generated_maps", StaticFiles(directory=MAP_DIR), name="generated_maps")
# app.mount("/uploaded_images", StaticFiles(directory=UPLOAD_DIR), name="uploaded_images")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
