"""
Flask server for Land Cover Classification with HTML/Leaflet UI.
Run: python server.py
Then open http://127.0.0.1:5000
"""
import os
import sys

_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)
from proj_runtime import clear_bad_proj_env

clear_bad_proj_env()

from sse_json import sse_json_dumps
from prediction_archive import write_lulc_manifest
from roi_geotiff_clip import _bbox_indices_from_mask

import base64
import io
import json
import tempfile
import time
import uuid
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
import numpy as np
from PIL import Image

# Load model and helpers from app (model loads once at import; model is on GPU when available)
from app import (
    load_image_from_path,
    raster_bands_to_pil_rgb,
    processor,
    model,
    draw_predictions_on_image,
    segment_and_draw,
    segment_and_draw_streaming,
    ID2LABEL,
    _to_device,
    CLASS_GRID_NODATA,
    class_grid_to_prediction_png_bytes,
)
import torch

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
PREDICTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions")
PREVIEW_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview_cache")
PREVIEW_MAX_AGE_SECONDS = 3600  # 1 hour

# Prefer EPSG registry over GeoTIFF geokeys for CRS; reduces PROJ/GDAL reprojection errors on Windows.
os.environ.setdefault("GTIFF_SRS_SOURCE", "EPSG")

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

if not os.path.isdir(PREDICTIONS_DIR):
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)
if not os.path.isdir(PREVIEW_CACHE_DIR):
    os.makedirs(PREVIEW_CACHE_DIR, exist_ok=True)


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large. Maximum size is 2 GB."}), 413


def _parse_crs_from_aux_xml(tiff_path):
    """Try to get CRS from .tif.aux.xml sidecar (GDAL PAM or ESRI format). Returns rasterio CRS or None."""
    import re
    import rasterio
    aux_path = tiff_path + ".aux.xml"
    if not os.path.isfile(aux_path):
        return None
    try:
        with open(aux_path, "rb") as f:
            raw = f.read().decode("utf-8", errors="ignore")
        # 1) ESRI / ArcGIS: <WKID>32638</WKID> or <LatestWKID>32638</LatestWKID>
        wkid_match = re.search(r"<(?:(?:Latest)?WKID|wkid)>(\d+)</(?:(?:Latest)?WKID|wkid)>", raw, re.I)
        if wkid_match:
            epsg = int(wkid_match.group(1))
            return rasterio.crs.CRS.from_epsg(epsg)
        # 2) WKT in XML: <Projection>PROJCS[...]</Projection> or <WKT>...</WKT> or inline PROJCS/GEOGCS
        for marker in ("PROJCS[", "GEOGCS["):
            if marker in raw:
                start = raw.find(marker)
                if start < 0:
                    continue
                depth = 0
                end = start
                for i in range(start, len(raw)):
                    if raw[i] == "[":
                        depth += 1
                    elif raw[i] == "]":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                wkt = raw[start:end]
                if len(wkt) > 10:
                    return rasterio.crs.CRS.from_string(wkt)
                break
        # 3) GDAL PAM: <Projection>...</Projection> or element with WKT text
        import xml.etree.ElementTree as ET
        tree = ET.parse(aux_path)
        for elem in tree.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("Projection", "SRS", "WKT", "SpatialReference"):
                if elem.text and ("PROJCS" in elem.text or "GEOGCS" in elem.text):
                    return rasterio.crs.CRS.from_string(elem.text.strip())
                for child in elem.iter():
                    if child.text and ("PROJCS" in child.text or "GEOGCS" in child.text):
                        return rasterio.crs.CRS.from_string(child.text.strip())
    except Exception:
        pass
    return None


def _bounds_from_tfw(tiff_path):
    """Read .tfw and image size to get bounds (left, bottom, right, top) in file CRS. Returns None on failure."""
    base = tiff_path.rsplit(".", 1)[0]
    tfw_path = base + ".tfw"
    if not os.path.isfile(tfw_path):
        tfw_path = base + ".tifw"
    if not os.path.isfile(tfw_path):
        return None
    try:
        with open(tfw_path) as f:
            lines = [f.readline().strip() for _ in range(6)]
        if len(lines) < 6:
            return None
        px_w = float(lines[0])
        px_h = float(lines[3])  # usually negative for north-up
        origin_x = float(lines[4])
        origin_y = float(lines[5])
        import rasterio
        with rasterio.open(tiff_path) as src:
            w, h = src.width, src.height
        # World file: (4,5) = center of top-left pixel
        left = origin_x - 0.5 * px_w
        top = origin_y + 0.5 * abs(px_h)
        right = left + w * abs(px_w)
        bottom = top - h * abs(px_h)
        return (left, bottom, right, top)
    except Exception:
        return None


def _transform_bounds_to_wgs84(left, bottom, right, top, crs):
    """Transform bounds to WGS84. Uses rasterio.warp first, then pyproj with CRS WKT/EPSG."""
    try:
        from rasterio.warp import transform_bounds
        w, s, e, n = transform_bounds(crs, "EPSG:4326", left, bottom, right, top)
        return [float(s), float(w), float(n), float(e)]
    except Exception:
        pass
    try:
        from pyproj import Transformer
        # Use EPSG if available, else WKT so any CRS works
        try:
            epsg = crs.to_epsg()
            src_crs = "EPSG:{}".format(epsg) if epsg else (crs.wkt if hasattr(crs, "wkt") else str(crs))
        except Exception:
            src_crs = crs.wkt if hasattr(crs, "wkt") else str(crs)
        trans = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
        # Transform all four corners (bounds can be rotated)
        w1, s1 = trans.transform(left, bottom)
        w2, s2 = trans.transform(right, bottom)
        w3, s3 = trans.transform(right, top)
        w4, s4 = trans.transform(left, top)
        west = min(w1, w2, w3, w4)
        east = max(w1, w2, w3, w4)
        south = min(s1, s2, s3, s4)
        north = max(s1, s2, s3, s4)
        return [float(south), float(west), float(north), float(east)]
    except Exception:
        return None


def _crs_to_display_string(crs):
    """Return a short human-readable CRS label for the UI (e.g. 'EPSG:32639' or WKT snippet)."""
    if crs is None:
        return None
    try:
        import rasterio
        # Prefer EPSG code if available
        if crs.to_epsg():
            return "EPSG:{}".format(crs.to_epsg())
        # Else use WKT, truncated if very long
        wkt = crs.wkt if hasattr(crs, "wkt") else str(crs)
        if len(wkt) > 80:
            return wkt[:77] + "..."
        return wkt
    except Exception:
        return str(crs) if crs else None


def get_geobounds(tiff_path):
    """Get geographic bounds in WGS84 [south, west, north, east] for Leaflet and CRS display string.
    Returns (bounds_list, crs_display) or (None, crs_display). Uses rasterio transform when bounds are pixel-like."""
    try:
        import rasterio
        from rasterio.transform import array_bounds
        with rasterio.open(tiff_path) as src:
            width, height = src.width, src.height
            transform = src.transform
            crs = src.crs
            left, bottom, right, top = src.bounds

            # If bounds look like pixel coords (0,0,w,h or ~pixel size), compute from affine transform
            # so we get correct geographic bounds from the GeoTIFF's internal transform (no .tfw needed).
            pixel_like = (
                (abs((right - left) - width) < 1 and abs((top - bottom) - height) < 1)
                or (left == 0 and bottom == 0)
                or (abs(left) < 1e-6 and abs(bottom) < 1e-6 and right <= width + 1 and top <= height + 1)
            )
            if pixel_like and transform is not None:
                try:
                    left, bottom, right, top = array_bounds(height, width, transform)
                except Exception:
                    bounds_tfw = _bounds_from_tfw(tiff_path)
                    if bounds_tfw is not None:
                        left, bottom, right, top = bounds_tfw
            elif pixel_like:
                bounds_tfw = _bounds_from_tfw(tiff_path)
                if bounds_tfw is not None:
                    left, bottom, right, top = bounds_tfw

            if crs is None:
                crs = _parse_crs_from_aux_xml(tiff_path)

            crs_display = _crs_to_display_string(crs)

            if crs is not None:
                result = _transform_bounds_to_wgs84(left, bottom, right, top, crs)
                if result is not None:
                    return result, crs_display

            # No CRS or transform failed: if bounds already look like lon/lat (degrees), use as WGS84
            if -180 <= left <= 180 and -180 <= right <= 180 and -90 <= bottom <= 90 and -90 <= top <= 90:
                return [float(bottom), float(left), float(top), float(right)], crs_display or "WGS 84 (assumed)"

            # Try .tfw + aux CRS or UTM guess
            bounds_tfw = _bounds_from_tfw(tiff_path)
            if bounds_tfw is not None:
                left, bottom, right, top = bounds_tfw
                if crs is None:
                    crs = _parse_crs_from_aux_xml(tiff_path)
                if crs is None:
                    for epsg in (32639, 32638, 32640, 32641, 32637):
                        try:
                            crs = rasterio.crs.CRS.from_epsg(epsg)
                            result = _transform_bounds_to_wgs84(left, bottom, right, top, crs)
                            if result is not None and -90 <= result[0] <= 90 and -180 <= result[1] <= 180:
                                return result, _crs_to_display_string(crs)
                        except Exception:
                            continue
                else:
                    result = _transform_bounds_to_wgs84(left, bottom, right, top, crs)
                    if result is not None:
                        return result, crs_display
                if -180 <= left <= 180 and -180 <= right <= 180 and -90 <= bottom <= 90 and -90 <= top <= 90:
                    return [float(bottom), float(left), float(top), float(right)], crs_display or "WGS 84 (assumed)"
            return None, crs_display
    except Exception:
        return None, None


def _get_geo_meta(tiff_path):
    """Get (transform, crs, width, height) from a GeoTIFF for writing a matching output. Returns None if not available."""
    try:
        import rasterio
        with rasterio.open(tiff_path) as src:
            return (src.transform, src.crs, src.width, src.height)
    except Exception:
        return None


def _write_annotation_geotiff(source_tiff_path, annotation_png_bytes, output_tif_path):
    """Write annotation image (PNG bytes) as a GeoTIFF with same transform/CRS as source. Returns True on success."""
    try:
        import rasterio
        meta = _get_geo_meta(source_tiff_path)
        if meta is None:
            return False
        transform, crs, src_width, src_height = meta
        img = Image.open(io.BytesIO(annotation_png_bytes))
        arr = np.array(img)
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        height, width = arr.shape[0], arr.shape[1]
        if (width, height) != (src_width, src_height):
            img = img.resize((src_width, src_height), Image.Resampling.LANCZOS)
            arr = np.array(img)
            if arr.ndim == 2:
                arr = np.stack([arr, arr, arr], axis=-1)
            height, width = arr.shape[0], arr.shape[1]
        # rasterio: (count, height, width)
        data = np.transpose(arr[:, :, :3], (2, 0, 1))
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 3,
            "dtype": data.dtype,
            "transform": transform,
            "compress": "lzw",
        }
        if crs is not None:
            profile["crs"] = crs
        with rasterio.open(output_tif_path, "w", **profile) as dst:
            dst.write(data)
        return True
    except Exception as e:
        print(f"[server] GeoTIFF write failed: {e}", flush=True)
        return False


def _resize_class_grid_nearest(class_arr: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    """Match RGB GeoTIFF behavior: inference uses SEG_MAX_PX downscale; upsample labels with nearest neighbor."""
    data = np.asarray(class_arr, dtype=np.uint8)
    if data.ndim != 2:
        return data
    h, w = int(data.shape[0]), int(data.shape[1])
    if h == out_h and w == out_w:
        return data
    im = Image.fromarray(data, mode="L")
    im = im.resize((out_w, out_h), Image.Resampling.NEAREST)
    return np.asarray(im, dtype=np.uint8)


def _write_class_geotiff_from_array(source_tiff_path, class_arr, output_tif_path, nodata=255):
    """Write uint8 class index array (H,W) as 1-band GeoTIFF, same georef as source RGB output flow."""
    try:
        import rasterio

        meta = _get_geo_meta(source_tiff_path)
        if meta is None:
            return False
        transform, crs, src_width, src_height = meta
        data = np.asarray(class_arr, dtype=np.uint8)
        if data.ndim != 2:
            return False
        data = _resize_class_grid_nearest(data, int(src_height), int(src_width))
        h, w = int(data.shape[0]), int(data.shape[1])
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
        with rasterio.open(output_tif_path, "w", **profile) as dst:
            dst.write(data, 1)
        return True
    except Exception as e:
        print(f"[server] class GeoTIFF write failed: {e}", flush=True)
        return False


def _write_class_geotiff_cropped(class_arr, output_tif_path, transform, crs, width, height, nodata=255):
    """1-band class GeoTIFF with explicit transform (ROI / crop path)."""
    try:
        import rasterio

        data = np.asarray(class_arr, dtype=np.uint8)
        if data.ndim != 2:
            return False
        data = _resize_class_grid_nearest(data, int(height), int(width))
        profile = {
            "driver": "GTiff",
            "height": int(height),
            "width": int(width),
            "count": 1,
            "dtype": "uint8",
            "transform": transform,
            "compress": "lzw",
            "nodata": int(nodata),
        }
        if crs is not None:
            profile["crs"] = crs
        with rasterio.open(output_tif_path, "w", **profile) as dst:
            dst.write(data, 1)
        return True
    except Exception as e:
        print(f"[server] cropped class GeoTIFF write failed: {e}", flush=True)
        return False


def _write_annotation_geotiff_cropped(annotation_png_bytes, output_tif_path, transform, crs, width, height):
    """Write annotation PNG as GeoTIFF using an explicit geotransform (e.g. ROI crop). Resizes PNG to width×height if needed."""
    try:
        import rasterio
        img = Image.open(io.BytesIO(annotation_png_bytes))
        arr = np.array(img)
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        ah, aw = arr.shape[0], arr.shape[1]
        if (aw, ah) != (width, height):
            img = img.resize((width, height), Image.Resampling.LANCZOS)
            arr = np.array(img)
            if arr.ndim == 2:
                arr = np.stack([arr, arr, arr], axis=-1)
        data = np.transpose(arr[:, :, :3], (2, 0, 1))
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 3,
            "dtype": data.dtype,
            "transform": transform,
            "compress": "lzw",
        }
        if crs is not None:
            profile["crs"] = crs
        with rasterio.open(output_tif_path, "w", **profile) as dst:
            dst.write(data)
        return True
    except Exception as e:
        print(f"[server] Cropped GeoTIFF write failed: {e}", flush=True)
        return False


def _geometry_polygon_from_roi_geojson(geojson_str):
    """Return a GeoJSON Polygon geometry dict from string (Polygon, Feature, or FeatureCollection)."""
    obj = json.loads(geojson_str)
    t = obj.get("type")
    if t == "Polygon":
        return obj
    if t == "Feature":
        g = obj.get("geometry")
        if g and g.get("type") == "Polygon":
            return g
    if t == "FeatureCollection":
        for f in obj.get("features") or []:
            g = f.get("geometry") if isinstance(f, dict) else None
            if g and g.get("type") == "Polygon":
                return g
    raise ValueError("ROI must be GeoJSON Polygon (or Feature / FeatureCollection with one Polygon)")


def _resolve_crs_for_roi(tif_path, src):
    """
    Match get_geobounds heuristics: embedded CRS, aux.xml, WGS84-like bounds, .tfw + UTM guess.
    Returns rasterio.crs.CRS or None.
    """
    import rasterio
    from rasterio.transform import array_bounds

    crs = src.crs
    if crs is not None:
        return crs

    crs = _parse_crs_from_aux_xml(tif_path)
    if crs is not None:
        return crs

    width, height = src.width, src.height
    transform = src.transform
    left, bottom, right, top = src.bounds

    pixel_like = (
        (abs((right - left) - width) < 1 and abs((top - bottom) - height) < 1)
        or (left == 0 and bottom == 0)
        or (abs(left) < 1e-6 and abs(bottom) < 1e-6 and right <= width + 1 and top <= height + 1)
    )
    if pixel_like and transform is not None:
        try:
            left, bottom, right, top = array_bounds(height, width, transform)
        except Exception:
            bounds_tfw = _bounds_from_tfw(tif_path)
            if bounds_tfw is not None:
                left, bottom, right, top = bounds_tfw
    elif pixel_like:
        bounds_tfw = _bounds_from_tfw(tif_path)
        if bounds_tfw is not None:
            left, bottom, right, top = bounds_tfw

    def _looks_like_wgs84_degrees(l, b, r, t):
        return (
            -180 <= l <= 180
            and -180 <= r <= 180
            and -90 <= b <= 90
            and -90 <= t <= 90
            and l < r
        )

    if _looks_like_wgs84_degrees(left, bottom, right, top):
        return rasterio.crs.CRS.from_epsg(4326)

    bounds_tfw = _bounds_from_tfw(tif_path)
    if bounds_tfw is not None:
        l, b, r, t = bounds_tfw
        crs2 = _parse_crs_from_aux_xml(tif_path)
        if crs2 is not None:
            return crs2
        if _looks_like_wgs84_degrees(l, b, r, t):
            return rasterio.crs.CRS.from_epsg(4326)
        for epsg in (32639, 32638, 32640, 32641, 32637, 32642, 32643, 32644, 32645, 32646):
            try:
                test_crs = rasterio.crs.CRS.from_epsg(epsg)
                result = _transform_bounds_to_wgs84(l, b, r, t, test_crs)
                if result is not None and -90 <= result[0] <= 90 and -180 <= result[1] <= 180:
                    return test_crs
            except Exception:
                continue

    # Affine geotransform set but no CRS tag (GDAL often still has correct transform)
    if src.transform is not None:
        try:
            l, b, r, t = array_bounds(src.height, src.width, src.transform)
        except Exception:
            l, b, r, t = src.bounds
        if _looks_like_wgs84_degrees(l, b, r, t):
            return rasterio.crs.CRS.from_epsg(4326)
        for epsg in (32639, 32638, 32640, 32641, 32637, 32642, 32643, 32644, 32645, 32646):
            try:
                test_crs = rasterio.crs.CRS.from_epsg(epsg)
                result = _transform_bounds_to_wgs84(l, b, r, t, test_crs)
                if result is not None and -90 <= result[0] <= 90 and -180 <= result[1] <= 180:
                    return test_crs
            except Exception:
                continue

    return None


def _extract_roi_rgb_pil_and_georef(tif_path, geometry_4326):
    """
    Clip GeoTIFF to polygon in WGS84. Returns (pil_rgb, wgs84_bounds_swne, out_transform, crs, width, height).
    wgs84_bounds: [south, west, north, east] for Leaflet (same as get_geobounds).

    When the file has no CRS tag (common with .tfw-only), we infer CRS like get_geobounds and run mask()
    on a small in-memory GeoTIFF window so rasterio accepts the CRS.
    """
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.mask import mask
    from rasterio.transform import array_bounds
    from rasterio.warp import transform_bounds, transform_geom
    from rasterio.windows import Window, from_bounds
    from shapely.geometry import shape

    with rasterio.open(tif_path) as src:
        resolved_crs = _resolve_crs_for_roi(tif_path, src)
        if resolved_crs is None:
            raise ValueError(
                "GeoTIFF has no usable CRS for ROI clipping. Add a CRS (GeoTIFF tags, .prj, or .tif.aux.xml) "
                "or a .tfw world file with a known projection (e.g. UTM)."
            )

        try:
            geom_src = transform_geom("EPSG:4326", resolved_crs, geometry_4326)
        except Exception as e:
            raise ValueError(f"Could not project ROI into raster CRS: {e}") from e

        n = min(3, src.count)
        if n < 1:
            raise ValueError("GeoTIFF has no bands")

        geom_shp = shape(geom_src)
        minx, miny, maxx, maxy = geom_shp.bounds
        if minx >= maxx or miny >= maxy:
            raise ValueError("Invalid ROI geometry after projection")

        try:
            win = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        except Exception as e:
            raise ValueError(f"ROI bounds do not map to this raster: {e}") from e

        full = Window(0, 0, src.width, src.height)
        try:
            win = win.intersection(full)
        except Exception:
            win = None
        if win is None or win.width <= 0 or win.height <= 0:
            raise ValueError("ROI does not overlap this raster")

        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        if win.width <= 0 or win.height <= 0:
            raise ValueError("ROI does not overlap this raster")

        indexes = list(range(1, n + 1))
        data = src.read(indexes=indexes, window=win)
        wt = rasterio.windows.transform(win, src.transform)

    profile = {
        "driver": "GTiff",
        "height": int(win.height),
        "width": int(win.width),
        "count": n,
        "dtype": data.dtype,
        "crs": resolved_crs,
        "transform": wt,
    }
    try:
        with MemoryFile() as mem:
            with mem.open(**profile) as dst:
                dst.write(data)
            with mem.open() as src_mem:
                try:
                    out_image, out_transform = mask(
                        src_mem,
                        [geom_src],
                        crop=True,
                        all_touched=True,
                        filled=True,
                        nodata=0,
                        indexes=list(range(1, n + 1)),
                    )
                except ValueError as e:
                    raise ValueError(f"ROI does not overlap this raster: {e}") from e
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"ROI clip failed: {e}") from e

    if out_image.size == 0 or out_image.shape[1] == 0 or out_image.shape[2] == 0:
        raise ValueError("ROI clip produced an empty image")

    pil_rgb = raster_bands_to_pil_rgb(out_image)
    if pil_rgb is None:
        raise ValueError("Could not build RGB image from ROI clip")

    h, w = out_image.shape[1], out_image.shape[2]
    left, bottom, right, top = array_bounds(h, w, out_transform)
    try:
        west, south, east, north = transform_bounds(resolved_crs, "EPSG:4326", left, bottom, right, top)
    except Exception as e:
        raise ValueError(f"Could not transform ROI bounds to WGS84: {e}") from e
    wgs84_bounds = [float(south), float(west), float(north), float(east)]
    return pil_rgb, wgs84_bounds, out_transform, resolved_crs, w, h


def _parse_roi_full_bounds_swne(form_value):
    """Parse JSON [south, west, north, east] from multipart form."""
    if not form_value:
        return None
    s = str(form_value).strip()
    if not s:
        return None
    try:
        arr = json.loads(s)
        if isinstance(arr, list) and len(arr) == 4:
            return [float(arr[0]), float(arr[1]), float(arr[2]), float(arr[3])]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _extract_roi_rgb_plate_carree(tif_path, geometry_4326, bounds_swne):
    """
    Clip ROI using linear lon/lat → pixel mapping (plate carrée over full image).
    Avoids GDAL/PROJ on the server when client sends the same WGS84 extent as the map (georaster).
    Returns same tuple as _extract_roi_rgb_pil_and_georef.
    crs is None so we never call PROJ/EPSG database (broken PROJ_LIB on some machines); bounds are still WGS84-like degrees from the map grid.
    """
    import rasterio
    from rasterio.transform import from_bounds
    from PIL import Image, ImageDraw

    south, west, north, east = bounds_swne
    if east <= west or north <= south:
        raise ValueError("roi_full_bounds_swne must be [south, west, north, east] with positive span")

    with rasterio.open(tif_path) as src:
        n = min(3, src.count)
        if n < 1:
            raise ValueError("GeoTIFF has no bands")
        data = src.read(list(range(1, n + 1)))

    pil_full = raster_bands_to_pil_rgb(data)
    if pil_full is None:
        raise ValueError("Could not read GeoTIFF as RGB")
    arr = np.asarray(pil_full.convert("RGB"))
    h, w = arr.shape[0], arr.shape[1]

    ring = geometry_4326.get("coordinates", [[]])[0]
    if not ring or len(ring) < 4:
        raise ValueError("ROI polygon must have at least 4 positions (closed ring)")

    flat = []
    for pt in ring:
        if len(pt) < 2:
            continue
        lon, lat = float(pt[0]), float(pt[1])
        col = (lon - west) / (east - west) * w
        row = (north - lat) / (north - south) * h
        flat.extend((col, row))

    mask_im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask_im).polygon(flat, outline=1, fill=1)
    mask_arr = np.asarray(mask_im, dtype=bool)

    if not mask_arr.any():
        raise ValueError(
            "ROI does not overlap the image for the given bounds; ensure the map extent matches this GeoTIFF"
        )

    work = arr.copy()
    work[~mask_arr] = 0

    r0, r1, c0, c1 = _bbox_indices_from_mask(mask_arr)
    crop = work[r0:r1, c0:c1]
    pil_rgb = Image.fromarray(crop)

    west_c = west + (c0 / w) * (east - west)
    east_c = west + (c1 / w) * (east - west)
    north_c = north - (r0 / h) * (north - south)
    south_c = north - (r1 / h) * (north - south)
    wgs84_bounds = [float(south_c), float(west_c), float(north_c), float(east_c)]

    ch, cw = r1 - r0, c1 - c0
    transform_out = from_bounds(west_c, south_c, east_c, north_c, cw, ch)
    return pil_rgb, wgs84_bounds, transform_out, None, cw, ch


def _bounds_look_like_wgs84_degrees(left, bottom, right, top):
    return (
        -180 <= left <= 180
        and -180 <= right <= 180
        and -90 <= bottom <= 90
        and -90 <= top <= 90
        and left < right
        and bottom < top
    )


def _extract_roi_rgb_plate_carree_from_raster_geographic_extent(tif_path, geometry_4326):
    """Linear lon/lat mapping using on-file world bounds as degrees (no PROJ)."""
    import rasterio

    with rasterio.open(tif_path) as src:
        left, bottom, right, top = src.bounds
    if not _bounds_look_like_wgs84_degrees(left, bottom, right, top):
        raise ValueError(
            "Raster extent is not geographic degrees; need map-aligned bounds (client) or CRS metadata"
        )
    swne = [float(bottom), float(left), float(top), float(right)]
    return _extract_roi_rgb_plate_carree(tif_path, geometry_4326, swne)


def _extract_roi_rgb_with_robust_fallbacks(tif_path, geometry_4326, bounds_swne):
    """Client map bounds (plate carrée) → geographic file extent → rasterio mask + PROJ."""
    if bounds_swne:
        try:
            return _extract_roi_rgb_plate_carree(tif_path, geometry_4326, bounds_swne)
        except ValueError as e:
            print(f"[server] ROI plate-carée (client bounds): {e}", flush=True)
    try:
        return _extract_roi_rgb_plate_carree_from_raster_geographic_extent(tif_path, geometry_4326)
    except ValueError as e:
        print(f"[server] ROI plate-carée (raster geographic extent): {e}", flush=True)
    return _extract_roi_rgb_pil_and_georef(tif_path, geometry_4326)


def _cleanup_tmp_dir(tmp_dir):
    if not tmp_dir or not os.path.isdir(tmp_dir):
        return
    try:
        for name in os.listdir(tmp_dir):
            os.unlink(os.path.join(tmp_dir, name))
        os.rmdir(tmp_dir)
    except Exception:
        pass


def _save_prediction(
    annotation_png_bytes,
    base_png_bytes,
    meta,
    source_geotiff_path=None,
    geotiff_crop=None,
    class_grid_arr=None,
):
    """
    Save prediction to PREDICTIONS_DIR.
    geotiff_crop: optional dict with keys transform, crs, width, height for ROI-aligned output GeoTIFF.
    """
    pred_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    meta["id"] = pred_id
    meta["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(PREDICTIONS_DIR, exist_ok=True)
    base_path = os.path.join(PREDICTIONS_DIR, pred_id)
    png_bytes = annotation_png_bytes
    if class_grid_arr is not None:
        try:
            png_bytes = class_grid_to_prediction_png_bytes(np.asarray(class_grid_arr))
        except Exception as e:
            print(f"[server] prediction-only PNG fallback: {e}", flush=True)
    with open(base_path + ".png", "wb") as f:
        f.write(png_bytes)
    if base_png_bytes:
        with open(base_path + "_base.png", "wb") as f:
            f.write(base_png_bytes)
    if geotiff_crop:
        tr = geotiff_crop.get("transform")
        cr = geotiff_crop.get("crs")
        gw = geotiff_crop.get("width")
        gh = geotiff_crop.get("height")
        if tr is not None and gw and gh:
            if _write_annotation_geotiff_cropped(
                png_bytes, base_path + ".tif", tr, cr, int(gw), int(gh)
            ):
                meta["geotiff_available"] = True
    elif source_geotiff_path and os.path.splitext(source_geotiff_path)[1].lower() in (".tif", ".tiff"):
        if _write_annotation_geotiff(source_geotiff_path, png_bytes, base_path + ".tif"):
            meta["geotiff_available"] = True

    cls_path = base_path + "_classes.tif"
    if class_grid_arr is not None:
        cg = np.asarray(class_grid_arr, dtype=np.uint8)
        ok_cls = False
        if geotiff_crop:
            tr = geotiff_crop.get("transform")
            cr = geotiff_crop.get("crs")
            gw = geotiff_crop.get("width")
            gh = geotiff_crop.get("height")
            if tr is not None and gw and gh:
                ok_cls = _write_class_geotiff_cropped(cg, cls_path, tr, cr, int(gw), int(gh), nodata=CLASS_GRID_NODATA)
        elif source_geotiff_path and os.path.splitext(source_geotiff_path)[1].lower() in (".tif", ".tiff"):
            ok_cls = _write_class_geotiff_from_array(source_geotiff_path, cg, cls_path, nodata=CLASS_GRID_NODATA)
        if ok_cls:
            meta["class_geotiff_available"] = True
            meta["class_geotiff_path"] = pred_id + "_classes.tif"
            meta["class_grid_nodata"] = CLASS_GRID_NODATA

    meta_path = base_path + ".json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return pred_id


def _register_lulc_prediction_archive(
    pred_id: str,
    *,
    source_filename: str,
    seg_mode: str,
    meta: dict,
) -> None:
    """Slim manifest pointer under backend/prediction_archive/lulc_<pred_id>/."""
    try:
        write_lulc_manifest(
            pred_id,
            model_name=meta.get("model_name") or os.environ.get(
                "LULC_MODEL_NAME", "GiD-Land-Cover-Classification"
            ),
            source_filename=source_filename or "",
            predictions_dir=PREDICTIONS_DIR,
            annotation_png=os.path.join(PREDICTIONS_DIR, pred_id + ".png"),
            meta_json=os.path.join(PREDICTIONS_DIR, pred_id + ".json"),
            base_png=os.path.join(PREDICTIONS_DIR, pred_id + "_base.png")
            if os.path.isfile(os.path.join(PREDICTIONS_DIR, pred_id + "_base.png"))
            else None,
            geotiff_path=os.path.join(PREDICTIONS_DIR, pred_id + ".tif")
            if os.path.isfile(os.path.join(PREDICTIONS_DIR, pred_id + ".tif"))
            else None,
            seg_mode=seg_mode,
            class_geotiff_path=os.path.join(PREDICTIONS_DIR, pred_id + "_classes.tif")
            if os.path.isfile(os.path.join(PREDICTIONS_DIR, pred_id + "_classes.tif"))
            else None,
        )
    except Exception as e:
        print(f"[server] prediction archive manifest skipped: {e}", flush=True)


def _use_native_tiff_resolution(seg_mode: str, image_path: str, source_is_tiff: bool = False):
    ext = os.path.splitext(str(image_path or ""))[1].lower()
    return bool(seg_mode == "fast" and (source_is_tiff or ext in (".tif", ".tiff")))


def run_inference(image_path, use_segmentation=True, seg_mode="fast", source_is_tiff=False):
    """Run model: patch-based segmentation overlay on image; legend is for the API/UI only (not drawn on PNG).
    seg_mode: 'fast' = larger tiles (faster), 'pixel' = pixel-level (slower).
    """
    from app import SEG_STRIDE_FAST, SEG_STRIDE_PIXEL
    seg_stride = SEG_STRIDE_PIXEL if seg_mode == "pixel" else SEG_STRIDE_FAST
    native_tiff_res = _use_native_tiff_resolution(
        seg_mode, image_path, source_is_tiff=source_is_tiff
    )
    image = load_image_from_path(image_path)
    if image is None:
        return None, None, {}, None
    image = image.convert("RGB")
    base_img = None
    if use_segmentation:
        annotated_img, base_img, label_dict, probs, class_grid = segment_and_draw(
            image,
            processor,
            model,
            top_k=5,
            seg_stride=seg_stride,
            input_size=None,
            skip_downscale=native_tiff_res,
        )
    else:
        inputs = processor(images=image, return_tensors="pt")
        inputs = _to_device(inputs)
        with torch.inference_mode():
            logits = model(**inputs).logits
            probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()
        annotated_img, label_dict = draw_predictions_on_image(image, probs, top_k=5, draw_overlay=False)
        w, h = annotated_img.size
        top_idx = int(max(range(len(probs)), key=lambda i: probs[i]))
        class_grid = np.full((h, w), top_idx, dtype=np.uint8)
    return probs, annotated_img, label_dict, base_img, class_grid


def run_inference_streaming(
    image_path,
    seg_mode="fast",
    progress_patch_interval=5,
    source_is_tiff=False,
    enable_preview=True,
):
    """Generator that yields SSE-style dicts: progress events then one done event."""
    from app import SEG_STRIDE_FAST, SEG_STRIDE_PIXEL
    seg_stride = SEG_STRIDE_PIXEL if seg_mode == "pixel" else SEG_STRIDE_FAST
    native_tiff_res = _use_native_tiff_resolution(
        seg_mode, image_path, source_is_tiff=source_is_tiff
    )
    # Full-resolution TIFF previews are expensive; emit fewer partial frames to avoid OOM.
    effective_patch_interval = (
        max(int(progress_patch_interval), 120) if native_tiff_res else int(progress_patch_interval)
    )
    print(
        f"[server] Stream started: path={image_path!r}, seg_mode={seg_mode}, stride={seg_stride}, "
        f"native_tiff_res={native_tiff_res}, "
        f"progress_patch_interval={effective_patch_interval}, preview={bool(enable_preview)}",
        flush=True,
    )
    image = load_image_from_path(image_path)
    if image is None:
        print("[server] Stream error: Could not load image", flush=True)
        yield {"type": "error", "error": "Could not load image"}
        return
    image = image.convert("RGB")
    try:
        for chunk in segment_and_draw_streaming(
            image,
            processor,
            model,
            top_k=5,
            seg_stride=seg_stride,
            progress_patch_interval=effective_patch_interval,
            input_size=None,
            skip_downscale=native_tiff_res,
            emit_partial_images=bool(enable_preview),
            partial_overlay_only=bool(enable_preview and native_tiff_res),
        ):
            if len(chunk) == 5 and isinstance(chunk[2], dict):
                out, base_img, label_dict, probs, class_grid = chunk
                buf = io.BytesIO()
                out.save(buf, format="PNG")
                img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                pred_png = class_grid_to_prediction_png_bytes(class_grid)
                prediction_image_b64 = base64.b64encode(pred_png).decode("utf-8")
                base_b64 = None
                if base_img is not None:
                    buf_base = io.BytesIO()
                    base_img.save(buf_base, format="PNG")
                    base_b64 = base64.b64encode(buf_base.getvalue()).decode("utf-8")
                idx = max(range(len(probs)), key=lambda i: probs[i])
                print(f"[server] Stream done. Top: {ID2LABEL[str(idx)]} ({round(probs[idx] * 100, 1)}%)", flush=True)
                yield {
                    "type": "done",
                    "image_b64": img_b64,
                    "prediction_image_b64": prediction_image_b64,
                    "base_image_b64": base_b64,
                    "predictions": label_dict,
                    "top_class": ID2LABEL[str(idx)],
                    "top_pct": round(probs[idx] * 100, 1),
                    "width": out.width,
                    "height": out.height,
                    "class_probs": [float(x) for x in probs],
                    "_class_grid": class_grid,
                }
            else:
                partial_pil, progress, patch_count, total_patches = chunk
                pct = round(progress * 100, 1)
                print(f"[server] Stream progress: {pct}%", flush=True)
                evt = {
                    "type": "progress",
                    "progress": round(progress, 4),
                    "patch_count": patch_count,
                    "total_patches": total_patches,
                }
                if partial_pil is not None:
                    buf = io.BytesIO()
                    partial_pil.save(buf, format="PNG")
                    evt["image_b64"] = base64.b64encode(buf.getvalue()).decode("utf-8")
                yield evt
    except Exception as e:
        print(f"[server] Stream error: {e}", flush=True)
        yield {"type": "error", "error": str(e)}


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/predictions", methods=["GET"])
def list_predictions():
    """List saved predictions (id, created_at, top_class, top_pct, original_filename)."""
    try:
        entries = []
        for name in os.listdir(PREDICTIONS_DIR):
            if not name.endswith(".json"):
                continue
            pred_id = name[:-5]
            json_path = os.path.join(PREDICTIONS_DIR, name)
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                entries.append({
                    "id": pred_id,
                    "created_at": meta.get("created_at", ""),
                    "top_class": meta.get("top_class", ""),
                    "top_pct": meta.get("top_pct", 0),
                    "original_filename": meta.get("original_filename", ""),
                    "has_buildings": bool(meta.get("building_detection")),
                })
            except Exception:
                continue
        entries.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jsonify({"predictions": entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/predictions/delete-all", methods=["POST"])
def delete_all_lulc_predictions_route():
    """Remove all saved LULC predictions (disk + archive manifests)."""
    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return jsonify({"error": "Send JSON { \"confirm\": true }"}), 400
    from prediction_archive import delete_all_lulc_predictions_only

    return jsonify(delete_all_lulc_predictions_only())


@app.route("/predictions/<pred_id>", methods=["GET", "DELETE"])
def get_prediction(pred_id):
    """Load a saved prediction (GET) or delete it and its archive entry (DELETE)."""
    if ".." in pred_id or "/" in pred_id or "\\" in pred_id:
        return jsonify({"error": "Invalid id"}), 400

    if request.method == "DELETE":
        from prediction_archive import delete_prediction_run

        r = delete_prediction_run("lulc", pred_id)
        if not r.get("ok"):
            return jsonify({"error": r.get("error", "delete failed")}), 400
        return jsonify(r)
    base_path = os.path.join(PREDICTIONS_DIR, pred_id)
    json_path = base_path + ".json"
    png_path = base_path + ".png"
    if not os.path.isfile(json_path) or not os.path.isfile(png_path):
        return jsonify({"error": "Prediction not found"}), 404
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        with open(png_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        base_b64 = None
        base_png_path = base_path + "_base.png"
        if os.path.isfile(base_png_path):
            with open(base_png_path, "rb") as f:
                base_b64 = base64.b64encode(f.read()).decode("utf-8")
        out = {
            "predictions": meta.get("predictions", {}),
            "top_class": meta.get("top_class", ""),
            "top_pct": meta.get("top_pct", 0),
            "image_b64": img_b64,
            "width": meta.get("width", 0),
            "height": meta.get("height", 0),
            "bounds": meta.get("bounds"),
            "crs": meta.get("crs"),
            "prediction_id": pred_id,
            "geotiff_available": os.path.isfile(base_path + ".tif"),
            "class_geotiff_available": os.path.isfile(base_path + "_classes.tif"),
            "original_filename": meta.get("original_filename", ""),
        }
        if base_b64 is not None:
            out["base_image_b64"] = base_b64
        bd = meta.get("building_detection")
        bpath = base_path + "_buildings.geojson"
        if bd and os.path.isfile(bpath):
            out["building_detection"] = {
                "task": bd.get("task"),
                "run_id": bd.get("run_id"),
                "inference_threshold": bd.get("inference_threshold"),
                "model_name": bd.get("model_name"),
                "geojson_url": f"/predictions/{pred_id}/buildings.geojson",
                "has_full_geojson": os.path.isfile(base_path + "_buildings_full.geojson"),
                "has_unet_confidence": os.path.isfile(base_path + "_unet_confidence.npz"),
            }
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/predictions/<pred_id>/buildings.geojson", methods=["GET"])
def get_prediction_buildings_geojson(pred_id):
    """Saved building footprints linked to this LULC run (from UNet/Mask R-CNN attach)."""
    if ".." in pred_id or "/" in pred_id or "\\" in pred_id:
        return jsonify({"error": "Invalid id"}), 400
    fn = pred_id + "_buildings.geojson"
    path = os.path.join(PREDICTIONS_DIR, fn)
    if not os.path.isfile(path):
        return jsonify({"error": "No building detection stored for this prediction"}), 404
    return send_from_directory(PREDICTIONS_DIR, fn, mimetype="application/geo+json")


_CACHE_FOREVER = "public, max-age=31536000, immutable"


@app.route("/predictions/<pred_id>/overlay.png", methods=["GET"])
def get_prediction_overlay_png(pred_id):
    """Serve saved annotated overlay PNG for fast cached loads (Analysis Comparison tab, img src)."""
    if ".." in pred_id or "/" in pred_id or "\\" in pred_id:
        return jsonify({"error": "Invalid id"}), 400
    fn = pred_id + ".png"
    path = os.path.join(PREDICTIONS_DIR, fn)
    if not os.path.isfile(path):
        return jsonify({"error": "Prediction overlay PNG not found"}), 404
    resp = send_from_directory(PREDICTIONS_DIR, fn, mimetype="image/png")
    resp.headers["Cache-Control"] = _CACHE_FOREVER
    return resp


@app.route("/predictions/<pred_id>/base.png", methods=["GET"])
def get_prediction_base_png(pred_id):
    """Serve saved base (pre-overlay) PNG when present."""
    if ".." in pred_id or "/" in pred_id or "\\" in pred_id:
        return jsonify({"error": "Invalid id"}), 400
    fn = pred_id + "_base.png"
    path = os.path.join(PREDICTIONS_DIR, fn)
    if not os.path.isfile(path):
        return jsonify({"error": "Base PNG not available for this prediction"}), 404
    resp = send_from_directory(PREDICTIONS_DIR, fn, mimetype="image/png")
    resp.headers["Cache-Control"] = _CACHE_FOREVER
    return resp


@app.route("/predictions/<pred_id>/classes-geotiff", methods=["GET"])
def get_prediction_classes_geotiff(pred_id):
    """Serve 1-band class-index GeoTIFF when saved (GeoTIFF-based prediction)."""
    if ".." in pred_id or "/" in pred_id or "\\" in pred_id:
        return jsonify({"error": "Invalid id"}), 400
    base_path = os.path.join(PREDICTIONS_DIR, pred_id)
    tif_path = base_path + "_classes.tif"
    if not os.path.isfile(tif_path):
        return jsonify({"error": "Class GeoTIFF not available for this prediction"}), 404
    return send_from_directory(PREDICTIONS_DIR, pred_id + "_classes.tif", mimetype="image/tiff", as_attachment=True, download_name=pred_id + "_classes.tif")


@app.route("/predictions/<pred_id>/geotiff", methods=["GET"])
def get_prediction_geotiff(pred_id):
    """Serve the prediction result as GeoTIFF for ArcGIS-style zoomable viewing (only when source was GeoTIFF)."""
    if ".." in pred_id or "/" in pred_id or "\\" in pred_id:
        return jsonify({"error": "Invalid id"}), 400
    base_path = os.path.join(PREDICTIONS_DIR, pred_id)
    tif_path = base_path + ".tif"
    if not os.path.isfile(tif_path):
        return jsonify({"error": "GeoTIFF not available for this prediction (upload a GeoTIFF to get a GeoTIFF result)"}), 404
    return send_from_directory(PREDICTIONS_DIR, pred_id + ".tif", mimetype="image/tiff", as_attachment=True, download_name=pred_id + ".tif")


MAX_PREVIEW_PIXELS = 2048  # max width or height for preview image (keeps response small)


@app.route("/preview", methods=["POST"])
def preview():
    """Return original image as PNG base64 + bounds (for GeoTIFF) so user can show it on the map before running prediction."""
    main_file, ext, tfw_file, aux_file = _parse_predict_files()
    if main_file is None:
        return jsonify({"error": "No image file (use .tif, .png, .jpg)"}), 400
    tmp_dir = tempfile.mkdtemp()
    try:
        base = "raster"
        tif_path = os.path.join(tmp_dir, base + ext)
        main_file.save(tif_path)
        if tfw_file is not None:
            tfw_file.save(os.path.join(tmp_dir, base + ".tfw"))
        if aux_file is not None:
            aux_file.save(os.path.join(tmp_dir, base + ext + ".aux.xml"))
        img = load_image_from_path(tif_path)
        if img is None:
            return jsonify({"error": "Could not load image"}), 400
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > MAX_PREVIEW_PIXELS:
            if w >= h:
                new_w = MAX_PREVIEW_PIXELS
                new_h = max(1, round(h * new_w / w))
            else:
                new_h = MAX_PREVIEW_PIXELS
                new_w = max(1, round(w * new_h / h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        bounds, crs_display = (get_geobounds(tif_path) if ext in (".tif", ".tiff") else (None, None))
        out = {
            "image_b64": image_b64,
            "bounds": bounds,
            "crs": crs_display,
            "width": img.width,
            "height": img.height,
        }
        if ext in (".tif", ".tiff") and bounds:
            try:
                import shutil
                import rasterio
                try:
                    with rasterio.open(tif_path) as src:
                        n = min(3, src.count)
                        bands = [src.read(i) for i in range(1, n + 1)]
                        stretch = []
                        for i in range(n):
                            b = bands[i].astype(np.float64)
                            valid = b[np.isfinite(b)]
                            if valid.size == 0:
                                stretch.append([0, 65535])
                            else:
                                p2, p98 = np.percentile(valid, [2, 98])
                                if p98 <= p2:
                                    p98 = p2 + 1
                                stretch.append([float(p2), float(p98)])
                        while len(stretch) < 3:
                            stretch.append(stretch[-1] if stretch else [0, 65535])
                        out["stretch"] = stretch
                except Exception as e:
                    print(f"[server] Preview stretch failed: {e}", flush=True)
                now = time.time()
                for name in os.listdir(PREVIEW_CACHE_DIR):
                    path = os.path.join(PREVIEW_CACHE_DIR, name)
                    if os.path.isfile(path) and (now - os.path.getmtime(path)) > PREVIEW_MAX_AGE_SECONDS:
                        try:
                            os.unlink(path)
                        except Exception:
                            pass
                preview_id = uuid.uuid4().hex[:16]
                dest_path = os.path.join(PREVIEW_CACHE_DIR, preview_id + ".tif")
                shutil.copy2(tif_path, dest_path)
                out["preview_geotiff_id"] = preview_id
            except Exception as e:
                print(f"[server] Preview GeoTIFF cache failed: {e}", flush=True)
        return jsonify(out)
    except Exception as e:
        print(f"[server] Preview error: {e}", flush=True)
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            for name in os.listdir(tmp_dir):
                os.unlink(os.path.join(tmp_dir, name))
            os.rmdir(tmp_dir)
        except Exception:
            pass


@app.route("/preview/<preview_id>/geotiff", methods=["GET"])
def get_preview_geotiff(preview_id):
    """Serve cached original GeoTIFF for ArcGIS-style zoomable preview (only for GeoTIFF uploads)."""
    if ".." in preview_id or "/" in preview_id or "\\" in preview_id or len(preview_id) > 64:
        return jsonify({"error": "Invalid id"}), 400
    path = os.path.join(PREVIEW_CACHE_DIR, preview_id + ".tif")
    if not os.path.isfile(path):
        return jsonify({"error": "Preview expired or not found"}), 404
    return send_from_directory(PREVIEW_CACHE_DIR, preview_id + ".tif", mimetype="image/tiff")


def _parse_predict_files():
    """Shared file parsing for /predict and /predict-stream. Returns (main_file, ext, tfw_file, aux_file) or (None,)*4."""
    files = request.files.getlist("image")
    if not files:
        files = [request.files.get("image")]
    files = [f for f in files if f and f.filename]
    if not files:
        return None, None, None, None
    main_file = None
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext in (".tif", ".tiff", ".png", ".jpg", ".jpeg"):
            main_file = f
            break
    if main_file is None:
        return None, None, None, None
    ext = os.path.splitext(main_file.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        return None, None, None, None
    tfw_file = None
    aux_file = None
    for f in files:
        fn = f.filename.lower()
        if fn.endswith((".tfw", ".tifw")):
            tfw_file = f
        elif ".aux.xml" in fn or fn.endswith(".xml"):
            aux_file = f
    return main_file, ext, tfw_file, aux_file


@app.route("/predict-stream", methods=["POST"])
def predict_stream():
    """Stream segmentation progress: send partial overlay images as they are computed (SSE)."""
    print("[server] POST /predict-stream received", flush=True)
    main_file, ext, tfw_file, aux_file = _parse_predict_files()
    if main_file is None:
        return jsonify({"error": "No image file (use .tif, .png, .jpg)"}), 400
    seg_mode = (request.form.get("seg_mode") or "fast").strip().lower()
    if seg_mode not in ("fast", "pixel"):
        seg_mode = "fast"
    try:
        stream_patch_interval = int((request.form.get("stream_patch_interval") or "5").strip())
    except ValueError:
        stream_patch_interval = 5
    stream_patch_interval = max(1, min(stream_patch_interval, 50))
    stream_preview_raw = (request.form.get("stream_preview") or "1").strip().lower()
    stream_preview = stream_preview_raw in ("1", "true", "yes", "on")
    tmp_dir = tempfile.mkdtemp()
    base = "raster"
    tif_path = os.path.join(tmp_dir, base + ext)
    main_file.save(tif_path)
    if tfw_file is not None:
        tfw_file.save(os.path.join(tmp_dir, base + ".tfw"))
    if aux_file is not None:
        aux_file.save(os.path.join(tmp_dir, base + ext + ".aux.xml"))

    roi_raw = (request.form.get("roi_geojson") or "").strip()
    bounds_swne = _parse_roi_full_bounds_swne(request.form.get("roi_full_bounds_swne"))
    inference_path = tif_path
    roi_bounds_override = None
    roi_crs_override = None
    geotiff_crop = None

    if roi_raw:
        if ext not in (".tif", ".tiff"):
            _cleanup_tmp_dir(tmp_dir)
            return jsonify({"error": "ROI polygon is only supported for GeoTIFF uploads."}), 400
        try:
            geom = _geometry_polygon_from_roi_geojson(roi_raw)
            pil_roi, wgs_bounds, out_tr, out_crs, cw, ch = _extract_roi_rgb_with_robust_fallbacks(
                tif_path, geom, bounds_swne
            )
        except (json.JSONDecodeError, ValueError) as e:
            _cleanup_tmp_dir(tmp_dir)
            return jsonify({"error": str(e)}), 400
        inference_path = os.path.join(tmp_dir, "roi_crop.png")
        pil_roi.save(inference_path)
        roi_bounds_override = wgs_bounds
        roi_crs_override = (
            _crs_to_display_string(out_crs) if out_crs is not None else "WGS84 (map grid)"
        )
        geotiff_crop = {"transform": out_tr, "crs": out_crs, "width": cw, "height": ch}
        print(f"[server] predict-stream: ROI clip -> {cw}x{ch}, inference on PNG crop", flush=True)

    def generate():
        try:
            print(
                f"[server] predict-stream: processing {main_file.filename!r} (seg_mode={seg_mode}, "
                f"stream_patch_interval={stream_patch_interval}, preview={stream_preview})",
                flush=True,
            )
            if roi_bounds_override is not None:
                bounds, crs_display = roi_bounds_override, roi_crs_override
            else:
                bounds, crs_display = (get_geobounds(tif_path) if ext in (".tif", ".tiff") else (None, None))
            yield "data: " + json.dumps({"type": "start", "bounds": bounds, "crs": crs_display}, ensure_ascii=False) + "\n\n"
            for event in run_inference_streaming(
                inference_path,
                seg_mode=seg_mode,
                progress_patch_interval=stream_patch_interval,
                source_is_tiff=ext in (".tif", ".tiff"),
                enable_preview=stream_preview,
            ):
                class_grid_save = event.pop("_class_grid", None) if isinstance(event, dict) else None
                if event.get("type") == "done":
                    if roi_bounds_override is not None:
                        event["bounds"] = roi_bounds_override
                        event["crs"] = roi_crs_override
                    else:
                        b, c = (get_geobounds(tif_path) if ext in (".tif", ".tiff") else (None, None))
                        event["bounds"] = b
                        event["crs"] = c
                    try:
                        annotation_bytes = base64.b64decode(event["image_b64"])
                        base_bytes = base64.b64decode(event["base_image_b64"]) if event.get("base_image_b64") else None
                        meta = {
                            "predictions": event.get("predictions", {}),
                            "top_class": event.get("top_class", ""),
                            "top_pct": event.get("top_pct", 0),
                            "width": event.get("width", 0),
                            "height": event.get("height", 0),
                            "bounds": event.get("bounds"),
                            "crs": event.get("crs"),
                            "original_filename": main_file.filename,
                            "class_probs": event.get("class_probs") or [],
                            "id2label": {str(k): v for k, v in ID2LABEL.items()},
                            "seg_mode": seg_mode,
                        }
                        src_gt = None if geotiff_crop else (tif_path if ext in (".tif", ".tiff") else None)
                        pred_id = _save_prediction(
                            annotation_bytes,
                            base_bytes,
                            meta,
                            source_geotiff_path=src_gt,
                            geotiff_crop=geotiff_crop,
                            class_grid_arr=class_grid_save,
                        )
                        event["prediction_id"] = pred_id
                        event["geotiff_available"] = meta.get("geotiff_available", False)
                        event["class_geotiff_available"] = bool(meta.get("class_geotiff_available"))
                        event["original_filename"] = main_file.filename
                        _register_lulc_prediction_archive(
                            pred_id,
                            source_filename=main_file.filename or "",
                            seg_mode=seg_mode,
                            meta=meta,
                        )
                        print(f"[server] Saved prediction: {pred_id}", flush=True)
                    except Exception as e:
                        event["save_error"] = str(e)
                        print(f"[server] Save warning: {e}", flush=True)
                yield "data: " + sse_json_dumps(event) + "\n\n"
        finally:
            print("[server] predict-stream: finished, cleaning up temp dir", flush=True)
            _cleanup_tmp_dir(tmp_dir)

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/predict", methods=["POST"])
def predict():
    print("[server] POST /predict received", flush=True)
    main_file, ext, tfw_file, aux_file = _parse_predict_files()
    if main_file is None:
        return jsonify({"error": "No file selected"}), 400

    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp()
        base = "raster"
        tif_path = os.path.join(tmp_dir, base + ext)
        main_file.save(tif_path)
        if tfw_file is not None:
            tfw_path = os.path.join(tmp_dir, base + ".tfw")
            tfw_file.save(tfw_path)
        if aux_file is not None:
            aux_path = os.path.join(tmp_dir, base + ext + ".aux.xml")
            aux_file.save(aux_path)

        roi_raw = (request.form.get("roi_geojson") or "").strip()
        bounds_swne = _parse_roi_full_bounds_swne(request.form.get("roi_full_bounds_swne"))
        inference_path = tif_path
        geotiff_crop = None
        roi_bounds_override = None
        roi_crs_override = None

        if roi_raw:
            if ext not in (".tif", ".tiff"):
                return jsonify({"error": "ROI polygon is only supported for GeoTIFF uploads."}), 400
            try:
                geom = _geometry_polygon_from_roi_geojson(roi_raw)
                pil_roi, wgs_bounds, out_tr, out_crs, cw, ch = _extract_roi_rgb_with_robust_fallbacks(
                    tif_path, geom, bounds_swne
                )
            except (json.JSONDecodeError, ValueError) as e:
                return jsonify({"error": str(e)}), 400
            inference_path = os.path.join(tmp_dir, "roi_crop.png")
            pil_roi.save(inference_path)
            roi_bounds_override = wgs_bounds
            roi_crs_override = (
                _crs_to_display_string(out_crs) if out_crs is not None else "WGS84 (map grid)"
            )
            geotiff_crop = {"transform": out_tr, "crs": out_crs, "width": cw, "height": ch}

        seg_mode = (request.form.get("seg_mode") or "fast").strip().lower()
        if seg_mode not in ("fast", "pixel"):
            seg_mode = "fast"
        print(f"[server] /predict: processing {main_file.filename!r} (seg_mode={seg_mode})", flush=True)
        probs, annotated_img, label_dict, base_img, class_grid = run_inference(
            inference_path,
            seg_mode=seg_mode,
            source_is_tiff=ext in (".tif", ".tiff"),
        )
        print("[server] /predict: inference done", flush=True)
        if annotated_img is None:
            return jsonify({"error": "Could not load image"}), 400
        buf = io.BytesIO()
        annotated_img.save(buf, format="PNG")
        annotation_bytes = buf.getvalue()
        img_b64 = base64.b64encode(annotation_bytes).decode("utf-8")
        prediction_image_b64 = None
        if class_grid is not None:
            try:
                prediction_image_b64 = base64.b64encode(
                    class_grid_to_prediction_png_bytes(class_grid)
                ).decode("utf-8")
            except Exception:
                pass
        base_b64 = None
        base_bytes = None
        if base_img is not None:
            buf_base = io.BytesIO()
            base_img.save(buf_base, format="PNG")
            base_bytes = buf_base.getvalue()
            base_b64 = base64.b64encode(base_bytes).decode("utf-8")
        idx = max(range(len(probs)), key=lambda i: probs[i])
        if roi_bounds_override is not None:
            bounds, crs_display = roi_bounds_override, roi_crs_override
        else:
            bounds, crs_display = (get_geobounds(tif_path) if ext in (".tif", ".tiff") else (None, None))
        out = {
            "predictions": label_dict,
            "top_class": ID2LABEL[str(idx)],
            "top_pct": round(probs[idx] * 100, 1),
            "image_b64": img_b64,
            "width": annotated_img.width,
            "height": annotated_img.height,
            "bounds": bounds,
            "crs": crs_display,
        }
        if prediction_image_b64 is not None:
            out["prediction_image_b64"] = prediction_image_b64
        if base_b64 is not None:
            out["base_image_b64"] = base_b64
        meta = {
            "predictions": label_dict,
            "top_class": ID2LABEL[str(idx)],
            "top_pct": round(probs[idx] * 100, 1),
            "width": annotated_img.width,
            "height": annotated_img.height,
            "bounds": bounds,
            "crs": crs_display,
            "original_filename": main_file.filename,
            "class_probs": [float(x) for x in probs],
            "id2label": {str(k): v for k, v in ID2LABEL.items()},
            "seg_mode": seg_mode,
        }
        try:
            src_gt = None if geotiff_crop else (tif_path if ext in (".tif", ".tiff") else None)
            pred_id = _save_prediction(
                annotation_bytes,
                base_bytes,
                meta,
                source_geotiff_path=src_gt,
                geotiff_crop=geotiff_crop,
                class_grid_arr=class_grid,
            )
            out["prediction_id"] = pred_id
            out["geotiff_available"] = meta.get("geotiff_available", False)
            out["class_geotiff_available"] = bool(meta.get("class_geotiff_available"))
            _register_lulc_prediction_archive(
                pred_id,
                source_filename=main_file.filename or "",
                seg_mode=seg_mode,
                meta=meta,
            )
        except Exception as e:
            out["save_error"] = str(e)
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        _cleanup_tmp_dir(tmp_dir)


if __name__ == "__main__":
    print("Land Cover Classification server: http://127.0.0.1:5000")
    print("Max upload size: 2 GB (for large GeoTIFFs)")
    app.run(host="0.0.0.0", port=5000, debug=False)
