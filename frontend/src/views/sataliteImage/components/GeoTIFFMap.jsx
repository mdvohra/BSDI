import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import GeoTiffLoadingOverlay from "../../../components/GeoTiffLoadingOverlay";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import RoiLeafletDraw from "../../lulc/components/RoiLeafletDraw";

import parseGeoraster from "georaster";
import GeoRasterLayer from "georaster-layer-for-leaflet";
import proj4 from "proj4";
import "leaflet-draw/dist/leaflet.draw.css";

proj4.defs("EPSG:32643", "+proj=utm +zone=43 +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32644", "+proj=utm +zone=44 +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32645", "+proj=utm +zone=45 +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32646", "+proj=utm +zone=46 +datum=WGS84 +units=m +no_defs");
proj4.defs(
  "EPSG:3857",
  "+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs"
);

/** WGS84 [south, west, north, east] — same grid as Leaflet ROI; sent as roi_full_bounds_swne for Mask R-CNN clip */
function latLngBoundsToSwne(bounds) {
  if (!bounds || typeof bounds.isValid !== "function" || !bounds.isValid()) return null;
  const sw = bounds.getSouthWest();
  const ne = bounds.getNorthEast();
  return [sw.lat, sw.lng, ne.lat, ne.lng];
}

/** Leaflet [[south, west], [north, east]] — reject degenerate [[0,0],[0,0]] from API. */
function isUsableWgs84Bounds(bounds) {
  if (!bounds || !Array.isArray(bounds) || bounds.length !== 2) return false;
  const [sw, ne] = bounds;
  if (!Array.isArray(sw) || !Array.isArray(ne) || sw.length < 2 || ne.length < 2) return false;
  const latSpan = Math.abs(ne[0] - sw[0]);
  const lngSpan = Math.abs(ne[1] - sw[1]);
  return latSpan > 1e-8 || lngSpan > 1e-8;
}

// ---------- Pane + renderer ----------
const PredictionsPaneInit = () => {
  const map = useMap();

  useEffect(() => {
    if (!map.getPane("predictions-pane")) {
      map.createPane("predictions-pane");
      const paneEl = map.getPane("predictions-pane");
      paneEl.style.zIndex = 650;
      paneEl.style.pointerEvents = "auto";
    }

    if (!map._predictionsRenderer) {
      map._predictionsRenderer = L.canvas({ pane: "predictions-pane" });
    }
  }, [map]);

  return null;
};

// ---------- Swipe clip (clip renderer canvas container) ----------
const SwipePredictionsClip = ({ enabled, positionPct, onTargetEl }) => {
  const map = useMap();

  useEffect(() => {
    const computeAndApply = () => {
      const renderer = map._predictionsRenderer;
      const canvasEl = renderer && renderer._container;
      if (!canvasEl) return;

      onTargetEl?.(canvasEl);

      if (!enabled) {
        canvasEl.style.clipPath = "";
        canvasEl.style.webkitClipPath = "";
        return;
      }

      const rect = canvasEl.getBoundingClientRect();
      const pct = Math.max(0, Math.min(100, positionPct));
      const xPx = Math.round((pct / 100) * rect.width);

      const clipValue = `inset(0px 0px 0px ${xPx}px)`;
      canvasEl.style.clipPath = clipValue;
      canvasEl.style.webkitClipPath = clipValue;
    };

    computeAndApply();
    map.on("resize", computeAndApply);
    map.on("zoom", computeAndApply);
    map.on("move", computeAndApply);

    const t = window.setTimeout(computeAndApply, 50);

    return () => {
      window.clearTimeout(t);
      map.off("resize", computeAndApply);
      map.off("zoom", computeAndApply);
      map.off("move", computeAndApply);

      const renderer = map._predictionsRenderer;
      const canvasEl = renderer && renderer._container;
      if (canvasEl) {
        canvasEl.style.clipPath = "";
        canvasEl.style.webkitClipPath = "";
      }
    };
  }, [enabled, positionPct, map, onTargetEl]);

  return null;
};

// ---------- Draggable divider overlay ----------
const DraggableDivider = ({ enabled, targetEl, mapRef, swipePct, setSwipePct }) => {
  const draggingRef = useRef(false);

  useEffect(() => {
    if (!enabled || !targetEl) return;

    const stop = () => {
      draggingRef.current = false;
      if (mapRef.current) mapRef.current.dragging.enable(); // re-enable map panning [web:361]
    };

    const move = (e) => {
      if (!draggingRef.current || !targetEl) return;

      const rect = targetEl.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      setSwipePct((x / rect.width) * 100);
    };

    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("pointermove", move);

    return () => {
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("pointermove", move);
    };
  }, [enabled, targetEl, mapRef, setSwipePct]);

  if (!enabled || !targetEl) return null;

  const rect = targetEl.getBoundingClientRect();
  const xPx = Math.round((Math.max(0, Math.min(100, swipePct)) / 100) * rect.width);

  return (
    <div
      onPointerDown={(e) => {
        e.preventDefault();
        e.stopPropagation();
        draggingRef.current = true;
        if (mapRef.current) mapRef.current.dragging.disable(); // prevent map drag while dragging divider [web:361]
      }}
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        left: `${xPx}px`,
        width: 22,
        transform: "translateX(-11px)",
        zIndex: 9999,
        cursor: "col-resize",
        pointerEvents: "auto",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div style={{ width: 2, height: "100%", background: "rgba(206,17,38,0.92)" }} />
      <div
        style={{
          position: "absolute",
          width: 18,
          height: 42,
          borderRadius: 10,
          background: "rgba(255,255,255,0.95)",
          border: "1px solid rgba(0,0,0,0.15)",
          boxShadow: "0 2px 8px rgba(0,0,0,0.20)",
        }}
      />
    </div>
  );
};

// ---------- Segmentation PNG overlay (oil spill etc.) ----------
const SegmentationPaneInit = () => {
  const map = useMap();
  useEffect(() => {
    if (!map.getPane("oil-spill-seg-pane")) {
      map.createPane("oil-spill-seg-pane");
      const el = map.getPane("oil-spill-seg-pane");
      el.style.zIndex = "700";
      el.style.pointerEvents = "none";
    }
  }, [map]);
  return null;
};

const SegmentationImageOverlay = ({ imageUrl, boundsLatLng, disableAutoFit }) => {
  const map = useMap();
  const layerRef = useRef(null);

  useEffect(() => {
    if (!imageUrl || !boundsLatLng || !isUsableWgs84Bounds(boundsLatLng)) return;

    if (layerRef.current && map.hasLayer(layerRef.current)) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    const layer = L.imageOverlay(imageUrl, boundsLatLng, {
      opacity: 0.62,
      pane: "oil-spill-seg-pane",
      interactive: false,
    });
    layer.addTo(map);
    layerRef.current = layer;

    if (!disableAutoFit) {
      const b = L.latLngBounds(boundsLatLng);
      if (b.isValid()) map.fitBounds(b, { padding: [30, 30], maxZoom: 18 });
    }

    return () => {
      if (layerRef.current && map.hasLayer(layerRef.current)) {
        map.removeLayer(layerRef.current);
      }
      layerRef.current = null;
    };
  }, [imageUrl, boundsLatLng, map, disableAutoFit]);

  return null;
};

/** UNet water_body.pth: blue polygons + overlay styling (matches server PNG tint). */
function isWaterBodyModelName(name) {
  if (name == null || String(name).trim() === "") return false;
  const base = String(name).split(/[/\\]/).pop().toLowerCase().trim();
  return base === "water_body.pth" || base.includes("water_body");
}

function leafletStyleForDetectionModel(modelName, modelFamily) {
  const base = { weight: 2, opacity: 0.9, fillOpacity: 0.25 };
  const fam = (modelFamily || "").toLowerCase();
  if (fam === "esri") {
    return {
      ...base,
      weight: 2,
      fillOpacity: 0.35,
      color: "#15803d",
      fillColor: "#bbf7d0",
    };
  }
  if (isWaterBodyModelName(modelName)) {
    return { ...base, color: "#2563eb", fillColor: "#2563eb" };
  }
  return { ...base, color: "#ff0000", fillColor: "#ff0000" };
}

// ---------- Detection overlay ----------
const DetectionOverlay = ({
  detectionData,
  imageMetadata,
  detectionModelName,
  detectionModelFamily,
  disableAutoFit,
}) => {
  const map = useMap();
  const layerRef = useRef(null);
  /** Avoid fitBounds on every streaming GeoJSON refresh when raster bounds are unchanged. */
  const lastAutoFitKeyRef = useRef(null);
  /** Stable key for one inference session (bounds / URL); allows in-place GeoJSON updates while streaming. */
  const sessionRef = useRef(null);

  useEffect(() => {
    return () => {
      if (layerRef.current && map.hasLayer(layerRef.current)) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
      sessionRef.current = null;
      lastAutoFitKeyRef.current = null;
    };
  }, [map]);

  useEffect(() => {
    if (!detectionData) return;

    if (!map._predictionsRenderer) {
      map._predictionsRenderer = L.canvas({ pane: "predictions-pane" });
    }

    const modelKey = (detectionModelName || "").trim().toLowerCase();
    const famKey = (detectionModelFamily || "").trim().toLowerCase();
    const sessionKey =
      typeof detectionData === "string"
        ? `url:${detectionData}:${modelKey}:${famKey}`
        : `obj:${
            imageMetadata?.bounds && isUsableWgs84Bounds(imageMetadata.bounds)
              ? JSON.stringify(imageMetadata.bounds)
              : "nogeo"
          }:${modelKey}:${famKey}`;

    if (sessionRef.current !== sessionKey) {
      if (layerRef.current && map.hasLayer(layerRef.current)) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
      sessionRef.current = sessionKey;
      lastAutoFitKeyRef.current = null;
    }

    let abortController = null;

    const style = leafletStyleForDetectionModel(detectionModelName, detectionModelFamily);

    const onEachFeature = (feature, layer) => {
      const props = feature?.properties || {};
      layer.bindPopup(`
        <div style="font-size: 12px;">
          <strong>Detection</strong><br/>
          ${props.confidence ? `Confidence: ${(props.confidence * 100).toFixed(1)}%<br/>` : ""}
          ${props.area ? `Area: ${Number(props.area).toFixed(2)} m²` : ""}
        </div>
      `);
    };

    const tryAutoFit = (geoJsonLayer) => {
      if (disableAutoFit) return;
      const metaB = imageMetadata?.bounds;
      const metaKey =
        metaB && isUsableWgs84Bounds(metaB) ? `meta:${JSON.stringify(metaB)}` : "";
      if (metaKey && metaKey === lastAutoFitKeyRef.current) return;
      if (metaB && isUsableWgs84Bounds(metaB)) {
        const b = L.latLngBounds(metaB);
        if (b.isValid()) {
          lastAutoFitKeyRef.current = metaKey;
          map.fitBounds(b, { padding: [30, 30], maxZoom: 18 });
        }
        return;
      }
      if (geoJsonLayer.getBounds && geoJsonLayer.getBounds().isValid()) {
        const b = geoJsonLayer.getBounds();
        const gjKey = `gj:${b.getWest()},${b.getSouth()},${b.getEast()},${b.getNorth()}`;
        if (gjKey === lastAutoFitKeyRef.current) return;
        lastAutoFitKeyRef.current = gjKey;
        map.fitBounds(b, { padding: [30, 30], maxZoom: 18 });
      }
    };

    const addGeoJson = (geojson) => {
      const geoJsonLayer = L.geoJSON(geojson, {
        pane: "predictions-pane",
        renderer: map._predictionsRenderer,
        style: () => style,
        onEachFeature,
      }).addTo(map);

      layerRef.current = geoJsonLayer;
      tryAutoFit(geoJsonLayer);
    };

    if (typeof detectionData === "string") {
      abortController = new AbortController();
      fetch(detectionData, { signal: abortController.signal })
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
          return res.json();
        })
        .then((geojson) => addGeoJson(geojson))
        .catch((err) => {
          if (err?.name !== "AbortError") console.error("❌ GeoJSON fetch failed:", err);
        });

      return () => {
        if (abortController) abortController.abort();
      };
    }

    const geoJsonData = Array.isArray(detectionData)
      ? { type: "FeatureCollection", features: detectionData }
      : detectionData;

    const existing = layerRef.current;
    const canPatch =
      existing &&
      map.hasLayer(existing) &&
      typeof existing.clearLayers === "function" &&
      typeof existing.addData === "function";

    if (canPatch) {
      try {
        existing.clearLayers();
        existing.addData(geoJsonData);
        tryAutoFit(existing);
      } catch (e) {
        console.warn("Detection overlay: incremental GeoJSON update failed, recreating layer", e);
        map.removeLayer(existing);
        layerRef.current = null;
        addGeoJson(geoJsonData);
      }
    } else {
      addGeoJson(geoJsonData);
    }

    return () => {
      if (abortController) abortController.abort();
    };
  }, [detectionData, imageMetadata, detectionModelName, detectionModelFamily, disableAutoFit, map]);

  return null;
};

// ---------- GeoTIFF raster layer ----------
const GeoTIFFLayer = ({ tiffBlob, onLoadError, onMapBoundsSwne, onRasterLoadFinished }) => {
  const map = useMap();
  const layerRef = useRef(null);
  const boundsCbRef = useRef(onMapBoundsSwne);
  boundsCbRef.current = onMapBoundsSwne;
  const onDoneRef = useRef(onRasterLoadFinished);
  onDoneRef.current = onRasterLoadFinished;

  useEffect(() => {
    if (!tiffBlob) {
      boundsCbRef.current?.(null);
      return undefined;
    }
    let cancelled = false;
    onLoadError?.(null);

    const load = async () => {
      try {
        if (layerRef.current && map.hasLayer(layerRef.current)) {
          map.removeLayer(layerRef.current);
          layerRef.current = null;
        }

        let buf;
        if (typeof tiffBlob === "string") {
          const res = await fetch(tiffBlob);
          buf = await res.arrayBuffer();
        } else {
          buf = await tiffBlob.arrayBuffer();
        }

        if (cancelled) return;

        const raster = await parseGeoraster(buf);
        let projCode = raster.projection?.toString() || null;

        const addRaster = (resolution, fitBounds) => {
          const layer = new GeoRasterLayer({ georaster: raster, opacity: 1, resolution });
          layer.addTo(map);
          layerRef.current = layer;

          if (typeof boundsCbRef.current === "function" && fitBounds) {
            const swne = latLngBoundsToSwne(fitBounds);
            if (swne) boundsCbRef.current(swne);
          }

          if (fitBounds?.isValid?.() && fitBounds.isValid()) {
            map.fitBounds(fitBounds, { maxZoom: 18, padding: [50, 50] });
          }
        };

        if (!projCode || projCode === "32767" || projCode === "EPSG:32767") {
          const bounds = L.latLngBounds([raster.ymin, raster.xmin], [raster.ymax, raster.xmax]);
          const w = Math.abs(raster.xmax - raster.xmin);
          const h = Math.abs(raster.ymax - raster.ymin);
          const isSmall = w < 0.01 || h < 0.01;
          addRaster(isSmall ? 64 : 256, bounds);
          if (isSmall && bounds.isValid()) map.setView(bounds.getCenter(), 18);
          return;
        }

        const numeric = parseInt(projCode.replace("EPSG:", ""), 10);
        const isUTM =
          (numeric >= 32601 && numeric <= 32660) || (numeric >= 32701 && numeric <= 32760);

        if (isUTM) {
          const epsg = `EPSG:${numeric}`;
          if (!proj4.defs(epsg)) {
            const zone = numeric % 100;
            const south = numeric >= 32700;
            proj4.defs(
              epsg,
              `+proj=utm +zone=${zone} ${south ? "+south" : ""} +datum=WGS84 +units=m +no_defs`
            );
          }

          const corners = [
            [raster.xmin, raster.ymin],
            [raster.xmin, raster.ymax],
            [raster.xmax, raster.ymax],
            [raster.xmax, raster.ymin],
          ];

          const wgsCorners = corners.map(([x, y]) => proj4(epsg, "EPSG:4326", [x, y]).reverse());
          const lats = wgsCorners.map((c) => c[0]);
          const lngs = wgsCorners.map((c) => c[1]);

          const bounds = L.latLngBounds(
            [Math.min(...lats), Math.min(...lngs)],
            [Math.max(...lats), Math.max(...lngs)]
          );

          const bw = bounds.getEast() - bounds.getWest();
          const bh = bounds.getNorth() - bounds.getSouth();
          const isSmall = bw < 0.0001 || bh < 0.0001;

          addRaster(isSmall ? 64 : 256, bounds);
          if (isSmall && bounds.isValid()) map.setView(bounds.getCenter(), 18);
          return;
        }

        if (projCode.includes("4326")) {
          const bounds = L.latLngBounds([raster.ymin, raster.xmin], [raster.ymax, raster.xmax]);
          const bw = bounds.getEast() - bounds.getWest();
          const bh = bounds.getNorth() - bounds.getSouth();
          const isSmall = bw < 0.0001 || bh < 0.0001;

          addRaster(isSmall ? 64 : 256, bounds);
          if (isSmall && bounds.isValid()) map.setView(bounds.getCenter(), 18);
          return;
        }

        const layer = new GeoRasterLayer({ georaster: raster, opacity: 1, resolution: 256 });
        layer.addTo(map);
        layerRef.current = layer;
        if (typeof boundsCbRef.current === "function" && layer.getBounds) {
          const swne = latLngBoundsToSwne(layer.getBounds());
          if (swne) boundsCbRef.current(swne);
        }
        if (layer.getBounds) map.fitBounds(layer.getBounds(), { maxZoom: 18, padding: [50, 50] });
      } catch (err) {
        console.error("❌ TIFF load error:", err);
        if (!cancelled) {
          onLoadError?.(err?.message || String(err));
          boundsCbRef.current?.(null);
        }
      } finally {
        if (!cancelled) onDoneRef.current?.();
      }
    };

    load();

    return () => {
      cancelled = true;
      if (layerRef.current && map.hasLayer(layerRef.current)) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [tiffBlob, map, onLoadError]);

  return null;
};

function SatHexagonGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
      <polygon fill="currentColor" points="12,2 22,8 22,16 12,22 2,16 2,8" />
    </svg>
  );
}

// ---------- Main ----------
const GeoTIFFMap = ({
  tiffBlob,
  detectionData,
  imageMetadata,
  detectionModelName,
  detectionModelFamily,
  segmentationOverlayUrl,
  segmentationOverlayBounds,
  oilSpillLegendEntries,
  roiDrawActive = false,
  onRoiDrawActiveChange,
  roiGeometry,
  onRoiGeometryChange,
  onRasterMapBoundsSwne,
}) => {
  const [swipeEnabled, setSwipeEnabled] = useState(false);
  const [swipePct, setSwipePct] = useState(50);
  const [tiffError, setTiffError] = useState(null);
  const [tiffLoading, setTiffLoading] = useState(false);

  const objectsDetectedCount = (() => {
    const m = imageMetadata?.count;
    if (m != null && Number.isFinite(Number(m))) return Number(m);
    if (!detectionData) return 0;
    if (Array.isArray(detectionData.features)) return detectionData.features.length;
    if (Array.isArray(detectionData)) return detectionData.length;
    return 0;
  })();

  const showOilSpillLegend =
    Array.isArray(oilSpillLegendEntries) && oilSpillLegendEntries.length > 0;

  const mapRef = useRef(null);
  const [clipTargetEl, setClipTargetEl] = useState(null);
  /** User-drag offset from default top-right position */
  const [resultsPanelOffset, setResultsPanelOffset] = useState({ x: 0, y: 0 });
  const resultsPanelOffsetRef = useRef(resultsPanelOffset);
  resultsPanelOffsetRef.current = resultsPanelOffset;

  useEffect(() => {
    setTiffError(null);
    setResultsPanelOffset({ x: 0, y: 0 });
  }, [tiffBlob]);

  useLayoutEffect(() => {
    setTiffLoading(Boolean(tiffBlob));
  }, [tiffBlob]);

  const onResultsPanelDragStart = useCallback((e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startY = e.clientY;
    const { x: ox, y: oy } = resultsPanelOffsetRef.current;

    const onMove = (ev) => {
      setResultsPanelOffset({
        x: ox + (ev.clientX - startX),
        y: oy + (ev.clientY - startY),
      });
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }, []);

  const onResultsPanelDoubleClick = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setResultsPanelOffset({ x: 0, y: 0 });
  }, []);

  return (
    <div className="sat-geotiff-map-wrap">
      <GeoTiffLoadingOverlay visible={tiffLoading && Boolean(tiffBlob)} />
      {tiffError && (
        <div
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            right: 12,
            zIndex: 2000,
            padding: "12px 14px",
            borderRadius: 10,
            background: "rgba(127, 29, 29, 0.92)",
            color: "#fecaca",
            fontSize: 13,
            lineHeight: 1.4,
            boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
          }}
        >
          <strong style={{ color: "#fff" }}>Could not display GeoTIFF</strong>
          <div style={{ marginTop: 6, opacity: 0.95 }}>{tiffError}</div>
          <div style={{ marginTop: 8, fontSize: 12, opacity: 0.85 }}>
            Very large files may exceed browser memory. Try a smaller COG or export a subset.
          </div>
        </div>
      )}
      {/* Detection results panel — pointer-events disabled while ROI draw is active so Leaflet.draw toolbar receives clicks */}
      {imageMetadata && (
        <div
          className={`sat-results-panel${roiDrawActive ? " sat-results-panel--roi-drawing" : ""}`}
          style={{
            transform: `translate(${resultsPanelOffset.x}px, ${resultsPanelOffset.y}px)`,
          }}
        >
          <div
            className="sat-results-title sat-results-drag-handle"
            onPointerDown={onResultsPanelDragStart}
            onDoubleClick={onResultsPanelDoubleClick}
            title="Drag to move · double-click title to reset position"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            {showOilSpillLegend ? "Oil spill segmentation" : "Detection Results"}
            <span className="sat-results-drag-hint" aria-hidden>⋮⋮</span>
          </div>
          {showOilSpillLegend ? (
            <>
              <div className="sat-results-count" style={{ fontSize: 13, letterSpacing: "0.02em" }}>
                {oilSpillLegendEntries.length} classes
              </div>
              <div className="sat-results-label">Semantic mask</div>
            </>
          ) : (
            <>
              <div className="sat-results-count">{objectsDetectedCount}</div>
              <div className="sat-results-label">Objects Detected</div>
            </>
          )}
          <div className="sat-results-divider" />
          <div className="sat-results-meta">
            <strong style={{ color: 'var(--geoai-od-on-light-muted)' }}>CRS:</strong>{' '}
            {imageMetadata.crs ? imageMetadata.crs.replace(/^PROJCS\["|".*$/g, '').substring(0, 40) : 'N/A'}
          </div>
          {showOilSpillLegend && (
            <>
              <div className="sat-results-divider" />
              <div style={{ fontSize: 11, color: 'var(--geoai-od-on-light-muted)', marginBottom: 8, fontWeight: 600 }}>
                Class colors (overlay)
              </div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {oilSpillLegendEntries.map((row) => (
                  <li
                    key={row.key}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      marginBottom: 6,
                      fontSize: 12,
                      color: 'var(--geoai-od-on-light-text)',
                    }}
                  >
                    <span
                      title={row.hex}
                      style={{
                        flexShrink: 0,
                        width: 22,
                        height: 16,
                        borderRadius: 4,
                        background: row.color,
                        border: "1px solid rgba(255,255,255,0.28)",
                        boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.2)",
                      }}
                    />
                    <span style={{ lineHeight: 1.35 }}>
                      <strong style={{ color: 'var(--geoai-od-accent)', marginRight: 6 }}>{row.classId}</strong>
                      {row.label}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {/* Draggable divider */}
      <DraggableDivider
        enabled={swipeEnabled}
        targetEl={clipTargetEl}
        mapRef={mapRef}
        swipePct={swipePct}
        setSwipePct={setSwipePct}
      />

      <MapContainer
        whenCreated={(m) => {
          mapRef.current = m;
        }}
        center={[20.5937, 78.9629]}
        zoom={5}
        maxZoom={20}
        minZoom={2}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />

        <PredictionsPaneInit />

        <SegmentationPaneInit />

        {tiffBlob && (
          <GeoTIFFLayer
            tiffBlob={tiffBlob}
            onLoadError={setTiffError}
            onMapBoundsSwne={onRasterMapBoundsSwne}
            onRasterLoadFinished={() => setTiffLoading(false)}
          />
        )}

        {segmentationOverlayUrl && segmentationOverlayBounds && (
          <SegmentationImageOverlay
            imageUrl={segmentationOverlayUrl}
            boundsLatLng={segmentationOverlayBounds}
            disableAutoFit={swipeEnabled}
          />
        )}

        {detectionData && (
          <DetectionOverlay
            detectionData={detectionData}
            imageMetadata={imageMetadata}
            detectionModelName={detectionModelName}
            detectionModelFamily={detectionModelFamily}
            disableAutoFit={swipeEnabled}
          />
        )}

        {tiffBlob && (
          <RoiLeafletDraw
            drawActive={roiDrawActive}
            geometry={roiGeometry}
            onGeometryChange={onRoiGeometryChange}
            drawControlPosition="topright"
          />
        )}

        <SwipePredictionsClip enabled={swipeEnabled} positionPct={swipePct} onTargetEl={setClipTargetEl} />
      </MapContainer>

      {tiffBlob && (
        <div className="sat-roi-toolbar">
          <button
            type="button"
            className={`sat-roi-fab ${roiDrawActive ? "sat-roi-fab-active" : ""}`}
            title={
              roiDrawActive
                ? "Exit draw mode"
                : "Draw polygon: detect only inside this area (Mask R-CNN + GeoTIFF)"
            }
            onClick={() => onRoiDrawActiveChange?.(!roiDrawActive)}
          >
            <SatHexagonGlyph />
          </button>
          {roiGeometry && (
            <button
              type="button"
              className="sat-roi-clear"
              title="Remove drawn area"
              onClick={() => {
                onRoiGeometryChange?.(null);
                onRoiDrawActiveChange?.(false);
              }}
            >
              Clear area
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default GeoTIFFMap;





