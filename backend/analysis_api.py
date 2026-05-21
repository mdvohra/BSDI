"""
Analysis API: catalog, enriched prediction metadata, pairwise compare, LLM chat (gpt-4o).
Mounted on main_app at /api/analysis.
"""

from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

_backend_root = os.path.dirname(os.path.abspath(__file__))
_lulc_predictions_dir = os.path.normpath(os.path.join(_backend_root, "lulc", "predictions"))

from prediction_archive import (
    delete_all_archived_predictions,
    delete_prediction_run,
    list_manifests,
    read_manifest,
    validate_run_id,
)

router = APIRouter(tags=["analysis"])

_LULC_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-fA-F]{8}$")

# LLM context size guard (~chars of JSON)
_MAX_CONTEXT_CHARS = 120_000


def _safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _artifact_geojson_path(m: Dict[str, Any]) -> Optional[str]:
    art = m.get("artifacts") or {}
    p = art.get("geojson")
    if p and os.path.isfile(p):
        return p
    return None


def _artifact_buildings_lulc(m: Dict[str, Any]) -> Optional[str]:
    art = m.get("artifacts") or {}
    p = art.get("buildings_geojson") or art.get("buildings_full_geojson")
    if p and os.path.isfile(p):
        return p
    return None


def _derive_geojson_stats(geojson_path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "geojson_path": geojson_path,
        "feature_count": 0,
        "geometry_types": {},
        "bounds_wgs84": None,
        "area_sum_m2_approx": None,
        "confidence_histogram": None,
        "error": None,
    }
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = gpd.read_file(geojson_path)
        if gdf.empty:
            return out
        out["feature_count"] = int(len(gdf))
        for t in gdf.geometry.geom_type:
            out["geometry_types"][t] = out["geometry_types"].get(t, 0) + 1
        if gdf.crs is not None and str(gdf.crs) != "EPSG:4326":
            gdf_w = gdf.to_crs(4326)
        else:
            gdf_w = gdf
        b = gdf_w.total_bounds
        if len(b) == 4 and all(math.isfinite(float(x)) for x in b):
            out["bounds_wgs84"] = [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
        try:
            gdf_a = gdf_w.copy()
            c = gdf_a.unary_union.centroid
            if isinstance(c, Point):
                lon, lat = c.x, c.y
                utm = int((lon + 180) / 6) + 1
                epsg = 32600 + utm if lat >= 0 else 32700 + utm
                gdf_p = gdf_a.to_crs(epsg=epsg)
                out["area_sum_m2_approx"] = float(gdf_p.geometry.area.sum())
        except Exception:
            try:
                out["area_sum_m2_approx"] = float(gdf_w.geometry.area.sum())
            except Exception:
                pass
        if "confidence" in gdf.columns:
            conf = gdf["confidence"].dropna()
            bins = [0, 0.2, 0.4, 0.6, 0.8, 1.01]
            hist = {f"{bins[i]}-{bins[i+1]}": int(((conf >= bins[i]) & (conf < bins[i + 1])).sum()) for i in range(len(bins) - 1)}
            out["confidence_histogram"] = hist
    except Exception as e:
        out["error"] = str(e)
    return out


def _load_lulc_json(pred_id: str) -> Optional[Dict[str, Any]]:
    p = os.path.join(_lulc_predictions_dir, pred_id + ".json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _lulc_folder_name(pred_id: str) -> str:
    return f"lulc_{pred_id}"


def _raw_meta_for_llm(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Copy for LLM; trim huge vectors if needed."""
    if not meta:
        return {}
    raw = json.loads(json.dumps(meta))

    def trim_probs(d: Dict[str, Any]) -> None:
        cp = d.get("class_probs")
        if isinstance(cp, list) and len(cp) > 64:
            d["class_probs"] = cp[:64]
            d["class_probs_truncated"] = True
            d["class_probs_len"] = len(cp)

    if isinstance(raw, dict):
        trim_probs(raw)
    return raw


def build_prediction_bundle(task: str, pred_id: str) -> Dict[str, Any]:
    task = task.lower().strip()
    if task not in ("unet", "maskrcnn", "lulc", "solar_panel"):
        raise HTTPException(
            status_code=400,
            detail="task must be unet, maskrcnn, solar_panel, or lulc",
        )

    if task == "lulc":
        if not _LULC_ID_RE.match(pred_id):
            raise HTTPException(status_code=400, detail="Invalid LULC prediction id")
        m = read_manifest(_lulc_folder_name(pred_id))
        lulc_raw = _load_lulc_json(pred_id)
        if not m and not lulc_raw:
            raise HTTPException(status_code=404, detail="LULC prediction not found")
        raw: Dict[str, Any] = dict(m) if m else {"task": "lulc", "run_id": pred_id}
        if lulc_raw:
            raw["lulc_meta_json"] = lulc_raw
        derived: Dict[str, Any] = {
            "task": "lulc",
            "top_class": lulc_raw.get("top_class") if lulc_raw else None,
            "top_pct": lulc_raw.get("top_pct") if lulc_raw else None,
            "bounds": lulc_raw.get("bounds") if lulc_raw else None,
            "seg_mode": lulc_raw.get("seg_mode") if lulc_raw else None,
            "geotiff_available": bool(lulc_raw.get("geotiff_available")) if lulc_raw else None,
            "has_building_detection": bool(lulc_raw.get("building_detection")) if lulc_raw else False,
            "class_probs_top5": None,
            "building_geojson_derived": None,
        }
        cls_tif = os.path.join(_lulc_predictions_dir, pred_id + "_classes.tif")
        derived["class_geotiff_available"] = os.path.isfile(cls_tif)

        if lulc_raw and isinstance(lulc_raw.get("class_probs"), list):
            probs = lulc_raw["class_probs"]
            id2 = lulc_raw.get("id2label") or {}
            idx_sorted = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)[:5]
            derived["class_probs_top5"] = [
                {"index": i, "label": id2.get(str(i), str(i)), "prob": probs[i]}
                for i in idx_sorted
                if i < len(probs)
            ]
        bpath = os.path.join(_lulc_predictions_dir, pred_id + "_buildings.geojson")
        if os.path.isfile(bpath):
            derived["building_geojson_derived"] = _derive_geojson_stats(bpath)
        elif m:
            bp = _artifact_buildings_lulc(m)
            if bp:
                derived["building_geojson_derived"] = _derive_geojson_stats(bp)

        png_path = os.path.join(_lulc_predictions_dir, pred_id + ".png")
        base_png_path_disk = os.path.join(_lulc_predictions_dir, pred_id + "_base.png")
        visual: Dict[str, Any] = {
            "overlay_png_path": f"/lulc/predictions/{pred_id}/overlay.png" if os.path.isfile(png_path) else None,
            "base_png_path": f"/lulc/predictions/{pred_id}/base.png" if os.path.isfile(base_png_path_disk) else None,
            "classes_geotiff_path": (
                f"/lulc/predictions/{pred_id}/classes-geotiff" if derived["class_geotiff_available"] else None
            ),
        }
        if lulc_raw is not None and lulc_raw.get("class_grid_nodata") is not None:
            visual["class_grid_nodata"] = lulc_raw.get("class_grid_nodata")
        derived["visual"] = visual

        return {"task": task, "id": pred_id, "raw": raw, "derived": derived}

    if not validate_run_id(pred_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")

    m = read_manifest(pred_id)
    if not m or m.get("task") != task:
        raise HTTPException(status_code=404, detail="Prediction not found")

    raw = dict(m)
    derived: Dict[str, Any] = {
        "task": task,
        "model_name": m.get("model_name"),
        "source_filename": m.get("source_filename"),
        "inference_threshold": m.get("inference_threshold"),
        "created_at": m.get("created_at"),
        "width": m.get("width"),
        "height": m.get("height"),
        "score_floor": m.get("score_floor"),
        "geojson_derived": None,
        "full_geojson_derived": None,
    }

    gp = _artifact_geojson_path(m)
    if gp:
        derived["geojson_derived"] = _derive_geojson_stats(gp)

    art = m.get("artifacts") or {}
    fg = art.get("full_geojson")
    if fg and os.path.isfile(fg) and task == "maskrcnn":
        derived["full_geojson_derived"] = _derive_geojson_stats(fg)

    return {"task": task, "id": pred_id, "raw": raw, "derived": derived}


def _compare_scalar(a: Any, b: Any) -> Dict[str, Any]:
    return {"a": a, "b": b, "delta": _safe_float(a) - _safe_float(b) if _safe_float(a) is not None and _safe_float(b) is not None else None}


@router.get("/catalog")
def get_catalog(limit: int = 200) -> Dict[str, Any]:
    limit = max(1, min(limit, 500))
    unet = list_manifests(task="unet", limit=limit)
    mrcnn = list_manifests(task="maskrcnn", limit=limit)
    solar = list_manifests(task="solar_panel", limit=limit)
    lulc = list_manifests(task="lulc", limit=limit)

    od: List[Dict[str, Any]] = []
    for m in unet:
        rid = m.get("run_id")
        if not rid:
            continue
        art = m.get("artifacts") or {}
        od.append(
            {
                "task": "unet",
                "id": rid,
                "created_at": m.get("created_at"),
                "model_name": m.get("model_name"),
                "source_filename": m.get("source_filename"),
                "inference_threshold": m.get("inference_threshold"),
                "has_geojson": bool(art.get("geojson") and os.path.isfile(str(art.get("geojson")))),
                "width": m.get("width"),
                "height": m.get("height"),
            }
        )
    for m in solar:
        rid = m.get("run_id")
        if not rid:
            continue
        art = m.get("artifacts") or {}
        od.append(
            {
                "task": "solar_panel",
                "id": rid,
                "created_at": m.get("created_at"),
                "model_name": m.get("model_name"),
                "source_filename": m.get("source_filename"),
                "inference_threshold": m.get("inference_threshold"),
                "has_geojson": bool(art.get("geojson") and os.path.isfile(str(art.get("geojson")))),
                "width": m.get("width"),
                "height": m.get("height"),
            }
        )
    for m in mrcnn:
        rid = m.get("run_id")
        if not rid:
            continue
        art = m.get("artifacts") or {}
        od.append(
            {
                "task": "maskrcnn",
                "id": rid,
                "created_at": m.get("created_at"),
                "model_name": m.get("model_name"),
                "source_filename": m.get("source_filename"),
                "inference_threshold": m.get("inference_threshold"),
                "score_floor": m.get("score_floor"),
                "has_geojson": bool(art.get("geojson") and os.path.isfile(str(art.get("geojson")))),
                "has_full_geojson": bool(art.get("full_geojson") and os.path.isfile(str(art.get("full_geojson")))),
            }
        )

    lulc_out: List[Dict[str, Any]] = []
    for m in lulc:
        rid = m.get("run_id")
        if not rid:
            continue
        lj = _load_lulc_json(rid)
        lulc_out.append(
            {
                "task": "lulc",
                "id": rid,
                "created_at": m.get("created_at") or (lj or {}).get("created_at"),
                "model_name": m.get("model_name"),
                "source_filename": m.get("source_filename") or (lj or {}).get("original_filename"),
                "seg_mode": m.get("seg_mode") or (lj or {}).get("seg_mode"),
                "top_class": (lj or {}).get("top_class"),
                "has_buildings": bool((lj or {}).get("building_detection")),
                "geotiff_available": bool((lj or {}).get("geotiff_available")),
            }
        )

    return {"object_detection": od, "lulc": lulc_out}


@router.delete("/prediction/{task}/{pred_id}")
def delete_catalog_prediction(task: str, pred_id: str) -> Dict[str, Any]:
    t = (task or "").strip().lower()
    r = delete_prediction_run(t, pred_id)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("error", "delete failed")))
    return r


class DeleteAllPredictionsBody(BaseModel):
    confirm: bool = False


@router.post("/predictions/delete-all")
def delete_every_archived_prediction(body: DeleteAllPredictionsBody) -> Dict[str, Any]:
    """Remove all archived runs (UNet, Mask R-CNN, LULC) from disk under the prediction archive."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail='Set "confirm": true in the JSON body.')
    out = delete_all_archived_predictions()
    if not out.get("ok"):
        raise HTTPException(status_code=500, detail=str(out.get("error", "delete-all failed")))
    return out


@router.get("/prediction/{task}/{pred_id}")
def get_prediction(task: str, pred_id: str) -> Dict[str, Any]:
    return build_prediction_bundle(task, pred_id)


class PredictionRef(BaseModel):
    task: str
    id: str


class CompareBody(BaseModel):
    primary: PredictionRef
    secondary: PredictionRef


def _compare_two(p: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    pt, st = p.get("task"), s.get("task")
    pd, sd = p.get("derived") or {}, s.get("derived") or {}

    out: Dict[str, Any] = {
        "primary": {"task": pt, "id": p.get("id")},
        "secondary": {"task": st, "id": s.get("id")},
    }

    if pt in ("unet", "maskrcnn", "solar_panel") and st in ("unet", "maskrcnn", "solar_panel"):
        gpd, gsd = pd.get("geojson_derived") or {}, sd.get("geojson_derived") or {}
        out["detection_comparison"] = {
            "feature_count": _compare_scalar(gpd.get("feature_count"), gsd.get("feature_count")),
            "area_sum_m2_approx": _compare_scalar(gpd.get("area_sum_m2_approx"), gsd.get("area_sum_m2_approx")),
            "bounds_primary": gpd.get("bounds_wgs84"),
            "bounds_secondary": gsd.get("bounds_wgs84"),
        }

    if pt == "lulc" and st == "lulc":
        lp, ls = _load_lulc_json(p.get("id")), _load_lulc_json(s.get("id"))
        if lp and ls:
            cp, cs = lp.get("class_probs") or [], ls.get("class_probs") or []
            n = min(len(cp), len(cs))
            diffs = [float(cp[i]) - float(cs[i]) for i in range(n)] if n else []
            out["lulc_class_prob_delta"] = {
                "length": n,
                "max_abs_delta": max((abs(d) for d in diffs), default=0),
                "sum_abs_delta": sum(abs(d) for d in diffs),
            }
            out["top_class_change"] = {
                "primary": lp.get("top_class"),
                "secondary": ls.get("top_class"),
            }

    if (pt in ("unet", "maskrcnn", "solar_panel") and st == "lulc") or (
        pt == "lulc" and st in ("unet", "maskrcnn", "solar_panel")
    ):
        out["note"] = "Cross-type comparison: compare detection feature counts to LULC building overlay or class distribution qualitatively using derived blocks."

    return out


@router.post("/compare")
def compare_predictions(body: CompareBody) -> Dict[str, Any]:
    try:
        pa = build_prediction_bundle(body.primary.task, body.primary.id)
        sb = build_prediction_bundle(body.secondary.task, body.secondary.id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _compare_two(pa, sb)


# ----- LLM -----

class ChatMessage(BaseModel):
    role: str
    content: str


class LLMContext(BaseModel):
    prediction_ids: List[PredictionRef] = Field(default_factory=list)


class LLMChatBody(BaseModel):
    messages: List[ChatMessage]
    context: Optional[LLMContext] = None


def _build_llm_system_content(ctx: Optional[LLMContext]) -> str:
    blocks: List[str] = []
    compare_json = ""
    if ctx and ctx.prediction_ids:
        preds: List[Dict[str, Any]] = []
        for pref in ctx.prediction_ids:
            try:
                b = build_prediction_bundle(pref.task, pref.id)
                preds.append(b)
                raw = b.get("raw") or {}
                raw_s = json.dumps(_raw_meta_for_llm(raw), ensure_ascii=False)
                der = json.dumps(b.get("derived") or {}, ensure_ascii=False)
                blocks.append(f"### Prediction {pref.task}/{pref.id}\nraw_meta:\n{raw_s}\n\nderived:\n{der}\n")
            except HTTPException as e:
                blocks.append(f"### Prediction {pref.task}/{pref.id}\n(error: {e.detail})\n")
        if len(preds) == 2:
            try:
                cmp = _compare_two(preds[0], preds[1])
                compare_json = json.dumps(cmp, ensure_ascii=False)
            except Exception as e:
                compare_json = json.dumps({"compare_error": str(e)})
    combined = "\n".join(blocks)
    if compare_json:
        combined += "\n\n## Pairwise comparison (A vs B)\n" + compare_json

    if len(combined) > _MAX_CONTEXT_CHARS:
        combined = combined[:_MAX_CONTEXT_CHARS] + "\n\n[TRUNCATED — context exceeded limit]"

    system = """You are a GIS and remote sensing analysis assistant. You receive authoritative JSON metadata and derived statistics for ML prediction runs (UNet building detection, Mask R-CNN object detection, solar-panel footprint segmentation, and LULC land-cover classification). The user may ask any question: counts, areas, differences, change detection, summaries, or requests for charts.

Rules:
- Base answers only on the provided raw_meta and derived data; if something is missing, say so.
- For comparisons, use numeric fields in derived when present.
- When the user asks for a chart or visualization, append a final fenced JSON block AFTER your prose, using exactly this shape (valid JSON):
```chart
{"chart":{"type":"bar|pie|line","title":"string","labels":["..."],"series":[{"name":"optional","values":[1,2,3]}]}}
```
Use realistic labels/values from the metadata. If a chart is not appropriate, omit the chart block."""

    if combined:
        return system + "\n\n## Attached prediction data\n" + combined
    return system


@router.post("/llm/chat")
def llm_chat(body: LLMChatBody) -> Dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not set on the server")

    try:
        from openai import OpenAI
    except ImportError:
        raise HTTPException(status_code=503, detail="openai package not installed")

    model = os.environ.get("OPENAI_ANALYSIS_MODEL", "gpt-4o").strip() or "gpt-4o"
    system_content = _build_llm_system_content(body.context)

    msgs: List[Dict[str, str]] = [{"role": "system", "content": system_content}]
    for m in body.messages:
        if m.role not in ("user", "assistant"):
            continue
        msgs.append({"role": m.role, "content": m.content})

    client = OpenAI(api_key=key)
    try:
        resp = client.chat.completions.create(model=model, messages=msgs, temperature=0.3)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

    choice = resp.choices[0] if resp.choices else None
    text = (choice.message.content or "").strip() if choice and choice.message else ""
    return {"reply": text, "model": model}


# ----- Grounded LLM (LULC change, tool calling) -----

_LULC_CHANGE_LL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_change_summary",
            "description": "Load global LULC change summary for a comparison_id (histograms, percent deltas, pixel counts).",
            "parameters": {
                "type": "object",
                "properties": {"comparison_id": {"type": "string"}},
                "required": ["comparison_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transition_matrix",
            "description": "Load class-to-class transition matrix counts for a comparison.",
            "parameters": {
                "type": "object",
                "properties": {"comparison_id": {"type": "string"}},
                "required": ["comparison_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_tiles",
            "description": "Load ranked tiles with most pixel changes for a comparison.",
            "parameters": {
                "type": "object",
                "properties": {"comparison_id": {"type": "string"}},
                "required": ["comparison_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_region_stats",
            "description": "Load per-region zonal stats if regions were computed for this comparison.",
            "parameters": {
                "type": "object",
                "properties": {"comparison_id": {"type": "string"}},
                "required": ["comparison_id"],
            },
        },
    },
]


class LLMQueryBody(BaseModel):
    messages: List[ChatMessage]
    comparison_id: Optional[str] = None


def _lulc_change_archive_root() -> str:
    return os.path.normpath(
        os.environ.get("LULC_CHANGE_ARCHIVE_DIR", os.path.join(_backend_root, "lulc_change_archive"))
    )


def _read_comparison_json(rel_path: str, comparison_id: str) -> Dict[str, Any]:
    root = os.path.join(_lulc_change_archive_root(), "comparisons", comparison_id)
    path = os.path.join(root, rel_path)
    if not os.path.isfile(path):
        return {"error": "not_found", "path": rel_path}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"error": str(e), "path": rel_path}


def _exec_change_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    cid = (arguments or {}).get("comparison_id") or ""
    if not cid:
        return {"error": "comparison_id required"}
    if name == "get_change_summary":
        return _read_comparison_json("summary.json", cid)
    if name == "get_transition_matrix":
        return _read_comparison_json("transition_matrix.json", cid)
    if name == "get_top_tiles":
        return _read_comparison_json("tiles_ranked_top.json", cid)
    if name == "get_region_stats":
        ri = _read_comparison_json("regions_index.json", cid)
        if ri.get("error"):
            return {"items": [], "note": "no regions_index"}
        items = []
        for r in ri.get("regions") or []:
            fp = r.get("file")
            if fp:
                items.append(_read_comparison_json(fp, cid))
        return {"items": items, "total": len(items)}
    return {"error": "unknown_tool", "name": name}


def _append_llm_query_log(entry: Dict[str, Any]) -> None:
    try:
        path = os.path.join(_lulc_change_archive_root(), "llm_queries.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


@router.post("/llm/query")
def llm_query_grounded(body: LLMQueryBody) -> Dict[str, Any]:
    """OpenAI chat with tools that read JSON artifacts only (no hallucinated numbers)."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not set on the server")

    try:
        from openai import OpenAI
    except ImportError:
        raise HTTPException(status_code=503, detail="openai package not installed")

    model = os.environ.get("OPENAI_ANALYSIS_MODEL", "gpt-4o").strip() or "gpt-4o"

    sys = """You answer questions about LULC change analysis using ONLY data returned by the tools.
Rules:
- Call tools when you need numbers (areas, percentages, matrices, tiles, regions).
- Quote exact numbers from tool JSON.
- If a tool returns error or not_found, say data is unavailable.
- Do not invent spatial statistics."""

    if body.comparison_id:
        sys += f"\nDefault comparison_id for tools (user-selected): {body.comparison_id}"

    msgs: List[Dict[str, Any]] = [{"role": "system", "content": sys}]
    for m in body.messages:
        if m.role not in ("user", "assistant"):
            continue
        msgs.append({"role": m.role, "content": m.content})

    client = OpenAI(api_key=key)
    tool_calls_trace: List[Dict[str, Any]] = []

    for _ in range(8):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=msgs,
                tools=_LULC_CHANGE_LL_TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

        choice = resp.choices[0] if resp.choices else None
        if not choice or not choice.message:
            break

        msg = choice.message
        if msg.tool_calls:
            msgs.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if body.comparison_id and "comparison_id" not in args:
                    args["comparison_id"] = body.comparison_id
                result = _exec_change_tool(tc.function.name, args)
                tool_calls_trace.append({"name": tc.function.name, "arguments": args, "result_keys": list(result.keys())})
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False)[: _MAX_CONTEXT_CHARS],
                    }
                )
            continue

        text = (msg.content or "").strip()
        _append_llm_query_log(
            {
                "model": model,
                "comparison_id": body.comparison_id,
                "tool_calls": tool_calls_trace,
                "reply_len": len(text),
            }
        )
        return {"reply": text, "model": model, "tool_calls": tool_calls_trace}

    raise HTTPException(status_code=502, detail="LLM did not produce a final reply")
