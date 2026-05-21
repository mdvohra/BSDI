"""Align class rasters, compute summary, transition matrix, tiles, optional regions."""

from __future__ import annotations

import hashlib
import json
import re
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .paths import get_predictions_dir

try:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject
    from rasterio import features as rio_features
except ImportError:
    rasterio = None


NODATA_DEFAULT = 255
NUM_CLASSES = 15  # ID2LABEL 0..14


def _meta_path(pred_id: str) -> str:
    return os.path.join(get_predictions_dir(), pred_id + ".json")


def _class_tif_path(pred_id: str) -> str:
    return os.path.join(get_predictions_dir(), pred_id + "_classes.tif")


def load_prediction_meta(pred_id: str) -> Optional[Dict[str, Any]]:
    p = _meta_path(pred_id)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def file_sha16(path: str) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read(min(8_000_000, os.path.getsize(path))))
        return h.hexdigest()[:16]
    except OSError:
        return None


def _pixel_area_m2(transform, crs) -> Optional[float]:
    if transform is None or crs is None:
        return None
    try:
        if crs.is_projected:
            return abs(float(transform[0])) * abs(float(transform[4]))
    except Exception:
        pass
    return None


def align_baseline_to_new(
    baseline_tif: str,
    new_tif: str,
    nodata: int = NODATA_DEFAULT,
) -> Tuple[np.ndarray, np.ndarray, Any, Any, Optional[float]]:
    """Read `new` grid; warp `baseline` to match. Returns (base_aligned, new_arr, transform, crs, pixel_area_m2)."""
    if rasterio is None:
        raise RuntimeError("rasterio required")

    with rasterio.open(new_tif) as dst_ref:
        new_arr = dst_ref.read(1).astype(np.uint8)
        dst_transform = dst_ref.transform
        dst_crs = dst_ref.crs
        height, width = new_arr.shape
        pa = _pixel_area_m2(dst_transform, dst_crs)

    base_aligned = np.full((height, width), nodata, dtype=np.uint8)
    with rasterio.open(baseline_tif) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=base_aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,
            src_nodata=nodata,
            dst_nodata=nodata,
        )

    return base_aligned, new_arr, dst_transform, dst_crs, pa


def global_histogram(
    a: np.ndarray, b: np.ndarray, nodata: int, n_class: int = NUM_CLASSES
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Valid pixels: both != nodata. Returns (hist_a, hist_b, hist_pair flat, valid_count)."""
    valid = (a != nodata) & (b != nodata)
    valid_count = int(np.sum(valid))
    if valid_count == 0:
        za = np.zeros(n_class, dtype=np.int64)
        zb = np.zeros(n_class, dtype=np.int64)
        return za, zb, np.zeros(n_class * n_class, dtype=np.int64), 0
    aa = a[valid].astype(np.int64).clip(0, n_class - 1)
    bb = b[valid].astype(np.int64).clip(0, n_class - 1)
    hist_a = np.bincount(aa, minlength=n_class).astype(np.int64)
    hist_b = np.bincount(bb, minlength=n_class).astype(np.int64)
    idx = aa * n_class + bb
    hist_pair = np.bincount(idx, minlength=n_class * n_class).astype(np.int64)
    return hist_a, hist_b, hist_pair, valid_count


def matrix_2d(flat: np.ndarray, n_class: int = NUM_CLASSES) -> List[List[int]]:
    m = flat.reshape(n_class, n_class)
    return m.astype(int).tolist()


def compute_tiles(
    baseline: np.ndarray,
    new: np.ndarray,
    nodata: int,
    tile_px: int,
    n_class: int = NUM_CLASSES,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Split into tile_px windows; stats per tile."""
    h, w = baseline.shape
    tile_px = max(8, min(tile_px, 2048))
    n_rows = int(math.ceil(h / tile_px))
    n_cols = int(math.ceil(w / tile_px))
    items: List[Dict[str, Any]] = []
    tid = 0
    for ri in range(n_rows):
        for ci in range(n_cols):
            r0, r1 = ri * tile_px, min(h, (ri + 1) * tile_px)
            c0, c1 = ci * tile_px, min(w, (ci + 1) * tile_px)
            ba = baseline[r0:r1, c0:c1]
            bn = new[r0:r1, c0:c1]
            valid = (ba != nodata) & (bn != nodata)
            vc = int(np.sum(valid))
            if vc == 0:
                items.append(
                    {
                        "tile_id": f"t{tid}",
                        "row": ri,
                        "col": ci,
                        "r0": r0,
                        "r1": r1,
                        "c0": c0,
                        "c1": c1,
                        "valid_pixels": 0,
                        "changed_pixels": 0,
                        "unchanged_pixels": 0,
                        "hist_baseline": [0] * n_class,
                        "hist_new": [0] * n_class,
                    }
                )
                tid += 1
                continue
            ba_v = ba[valid].astype(np.int64).clip(0, n_class - 1)
            bn_v = bn[valid].astype(np.int64).clip(0, n_class - 1)
            changed = int(np.sum(ba_v != bn_v))
            ha = np.bincount(ba_v, minlength=n_class).astype(int).tolist()
            hb = np.bincount(bn_v, minlength=n_class).astype(int).tolist()
            # dominant transition (mode of pair)
            pair_idx = ba_v * n_class + bn_v
            top = int(np.argmax(np.bincount(pair_idx, minlength=n_class * n_class)))
            from_c, to_c = top // n_class, top % n_class
            items.append(
                {
                    "tile_id": f"t{tid}",
                    "row": ri,
                    "col": ci,
                    "r0": r0,
                    "r1": r1,
                    "c0": c0,
                    "c1": c1,
                    "valid_pixels": vc,
                    "changed_pixels": changed,
                    "unchanged_pixels": int(vc - changed),
                    "hist_baseline": ha,
                    "hist_new": hb,
                    "dominant_transition": {"from": from_c, "to": to_c},
                }
            )
            tid += 1
    return items, n_rows, n_cols


def zonal_from_geojson(
    geojson_path: str,
    baseline: np.ndarray,
    new: np.ndarray,
    transform,
    crs,
    nodata: int,
    id2label: Dict[str, str],
    n_class: int = NUM_CLASSES,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Each polygon feature: compute histogram + transition if properties contain id or use enumerate.
    Returns (list of region stats, regions_index dict).
    """
    if rasterio is None or not os.path.isfile(geojson_path):
        return [], {"regions": []}

    try:
        import geopandas as gpd
    except ImportError:
        return [], {"regions": [], "error": "geopandas not installed"}

    gdf = gpd.read_file(geojson_path)
    if gdf.empty:
        return [], {"regions": []}

    h, w = baseline.shape
    out: List[Dict[str, Any]] = []
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    gdf = gdf.to_crs(crs)

    try:
        from shapely.geometry import mapping as shp_mapping
    except ImportError:
        return [], {"regions": [], "error": "shapely not installed"}

    regions_index = {"regions": []}
    for _i, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        try:
            shp = shp_mapping(geom)
        except Exception:
            continue

        mask = rio_features.rasterize(
            [(shp, 1)],
            out_shape=(h, w),
            transform=transform,
            fill=0,
            dtype=np.uint8,
        ).astype(bool)
        if not mask.any():
            continue
        ba = np.where(mask, baseline, nodata)
        bn = np.where(mask, new, nodata)
        ha, hb, hp, vc = global_histogram(ba, bn, nodata, n_class=n_class)
        rid = None
        if "id" in gdf.columns:
            rid = row["id"]
        name = ""
        if "name" in gdf.columns:
            name = str(row["name"])
        rid_raw = str(rid) if rid is not None else f"r{len(out)}"
        rid_s = re.sub(r"[^a-zA-Z0-9._-]+", "_", rid_raw)[:120] or f"r{len(out)}"
        labels = [id2label.get(str(j), str(j)) for j in range(n_class)]
        out.append(
            {
                "region_id": rid_s,
                "name": name,
                "valid_pixels": vc,
                "hist_baseline": ha.astype(int).tolist(),
                "hist_new": hb.astype(int).tolist(),
                "matrix": matrix_2d(hp, n_class),
                "labels": labels,
            }
        )
        regions_index["regions"].append({"region_id": rid_s, "file": f"regions/{rid_s}.json"})

    return out, regions_index


def local_window(
    baseline: np.ndarray,
    new: np.ndarray,
    row: int,
    col: int,
    win: int,
    nodata: int,
    n_class: int = NUM_CLASSES,
) -> Dict[str, Any]:
    h, w = baseline.shape
    half = win // 2
    r0, r1 = max(0, row - half), min(h, row + half + 1)
    c0, c1 = max(0, col - half), min(w, col + half + 1)
    ba = baseline[r0:r1, c0:c1]
    bn = new[r0:r1, c0:c1]
    ha, hb, hp, vc = global_histogram(ba, bn, nodata, n_class=n_class)
    top_idx = int(np.argmax(hp)) if hp.sum() > 0 else 0
    return {
        "window": {"r0": r0, "r1": r1, "c0": c0, "c1": c1, "center_row": row, "center_col": col},
        "valid_pixels": vc,
        "hist_baseline": ha.astype(int).tolist(),
        "hist_new": hb.astype(int).tolist(),
        "top_transition_idx": top_idx,
        "top_transition_from": top_idx // n_class,
        "top_transition_to": top_idx % n_class,
    }


def lonlat_to_rc(transform, crs, lon: float, lat: float) -> Optional[Tuple[int, int]]:
    if rasterio is None:
        return None
    try:
        import rasterio.warp

        xs, ys = rasterio.warp.transform("EPSG:4326", crs, [lon], [lat])
        row, col = rasterio.transform.rowcol(transform, xs[0], ys[0])
        return int(row), int(col)
    except Exception:
        return None
