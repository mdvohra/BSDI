"""
GeoTIFF ROI clip for Mask R-CNN (and similar): map-aligned plate carrée first (no PROJ),
then geographic file extent, then rasterio mask + transform_geom.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import List, Optional

import numpy as np
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def _bbox_indices_from_mask(mask_arr: np.ndarray) -> tuple[int, int, int, int]:
    """Tight pixel bounds (r0, r1, c0, c1) for True region.

    Avoids ``np.where(mask)`` on huge rasters: that allocates two int64 arrays of length
    (#true pixels) and can require ~1 GiB for 50M+ selected pixels.
    """
    row_idx = np.flatnonzero(np.any(mask_arr, axis=1))
    col_idx = np.flatnonzero(np.any(mask_arr, axis=0))
    if row_idx.size == 0 or col_idx.size == 0:
        raise ValueError("ROI mask is empty after rasterization")
    r0, r1 = int(row_idx[0]), int(row_idx[-1]) + 1
    c0, c1 = int(col_idx[0]), int(col_idx[-1]) + 1
    return r0, r1, c0, c1


def parse_roi_full_bounds_swne(form_value: Optional[str]) -> Optional[List[float]]:
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


def geometry_polygon_from_roi_geojson(geojson_str: str) -> dict:
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


def bounds_look_like_wgs84_degrees(left: float, bottom: float, right: float, top: float) -> bool:
    return (
        -180 <= left <= 180
        and -180 <= right <= 180
        and -90 <= bottom <= 90
        and -90 <= top <= 90
        and left < right
        and bottom < top
    )


def write_maskrcnn_roi_geotiff_plate_carree(
    src_path: str, geometry_4326: dict, bounds_swne: List[float]
) -> str:
    import rasterio
    from rasterio.transform import from_bounds

    south, west, north, east = bounds_swne
    if east <= west or north <= south:
        raise ValueError("roi_full_bounds_swne must be [south, west, north, east] with positive span")

    with rasterio.open(src_path) as src:
        n = src.count
        if n not in (3, 4):
            raise ValueError(f"ROI requires 3 or 4 bands; this file has {n}")
        data = src.read(list(range(1, n + 1)))

    _, h, w = data.shape
    ring = geometry_4326.get("coordinates", [[]])[0]
    if not ring or len(ring) < 4:
        raise ValueError("ROI polygon must have at least 4 positions (closed ring)")

    flat: List[float] = []
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

    out = data.copy()
    for bi in range(n):
        out[bi][~mask_arr] = 0

    r0, r1, c0, c1 = _bbox_indices_from_mask(mask_arr)
    crop = out[:, r0:r1, c0:c1]

    west_c = west + (c0 / w) * (east - west)
    east_c = west + (c1 / w) * (east - west)
    north_c = north - (r0 / h) * (north - south)
    south_c = north - (r1 / h) * (north - south)
    ch, cw = r1 - r0, c1 - c0
    transform_out = from_bounds(west_c, south_c, east_c, north_c, cw, ch)

    fd, out_path = tempfile.mkstemp(suffix=".tif", prefix="maskrcnn_roi_")
    os.close(fd)
    try:
        with rasterio.open(
            out_path,
            "w",
            driver="GTiff",
            height=ch,
            width=cw,
            count=n,
            dtype=crop.dtype,
            transform=transform_out,
            compress="lzw",
        ) as dst:
            dst.write(crop)
    except Exception:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        raise
    return out_path


def write_maskrcnn_roi_geotiff_georef(src_path: str, geometry_4326: dict) -> str:
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import transform_geom

    with rasterio.open(src_path) as src:
        crs = src.crs
        if crs is None:
            raise ValueError(
                "GeoTIFF has no CRS; draw the ROI on the map and run detection again so the server can use map-aligned bounds, "
                "or add CRS metadata to the file."
            )
        n = src.count
        if n not in (3, 4):
            raise ValueError(f"ROI requires 3 or 4 bands; this file has {n}")
        geom_src = transform_geom("EPSG:4326", crs, geometry_4326)
        indexes = list(range(1, n + 1))
        try:
            out_image, out_transform = mask(
                src,
                [geom_src],
                crop=True,
                all_touched=True,
                filled=True,
                nodata=0,
                indexes=indexes,
            )
        except ValueError as e:
            raise ValueError(f"ROI does not overlap this raster: {e}") from e

    if out_image.size == 0 or out_image.shape[1] == 0 or out_image.shape[2] == 0:
        raise ValueError("ROI clip produced an empty image")

    fd, out_path = tempfile.mkstemp(suffix=".tif", prefix="maskrcnn_roi_")
    os.close(fd)
    try:
        with rasterio.open(
            out_path,
            "w",
            driver="GTiff",
            height=out_image.shape[1],
            width=out_image.shape[2],
            count=n,
            dtype=out_image.dtype,
            crs=crs,
            transform=out_transform,
            compress="lzw",
        ) as dst:
            dst.write(out_image)
    except Exception:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        raise
    return out_path


def maskrcnn_roi_geotiff_with_fallbacks(
    src_path: str, geometry_4326: dict, bounds_swne: Optional[List[float]]
) -> str:
    if bounds_swne:
        try:
            return write_maskrcnn_roi_geotiff_plate_carree(src_path, geometry_4326, bounds_swne)
        except ValueError as e:
            logger.info("MaskRCNN ROI plate-carée (client bounds): %s", e)
    try:
        import rasterio

        with rasterio.open(src_path) as src:
            left, bottom, right, top = src.bounds
        if bounds_look_like_wgs84_degrees(left, bottom, right, top):
            swne = [float(bottom), float(left), float(top), float(right)]
            return write_maskrcnn_roi_geotiff_plate_carree(src_path, geometry_4326, swne)
    except ValueError as e:
        logger.info("MaskRCNN ROI plate-carée (raster geographic extent): %s", e)
    return write_maskrcnn_roi_geotiff_georef(src_path, geometry_4326)


def _unet_read_bands_stack(
    src, sar_mode: bool, prefer_four_bands: bool = False
) -> tuple[np.ndarray, int]:
    """Bands as (count, H, W) for UNet building (RGB-style) or SAR (single band).

    When ``prefer_four_bands`` is True (e.g. water SMP model), read up to four bands;
    if fewer than four are present, duplicate channels to reach four.
    """
    if sar_mode:
        data = src.read(1)
        return data[np.newaxis, ...], 1
    n = src.count
    if prefer_four_bands:
        if n >= 4:
            return src.read((1, 2, 3, 4)), 4
        if n == 3:
            b = np.asarray(src.read((1, 2, 3)), dtype=np.float32)
            b4 = np.expand_dims(b[2], axis=0)
            return np.concatenate([b, b4], axis=0), 4
        if n == 1:
            b = src.read(1)
            stacked = np.stack([b, b, b, b], axis=0)
            return stacked, 4
        b1, b2 = src.read(1), src.read(2)
        stacked = np.stack([b1, b2, b1, b2], axis=0)
        return stacked, 4
    if n >= 3:
        return src.read((1, 2, 3)), 3
    if n == 1:
        b = src.read(1)
        return b[np.newaxis, ...], 1
    b1, b2 = src.read(1), src.read(2)
    return np.stack([b1, b2], axis=0), 2


def _plate_carree_masked_crop_to_geotiff(
    data: np.ndarray,
    geometry_4326: dict,
    bounds_swne: List[float],
    out_prefix: str,
) -> str:
    """Shared plate carrée clip: data is (C,H,W)."""
    import rasterio
    from rasterio.transform import from_bounds

    south, west, north, east = bounds_swne
    if east <= west or north <= south:
        raise ValueError("roi_full_bounds_swne must be [south, west, north, east] with positive span")

    n, h, w = data.shape
    ring = geometry_4326.get("coordinates", [[]])[0]
    if not ring or len(ring) < 4:
        raise ValueError("ROI polygon must have at least 4 positions (closed ring)")

    flat: List[float] = []
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

    out = data.copy()
    for bi in range(n):
        out[bi][~mask_arr] = 0

    r0, r1, c0, c1 = _bbox_indices_from_mask(mask_arr)
    crop = out[:, r0:r1, c0:c1]

    west_c = west + (c0 / w) * (east - west)
    east_c = west + (c1 / w) * (east - west)
    north_c = north - (r0 / h) * (north - south)
    south_c = north - (r1 / h) * (north - south)
    ch, cw = r1 - r0, c1 - c0
    transform_out = from_bounds(west_c, south_c, east_c, north_c, cw, ch)

    fd, out_path = tempfile.mkstemp(suffix=".tif", prefix=out_prefix)
    os.close(fd)
    try:
        with rasterio.open(
            out_path,
            "w",
            driver="GTiff",
            height=ch,
            width=cw,
            count=n,
            dtype=crop.dtype,
            transform=transform_out,
            compress="lzw",
        ) as dst:
            dst.write(crop)
    except Exception:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        raise
    return out_path


def write_unet_roi_geotiff_plate_carree(
    src_path: str,
    geometry_4326: dict,
    bounds_swne: List[float],
    sar_mode: bool,
    prefer_four_bands: bool = False,
) -> str:
    import rasterio

    with rasterio.open(src_path) as src:
        data, _n = _unet_read_bands_stack(src, sar_mode, prefer_four_bands=prefer_four_bands)
    return _plate_carree_masked_crop_to_geotiff(data, geometry_4326, bounds_swne, "unet_roi_")


def write_unet_roi_geotiff_georef(src_path: str, geometry_4326: dict, sar_mode: bool) -> str:
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import transform_geom

    with rasterio.open(src_path) as src:
        crs = src.crs
        if crs is None:
            raise ValueError(
                "GeoTIFF has no CRS; draw the ROI on the map and run again so the server can use map-aligned bounds, "
                "or add CRS metadata to the file."
            )
        nb = src.count
        if nb < 1:
            raise ValueError("GeoTIFF has no bands")
        geom_src = transform_geom("EPSG:4326", crs, geometry_4326)
        indexes = list(range(1, nb + 1))
        try:
            out_image, out_transform = mask(
                src,
                [geom_src],
                crop=True,
                all_touched=True,
                filled=True,
                nodata=0,
                indexes=indexes,
            )
        except ValueError as e:
            raise ValueError(f"ROI does not overlap this raster: {e}") from e

    if out_image.size == 0 or out_image.shape[1] == 0 or out_image.shape[2] == 0:
        raise ValueError("ROI clip produced an empty image")

    fd, out_path = tempfile.mkstemp(suffix=".tif", prefix="unet_roi_")
    os.close(fd)
    try:
        with rasterio.open(
            out_path,
            "w",
            driver="GTiff",
            height=out_image.shape[1],
            width=out_image.shape[2],
            count=nb,
            dtype=out_image.dtype,
            crs=crs,
            transform=out_transform,
            compress="lzw",
        ) as dst:
            dst.write(out_image)
    except Exception:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        raise
    return out_path


def unet_roi_geotiff_with_fallbacks(
    src_path: str,
    geometry_4326: dict,
    bounds_swne: Optional[List[float]],
    sar_mode: bool,
    prefer_four_bands: bool = False,
) -> str:
    if bounds_swne:
        try:
            return write_unet_roi_geotiff_plate_carree(
                src_path, geometry_4326, bounds_swne, sar_mode, prefer_four_bands=prefer_four_bands
            )
        except ValueError as e:
            logger.info("UNet ROI plate-carée (client bounds): %s", e)
    try:
        import rasterio

        with rasterio.open(src_path) as src:
            left, bottom, right, top = src.bounds
            data, _ = _unet_read_bands_stack(src, sar_mode, prefer_four_bands=prefer_four_bands)
        if bounds_look_like_wgs84_degrees(left, bottom, right, top):
            swne = [float(bottom), float(left), float(top), float(right)]
            return _plate_carree_masked_crop_to_geotiff(data, geometry_4326, swne, "unet_roi_")
    except ValueError as e:
        logger.info("UNet ROI plate-carée (raster geographic extent): %s", e)
    return write_unet_roi_geotiff_georef(src_path, geometry_4326, sar_mode)
