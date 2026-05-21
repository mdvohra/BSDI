"""
Shared post-processing for tiled detection outputs (UNet footprints, Mask R-CNN, Oil pad).

Primarily IoU-based deduplication: overlapping tiles often produce duplicate or partial
geometries for the same object. Set DETECTION_IOU_DEDUPE=0 to skip deduplication.

Environment (regularization — ArcGIS-style footprint cleanup, native CRS units):

    DETECTION_REGULARIZE_MODE — ``off`` (default), ``simplify``, ``oriented_rectangle``,
    ``axis_aligned_envelope``. Aliases for off: empty, ``0``, ``false``, ``no``, ``none``.

    DETECTION_REGULARIZE_TOLERANCE — required for ``simplify``: max deviation (same units as
    geometry CRS, e.g. metres on projected data). If mode is ``simplify`` and tolerance is
    unset or ≤0, regularization is skipped. Ignored for rectangle modes.

    Use projected CRS for predictable metre tolerances; geographic CRS uses degrees.

    DETECTION_MIN_POLYGON_AREA_M2 — drop polygons whose area is strictly below this value (same
    square units as geometry CRS, e.g. m² on projected rasters). Unset or ``0`` disables.
    Applied after regularization wherever ``regularize_detection_polygons`` runs.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid

logger = logging.getLogger(__name__)


def _normalize_regularize_mode(raw: Optional[str]) -> str:
    s = (raw or "off").strip().lower()
    if s in ("", "off", "0", "false", "no", "none"):
        return "off"
    if s in ("simplify", "oriented_rectangle", "axis_aligned_envelope"):
        return s
    logger.warning("Unknown DETECTION_REGULARIZE_MODE=%r; treating as off", raw)
    return "off"


def _detection_regularize_tolerance() -> float:
    try:
        return float((os.environ.get("DETECTION_REGULARIZE_TOLERANCE") or "").strip() or "0")
    except ValueError:
        return 0.0


def _detection_min_polygon_area_m2() -> float:
    try:
        return max(0.0, float((os.environ.get("DETECTION_MIN_POLYGON_AREA_M2") or "").strip() or "0"))
    except ValueError:
        return 0.0


def filter_detection_polygons_by_min_area(
    polygons: List,
    *,
    min_area_m2: Optional[float] = None,
) -> List[Polygon]:
    """Drop polygons smaller than ``min_area_m2`` (native CRS area units).

    When ``min_area_m2`` is omitted, uses ``DETECTION_MIN_POLYGON_AREA_M2``; ``0`` or unset = no filter.
    """
    flat = _flatten_input_polygons(polygons)
    if not flat:
        return []
    if min_area_m2 is None:
        thr = _detection_min_polygon_area_m2()
    else:
        thr = max(0.0, float(min_area_m2))
    if thr <= 0:
        return flat
    kept = [p for p in flat if _area(p) >= thr]
    if len(kept) < len(flat):
        logger.info(
            "detection postprocess: min-area filter ≥%.6g (CRS²): %s → %s polygons",
            thr,
            len(flat),
            len(kept),
        )
    return kept


def _flatten_input_polygons(polygons: List) -> List[Polygon]:
    flat: List[Polygon] = []
    for p in polygons:
        if p is None:
            continue
        g = p if getattr(p, "is_valid", True) else make_valid(p)
        for poly in _to_polygons(g):
            if _area(poly) > 0:
                flat.append(poly)
    return flat


def regularize_polygon(geom, mode: str, tolerance: float) -> List[Polygon]:
    """Apply one regularization ``mode`` to a single geometry; returns zero or more polygons."""
    if geom is None or getattr(geom, "is_empty", True):
        return []
    g = geom if getattr(geom, "is_valid", True) else make_valid(geom)
    if g is None or g.is_empty:
        return []
    parts = _to_polygons(g)
    out: List[Polygon] = []
    for p in parts:
        if _area(p) <= 0:
            continue
        try:
            if mode == "simplify":
                if tolerance <= 0:
                    out.append(p)
                    continue
                rp = p.simplify(tolerance, preserve_topology=True)
                gg = rp if getattr(rp, "is_valid", True) else make_valid(rp)
                for q in _to_polygons(gg):
                    if _area(q) > 0:
                        out.append(q)
            elif mode == "oriented_rectangle":
                r = p.minimum_rotated_rectangle
                if isinstance(r, Polygon) and _area(r) > 0:
                    out.append(r)
            elif mode == "axis_aligned_envelope":
                env = p.envelope
                gg = env if getattr(env, "is_valid", True) else make_valid(env)
                for q in _to_polygons(gg):
                    if _area(q) > 0:
                        out.append(q)
            else:
                out.append(p)
        except Exception:
            logger.debug("regularize_polygon: keeping original part after failure", exc_info=True)
            out.append(p)
    return out


def regularize_detection_polygons(
    polygons: List,
    *,
    mode: Optional[str] = None,
    tolerance: Optional[float] = None,
    min_polygon_area_m2: Optional[float] = None,
) -> List[Polygon]:
    """Optional footprint regularization controlled by env (or overrides).

    See module docstring for ``DETECTION_REGULARIZE_MODE``, ``DETECTION_REGULARIZE_TOLERANCE``,
    and ``DETECTION_MIN_POLYGON_AREA_M2``.
    """
    if not polygons:
        return []

    def _after_regularize(result: List[Polygon]) -> List[Polygon]:
        return filter_detection_polygons_by_min_area(result, min_area_m2=min_polygon_area_m2)

    m = _normalize_regularize_mode(mode if mode is not None else os.environ.get("DETECTION_REGULARIZE_MODE"))
    tol = _detection_regularize_tolerance() if tolerance is None else float(tolerance)

    if m == "off":
        return _after_regularize(_flatten_input_polygons(polygons))

    if m == "simplify" and tol <= 0:
        logger.debug(
            "detection regularize: mode=simplify but tolerance<=0; skipping (set DETECTION_REGULARIZE_TOLERANCE)"
        )
        return _after_regularize(_flatten_input_polygons(polygons))

    out: List[Polygon] = []
    for p in polygons:
        out.extend(regularize_polygon(p, m, tol))
    if m != "off" and out:
        logger.info("detection postprocess: regularize mode=%s → %s polygons", m, len(out))
    return _after_regularize(out)


def _area(g) -> float:
    try:
        return float(g.area) if g is not None and not g.is_empty else 0.0
    except Exception:
        return 0.0


def _to_polygons(geom) -> List[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
    if isinstance(geom, GeometryCollection):
        out: List[Polygon] = []
        for g in geom.geoms:
            out.extend(_to_polygons(g))
        return out
    return []


def _iou(a: Polygon, b: Polygon) -> float:
    try:
        aa = a if a.is_valid else make_valid(a)
        bb = b if b.is_valid else make_valid(b)
        inter = aa.intersection(bb)
        union = aa.union(bb)
        ia, ua = inter.area, union.area
        return float(ia / ua) if ua > 1e-12 else 0.0
    except Exception:
        return 0.0


def dedupe_detection_polygons(
    polygons: List,
    *,
    iou_threshold: float | None = None,
) -> List[Polygon]:
    """Drop near-duplicate polygons (typical of overlapping tile inference).

    Keeps polygons in descending area order; skips a polygon if it is mostly inside an
    already-kept polygon or if IoU with any kept polygon exceeds the threshold.

    Environment:
        DETECTION_IOU_DEDUPE — default ``0.35``; set to ``0`` to disable.
    """
    if not polygons:
        return []
    if iou_threshold is None:
        try:
            thr = float(os.environ.get("DETECTION_IOU_DEDUPE", "0.35"))
        except ValueError:
            thr = 0.35
    else:
        thr = float(iou_threshold)
    if thr <= 0:
        out: List[Polygon] = []
        for p in polygons:
            out.extend(_to_polygons(p))
        return out

    flat: List[Polygon] = []
    for p in polygons:
        if p is None:
            continue
        g = p if getattr(p, "is_valid", True) else make_valid(p)
        for poly in _to_polygons(g):
            if _area(poly) > 0:
                flat.append(poly)

    if len(flat) <= 1:
        return flat

    flat.sort(key=_area, reverse=True)
    kept: List[Polygon] = []
    for p in flat:
        dup = False
        for k in kept:
            try:
                if p.within(k) or k.within(p):
                    dup = True
                    break
                if _iou(p, k) >= thr:
                    dup = True
                    break
            except Exception:
                continue
        if not dup:
            kept.append(p)

    if len(kept) < len(flat):
        logger.info(
            "detection postprocess: IoU dedupe %s → %s polygons (DETECTION_IOU_DEDUPE=%s)",
            len(flat),
            len(kept),
            thr,
        )
    return kept


def _auto_seam_merge_gap(polys: List[Polygon]) -> float:
    """Heuristic max gap (same units as geometry) to bridge tile chip seams without merging whole city blocks."""
    areas = [_area(p) for p in polys if _area(p) > 0]
    if not areas:
        return 1.0
    med = sorted(areas)[len(areas) // 2]
    # ~2.5% of sqrt(area): seam gaps are usually a few pixels / meters; cap vs scene size.
    gap = max(0.25, (med**0.5) * 0.025)
    try:
        u = unary_union(polys)
        minx, miny, maxx, maxy = u.bounds
        span = max(maxx - minx, maxy - miny)
        if span > 1e-12:
            gap = min(gap, span * 0.00015)
    except Exception:
        pass
    return max(gap, 1e-12)


def _merge_polygon_cluster(geoms: List[Polygon], buf: float) -> List[Polygon]:
    """Bridge sub-``buf`` gaps inside a cluster (chip seam), then return valid polygon(s)."""
    if len(geoms) == 1:
        return [g for g in geoms if isinstance(g, Polygon) and not g.is_empty]
    b = max(buf * 0.5, 1e-12)
    try:
        inflated = unary_union([g.buffer(b) for g in geoms])
        shrunk = inflated.buffer(-b)
        out = _to_polygons(shrunk)
        if out:
            return out
    except Exception:
        pass
    try:
        u = unary_union(geoms)
        return _to_polygons(u)
    except Exception:
        return geoms


def merge_chip_seam_polygons(
    polygons: List,
    *,
    max_gap: Optional[float] = None,
) -> List[Polygon]:
    """Merge pairs/groups of polygons separated only by a **small** gap (typical chip/tile seam).

    IoU-based dedupe does not merge these (near-zero overlap). This step clusters polygons whose
    pairwise distance is at most ``max_gap``, then bridges gaps with a small buffer/union.

    Does **not** merge unrelated buildings that are farther apart than ``max_gap``.

    Environment:
        ``DETECTION_SEAM_MERGE_GAP`` — max distance to merge (same units as input coordinates).
        Unset = auto from footprint scale. ``0`` / ``false`` / ``off`` = disable.
    """
    flat: List[Polygon] = []
    for p in polygons:
        if p is None:
            continue
        g = p if getattr(p, "is_valid", True) else make_valid(p)
        for poly in _to_polygons(g):
            if _area(poly) > 0:
                flat.append(poly)
    if len(flat) <= 1:
        return flat

    gap_env = (os.environ.get("DETECTION_SEAM_MERGE_GAP") or "").strip().lower()
    if gap_env in ("0", "false", "no", "off"):
        return flat

    if max_gap is None:
        if gap_env:
            try:
                max_gap = float(gap_env)
            except ValueError:
                max_gap = _auto_seam_merge_gap(flat)
        else:
            max_gap = _auto_seam_merge_gap(flat)

    if max_gap <= 0:
        return flat

    n = len(flat)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            try:
                if flat[i].distance(flat[j]) <= max_gap:
                    union(i, j)
            except Exception:
                continue

    clusters: dict[int, List[int]] = {}
    for i in range(n):
        r = find(i)
        clusters.setdefault(r, []).append(i)

    merged: List[Polygon] = []
    for _root, idxs in clusters.items():
        geoms = [flat[i] for i in idxs]
        if len(geoms) == 1:
            merged.extend(geoms)
        else:
            merged.extend(_merge_polygon_cluster(geoms, max_gap))

    if len(merged) < len(flat):
        logger.info(
            "detection postprocess: chip-seam merge %s → %s polygons (max_gap=%.6g)",
            len(flat),
            len(merged),
            max_gap,
        )
    return merged


def finalize_instance_detection_polygons(
    polygons: List,
    *,
    iou_threshold: Optional[float] = None,
    seam_merge_gap: Optional[float] = None,
    merge_touching: Optional[bool] = None,
    regularize_mode: Optional[str] = None,
    regularize_tolerance: Optional[float] = None,
) -> List[Polygon]:
    """IoU-dedupe tile overlap, then export **separate** footprints by default.

    ``unary_union`` was merging all touching buildings into one polygon. By default we **do not**
    merge touching buildings — only drop near-duplicates from overlapping tiles (see
    ``dedupe_detection_polygons``).

    Environment:
        ``DETECTION_MERGE_TOUCHING`` — set to ``1`` to restore merging of touching/overlapping
        footprints via ``unary_union`` (legacy behavior). Overridden when ``merge_touching`` is
        passed explicitly.

    ``merge_chip_seam_polygons`` runs after dedupe to join same-building fragments split across
    tile boundaries (see ``DETECTION_SEAM_MERGE_GAP``). Overridden by ``seam_merge_gap`` when set.

    ``regularize_detection_polygons`` runs last (see ``DETECTION_REGULARIZE_*``). Overridden by
    ``regularize_mode`` / ``regularize_tolerance`` when passed.
    """
    deduped = dedupe_detection_polygons(polygons, iou_threshold=iou_threshold)
    deduped = merge_chip_seam_polygons(deduped, max_gap=seam_merge_gap)
    if not deduped:
        return []
    if merge_touching is None:
        merge = (os.environ.get("DETECTION_MERGE_TOUCHING") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
    else:
        merge = bool(merge_touching)
    if not merge:
        result: List[Polygon] = deduped
    else:
        try:
            u = unary_union(deduped)
        except Exception as e:
            logger.warning("finalize_instance_detection_polygons: unary_union failed (%s); keeping deduped list", e)
            result = deduped
        else:
            if isinstance(u, Polygon):
                result = [u] if not u.is_empty else []
            elif isinstance(u, MultiPolygon):
                result = [g for g in u.geoms if isinstance(g, Polygon) and not g.is_empty]
            else:
                flat = _to_polygons(u)
                result = flat if flat else deduped
    return regularize_detection_polygons(
        result,
        mode=regularize_mode,
        tolerance=regularize_tolerance,
    )
