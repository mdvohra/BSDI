"""FastAPI routes under /api/analysis/lulc-change/*"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import compute
from .paths import comparison_dir, ensure_dir, get_change_archive_root, region_set_dir
from .run import id2label_from_meta, run_comparison_job

router = APIRouter(tags=["lulc-change"])


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class CreateComparisonBody(BaseModel):
    baseline_id: str = Field(..., description="LULC prediction id (older)")
    new_id: str = Field(..., description="LULC prediction id (newer)")
    tile_px: int = Field(128, ge=8, le=2048)
    region_set_id: Optional[str] = None


@router.post("/lulc-change/comparison")
def create_comparison(body: CreateComparisonBody) -> Dict[str, Any]:
    try:
        m = run_comparison_job(
            body.baseline_id,
            body.new_id,
            tile_px=body.tile_px,
            region_set_id=body.region_set_id,
        )
        cid = m["comparison_id"]
        return {"comparison_id": cid, "status": "complete", "manifest": m}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lulc-change/comparison/{comparison_id}/status")
def comparison_status(comparison_id: str) -> Dict[str, Any]:
    root = comparison_dir(comparison_id)
    mf = os.path.join(root, "manifest.json")
    if not os.path.isfile(mf):
        raise HTTPException(status_code=404, detail="comparison not found")
    return _read_json(mf)


@router.get("/lulc-change/comparison/{comparison_id}/summary")
def comparison_summary(comparison_id: str) -> Dict[str, Any]:
    root = comparison_dir(comparison_id)
    p = os.path.join(root, "summary.json")
    if not os.path.isfile(p):
        raise HTTPException(status_code=404, detail="summary not found")
    return _read_json(p)


@router.get("/lulc-change/comparison/{comparison_id}/transition-matrix")
def comparison_transition_matrix(comparison_id: str) -> Dict[str, Any]:
    root = comparison_dir(comparison_id)
    p = os.path.join(root, "transition_matrix.json")
    if not os.path.isfile(p):
        raise HTTPException(status_code=404, detail="transition_matrix not found")
    return _read_json(p)


@router.get("/lulc-change/comparison/{comparison_id}/classes")
def comparison_classes(
    comparison_id: str,
    class_idx: int = Query(0, ge=0, le=14, alias="class_idx"),
    top_n_regions: int = Query(5, ge=1, le=50),
    top_n_tiles: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    root = comparison_dir(comparison_id)
    summary_path = os.path.join(root, "summary.json")
    if not os.path.isfile(summary_path):
        raise HTTPException(status_code=404, detail="summary not found")
    summary = _read_json(summary_path)
    labels = summary.get("labels") or []

    ranked_path = os.path.join(root, "tiles_ranked_top.json")
    top_tiles = []
    if os.path.isfile(ranked_path):
        ranked = _read_json(ranked_path).get("items") or []
        scored = []
        for t in ranked:
            hb = t.get("hist_baseline") or [0] * 15
            hn = t.get("hist_new") or [0] * 15
            if class_idx < len(hb):
                scored.append((abs(hn[class_idx] - hb[class_idx]), t))
        scored.sort(key=lambda x: -x[0])
        top_tiles = [x[1] for x in scored[:top_n_tiles]]

    top_regions = []
    ri_path = os.path.join(root, "regions_index.json")
    if os.path.isfile(ri_path):
        idx = _read_json(ri_path).get("regions") or []
        scored_r = []
        for r in idx:
            rp = os.path.join(root, r.get("file", ""))
            if os.path.isfile(rp):
                rs = _read_json(rp)
                hb = rs.get("hist_baseline") or []
                hn = rs.get("hist_new") or []
                if class_idx < len(hb):
                    scored_r.append((abs(hn[class_idx] - hb[class_idx]), rs))
        scored_r.sort(key=lambda x: -x[0])
        top_regions = [x[1] for x in scored_r[:top_n_regions]]

    pb = summary.get("percent_baseline") or []
    pn = summary.get("percent_new") or []
    ha = summary.get("histogram_baseline") or []
    hb = summary.get("histogram_new") or []

    def area_like(cnt):
        pa = summary.get("pixel_area_m2")
        if pa and isinstance(pa, (int, float)):
            return round(cnt * float(pa), 2)
        return None

    return {
        "class_idx": class_idx,
        "label": labels[class_idx] if class_idx < len(labels) else str(class_idx),
        "percent_baseline": pb[class_idx] if class_idx < len(pb) else None,
        "percent_new": pn[class_idx] if class_idx < len(pn) else None,
        "delta_percent": (
            float(pn[class_idx]) - float(pb[class_idx])
            if class_idx < len(pn) and class_idx < len(pb)
            else None
        ),
        "pixel_count_baseline": ha[class_idx] if class_idx < len(ha) else None,
        "pixel_count_new": hb[class_idx] if class_idx < len(hb) else None,
        "area_m2_baseline": area_like(ha[class_idx]) if class_idx < len(ha) else None,
        "area_m2_new": area_like(hb[class_idx]) if class_idx < len(hb) else None,
        "top_tiles": top_tiles,
        "top_regions": top_regions,
    }


@router.get("/lulc-change/comparison/{comparison_id}/regions")
def comparison_regions(comparison_id: str) -> Dict[str, Any]:
    root = comparison_dir(comparison_id)
    ri_path = os.path.join(root, "regions_index.json")
    if not os.path.isfile(ri_path):
        return {"items": [], "total": 0}
    idx = _read_json(ri_path).get("regions") or []
    items = []
    for r in idx:
        rp = os.path.join(root, r.get("file", ""))
        if os.path.isfile(rp):
            items.append(_read_json(rp))
    return {"items": items, "total": len(items)}


@router.get("/lulc-change/comparison/{comparison_id}/tiles")
def comparison_tiles(
    comparison_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    root = comparison_dir(comparison_id)
    ranked_path = os.path.join(root, "tiles_ranked_top.json")
    if os.path.isfile(ranked_path):
        data = _read_json(ranked_path)
        items = data.get("items") or []
        total = data.get("total") or len(items)
        return {"items": items[offset : offset + limit], "total": total}
    # fallback: merge chunks
    chunks = sorted(glob.glob(os.path.join(root, "tiles_chunks", "chunk_*.json")))
    all_items: List[Dict[str, Any]] = []
    for c in chunks:
        all_items.extend((_read_json(c).get("items") or []))
    total = len(all_items)
    return {"items": all_items[offset : offset + limit], "total": total}


@router.get("/lulc-change/comparison/{comparison_id}/tiles/{tile_id}")
def comparison_tile_detail(comparison_id: str, tile_id: str) -> Dict[str, Any]:
    root = comparison_dir(comparison_id)
    ranked_path = os.path.join(root, "tiles_ranked_top.json")
    if os.path.isfile(ranked_path):
        for t in _read_json(ranked_path).get("items") or []:
            if t.get("tile_id") == tile_id:
                return t
    for c in sorted(glob.glob(os.path.join(root, "tiles_chunks", "chunk_*.json"))):
        for t in _read_json(c).get("items") or []:
            if t.get("tile_id") == tile_id:
                return t
    raise HTTPException(status_code=404, detail="tile not found")


class LocalInsightBody(BaseModel):
    comparison_id: str
    lon: float
    lat: float
    window_px: int = Field(31, ge=3, le=251)


@router.post("/lulc-change/local-insight")
def local_insight(body: LocalInsightBody) -> Dict[str, Any]:
    root = comparison_dir(body.comparison_id)
    mf = os.path.join(root, "manifest.json")
    if not os.path.isfile(mf):
        raise HTTPException(status_code=404, detail="comparison not found")
    manifest = _read_json(mf)
    bid = manifest.get("baseline_id")
    nid = manifest.get("new_id")
    if not bid or not nid:
        raise HTTPException(status_code=400, detail="invalid manifest")

    base_tif = compute._class_tif_path(bid)
    new_tif = compute._class_tif_path(nid)
    try:
        ba, na, transform, crs, _pa = compute.align_baseline_to_new(base_tif, new_tif)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    nodata = manifest.get("alignment", {}).get("nodata", compute.NODATA_DEFAULT)
    rc = compute.lonlat_to_rc(transform, crs, body.lon, body.lat)
    if rc is None:
        raise HTTPException(status_code=400, detail="could not map lon/lat to raster")
    row, col = rc
    meta_n = compute.load_prediction_meta(nid)
    id2 = id2label_from_meta(meta_n)

    win = compute.local_window(ba, na, row, col, body.window_px, nodata)
    labs = [id2.get(str(i), str(i)) for i in range(compute.NUM_CLASSES)]
    win["labels"] = labs
    win["comparison_id"] = body.comparison_id
    win["lon"] = body.lon
    win["lat"] = body.lat
    return win


class RegionSetBody(BaseModel):
    set_id: str
    geojson: Dict[str, Any]


@router.post("/lulc-change/region-set")
def upload_region_set(body: RegionSetBody) -> Dict[str, Any]:
    """Store GeoJSON FeatureCollection under region_sets/<set_id>/regions.geojson"""
    if not body.set_id or ".." in body.set_id or "/" in body.set_id:
        raise HTTPException(status_code=400, detail="invalid set_id")
    d = region_set_dir(body.set_id)
    ensure_dir(d)
    path = os.path.join(d, "regions.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body.geojson, f, indent=2, ensure_ascii=False)
    man = {"set_id": body.set_id, "path": path}
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2, ensure_ascii=False)
    return {"ok": True, "set_id": body.set_id, "path": path}


@router.get("/lulc-change/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "archive": get_change_archive_root()}
