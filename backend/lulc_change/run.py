"""Create comparison folder with JSON artifacts."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

from . import compute
from .paths import comparison_dir, ensure_dir, region_set_dir

NUM_CLASSES = compute.NUM_CLASSES


def id2label_from_meta(meta: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not meta:
        return {str(i): str(i) for i in range(NUM_CLASSES)}
    raw = meta.get("id2label") or {}
    out = {str(i): str(i) for i in range(NUM_CLASSES)}
    for k, v in raw.items():
        out[str(k)] = str(v)
    return out


def run_comparison_job(
    baseline_id: str,
    new_id: str,
    *,
    tile_px: int = 128,
    region_set_id: Optional[str] = None,
    nodata: int = compute.NODATA_DEFAULT,
) -> Dict[str, Any]:
    """Returns manifest dict; writes files under comparisons/<id>/."""
    base_meta = compute.load_prediction_meta(baseline_id)
    new_meta = compute.load_prediction_meta(new_id)
    if not base_meta or not new_meta:
        raise ValueError("baseline or new prediction meta not found")

    base_tif = compute._class_tif_path(baseline_id)
    new_tif = compute._class_tif_path(new_id)
    if not os.path.isfile(base_tif) or not os.path.isfile(new_tif):
        raise ValueError("both predictions must have class GeoTIFF (_classes.tif); re-run LULC on GeoTIFF")

    baseline_arr, new_arr, transform, crs, pixel_area_m2 = compute.align_baseline_to_new(
        base_tif, new_tif, nodata=nodata
    )

    labels = [id2label_from_meta(new_meta).get(str(i), str(i)) for i in range(NUM_CLASSES)]

    ha, hb, hp, valid_count = compute.global_histogram(baseline_arr, new_arr, nodata)
    unchanged = int(
        np.sum((baseline_arr == new_arr) & (baseline_arr != nodata) & (new_arr != nodata))
    )
    changed = valid_count - unchanged

    summary = {
        "baseline_id": baseline_id,
        "new_id": new_id,
        "valid_pixels": valid_count,
        "unchanged_pixels": unchanged,
        "changed_pixels": changed,
        "pixel_area_m2": pixel_area_m2,
        "histogram_baseline": ha.astype(int).tolist(),
        "histogram_new": hb.astype(int).tolist(),
        "percent_baseline": (ha.astype(np.float64) / max(valid_count, 1) * 100.0).round(4).tolist(),
        "percent_new": (hb.astype(np.float64) / max(valid_count, 1) * 100.0).round(4).tolist(),
        "delta_percent": (
            (hb.astype(np.float64) - ha.astype(np.float64)) / max(valid_count, 1) * 100.0
        ).round(4).tolist(),
        "labels": labels,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    tm = {
        "labels": labels,
        "matrix": compute.matrix_2d(hp),
        "flat_counts": hp.astype(int).tolist(),
    }

    tile_items, n_rows, n_cols = compute.compute_tiles(baseline_arr, new_arr, nodata, tile_px)
    ranked = sorted(tile_items, key=lambda x: x.get("changed_pixels", 0), reverse=True)

    comparison_id = uuid.uuid4().hex
    root = comparison_dir(comparison_id)
    ensure_dir(root)
    ensure_dir(os.path.join(root, "tiles_chunks"))

    manifest = {
        "comparison_id": comparison_id,
        "baseline_id": baseline_id,
        "new_id": new_id,
        "created_at": summary["created_at"],
        "status": "complete",
        "taxonomy_version": "fine_15",
        "alignment": {
            "reference": "new",
            "nodata": nodata,
            "transform": list(transform) if transform is not None else None,
            "crs": str(crs) if crs is not None else None,
            "height": int(baseline_arr.shape[0]),
            "width": int(baseline_arr.shape[1]),
        },
        "input_hashes": {
            "baseline_classes": compute.file_sha16(base_tif),
            "new_classes": compute.file_sha16(new_tif),
        },
        "tile_px": tile_px,
        "tiles_grid": {"n_rows": n_rows, "n_cols": n_cols},
        "paths": {
            "summary": "summary.json",
            "transition_matrix": "transition_matrix.json",
            "tiles_meta": "tiles_meta.json",
            "tiles_ranked_top": "tiles_ranked_top.json",
        },
    }

    with open(os.path.join(root, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    with open(os.path.join(root, "transition_matrix.json"), "w", encoding="utf-8") as f:
        json.dump(tm, f, indent=2, ensure_ascii=False)

    tiles_meta = {
        "tile_px": tile_px,
        "n_rows": n_rows,
        "n_cols": n_cols,
        "total_tiles": len(tile_items),
    }
    with open(os.path.join(root, "tiles_meta.json"), "w", encoding="utf-8") as f:
        json.dump(tiles_meta, f, indent=2, ensure_ascii=False)

    top_n = ranked[: min(500, len(ranked))]
    with open(os.path.join(root, "tiles_ranked_top.json"), "w", encoding="utf-8") as f:
        json.dump({"items": top_n, "total": len(tile_items)}, f, indent=2, ensure_ascii=False)

    # chunk full list for tooling
    chunk_max = 200
    chunk_i = 0
    for start in range(0, len(tile_items), chunk_max):
        chunk = tile_items[start : start + chunk_max]
        path = os.path.join(root, "tiles_chunks", f"chunk_{chunk_i:04d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"items": chunk, "offset": start}, f, indent=2, ensure_ascii=False)
        chunk_i += 1
    manifest["paths"]["tiles_chunk_glob"] = "tiles_chunks/chunk_*.json"

    # Always write one synthetic region = full valid overlap (no GeoJSON required for users).
    ensure_dir(os.path.join(root, "regions"))
    full_extent_payload = {
        "region_id": "full_extent",
        "name": "Entire compared area (automatic)",
        "source": "auto_full_overlap",
        "valid_pixels": int(valid_count),
        "hist_baseline": ha.astype(int).tolist(),
        "hist_new": hb.astype(int).tolist(),
        "matrix": compute.matrix_2d(hp),
        "labels": labels,
    }
    with open(os.path.join(root, "regions", "full_extent.json"), "w", encoding="utf-8") as f:
        json.dump(full_extent_payload, f, indent=2, ensure_ascii=False)

    regions_index: Dict[str, Any] = {
        "regions": [
            {
                "region_id": "full_extent",
                "name": "Entire compared area (automatic)",
                "file": "regions/full_extent.json",
            }
        ]
    }

    if region_set_id:
        rpath = os.path.join(region_set_dir(), region_set_id, "regions.geojson")
        regions: List[Dict[str, Any]]
        if not os.path.isfile(rpath):
            manifest.setdefault("warnings", []).append(f"region_set not found: {region_set_id}")
        else:
            extra_list, extra_index = compute.zonal_from_geojson(
                rpath,
                baseline_arr,
                new_arr,
                transform,
                crs,
                nodata,
                id2label_from_meta(new_meta),
            )
            for rs in extra_list:
                rid = rs.get("region_id") or "region"
                safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(rid))[:120]
                fname = f"custom_{safe}.json" if safe != "full_extent" else f"custom_{safe}_zonal.json"
                with open(os.path.join(root, "regions", fname), "w", encoding="utf-8") as f:
                    json.dump({**rs, "_saved_as": fname}, f, indent=2, ensure_ascii=False)
                regions_index["regions"].append(
                    {
                        "region_id": rs.get("region_id"),
                        "name": rs.get("name") or "",
                        "file": f"regions/{fname}",
                    }
                )

    with open(os.path.join(root, "regions_index.json"), "w", encoding="utf-8") as f:
        json.dump(regions_index, f, indent=2, ensure_ascii=False)
    manifest["paths"]["regions_index"] = "regions_index.json"

    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    manifest["summary"] = summary
    return manifest
