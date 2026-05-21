import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import GeoTiffLoadingOverlay from "../../../components/GeoTiffLoadingOverlay";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import parseGeoraster from "georaster";
import GeoRasterLayer from "georaster-layer-for-leaflet";
import proj4 from "proj4";

proj4.defs("EPSG:32643", "+proj=utm +zone=43 +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32644", "+proj=utm +zone=44 +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32645", "+proj=utm +zone=45 +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32646", "+proj=utm +zone=46 +datum=WGS84 +units=m +no_defs");
proj4.defs(
  "EPSG:3857",
  "+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs"
);

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
      <div style={{ width: 2, height: "100%", background: "rgba(16,185,129,0.95)" }} />
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

// ---------- Detection overlay ----------
const DetectionOverlay = ({ detectionData, imageMetadata, disableAutoFit }) => {
  const map = useMap();
  const layerRef = useRef(null);

  useEffect(() => {
    if (!detectionData) return;

    if (!map._predictionsRenderer) {
      map._predictionsRenderer = L.canvas({ pane: "predictions-pane" });
    }

    if (layerRef.current && map.hasLayer(layerRef.current)) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    let abortController = null;

    const style = {
      color: "#ff0000",
      weight: 2,
      opacity: 0.9,
      fillColor: "#ff0000",
      fillOpacity: 0.25,
    };

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

    const addGeoJson = (geojson) => {
      const geoJsonLayer = L.geoJSON(geojson, {
        pane: "predictions-pane",
        renderer: map._predictionsRenderer,
        style: () => style,
        onEachFeature,
      }).addTo(map);

      layerRef.current = geoJsonLayer;

      if (!disableAutoFit) {
        if (imageMetadata?.bounds && isUsableWgs84Bounds(imageMetadata.bounds)) {
          const b = L.latLngBounds(imageMetadata.bounds);
          if (b.isValid()) map.fitBounds(b, { padding: [30, 30], maxZoom: 18 });
        } else if (geoJsonLayer.getBounds && geoJsonLayer.getBounds().isValid()) {
          map.fitBounds(geoJsonLayer.getBounds(), { padding: [30, 30], maxZoom: 18 });
        }
      }
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
        if (layerRef.current && map.hasLayer(layerRef.current)) {
          map.removeLayer(layerRef.current);
          layerRef.current = null;
        }
      };
    }

    const geoJsonData = Array.isArray(detectionData)
      ? { type: "FeatureCollection", features: detectionData }
      : detectionData;

    addGeoJson(geoJsonData);

    return () => {
      if (layerRef.current && map.hasLayer(layerRef.current)) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [detectionData, imageMetadata, disableAutoFit, map]);

  return null;
};

// ---------- GeoTIFF raster layer ----------
const GeoTIFFLayer = ({ tiffBlob, onRasterLoadFinished }) => {
  const map = useMap();
  const layerRef = useRef(null);
  const onDoneRef = useRef(onRasterLoadFinished);
  onDoneRef.current = onRasterLoadFinished;

  useEffect(() => {
    if (!tiffBlob) return;
    let cancelled = false;

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
        if (layer.getBounds) map.fitBounds(layer.getBounds(), { maxZoom: 18, padding: [50, 50] });
      } catch (err) {
        console.error("❌ TIFF load error:", err);
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
  }, [tiffBlob, map]);

  return null;
};

// ---------- Main ----------
const GeoTIFFMap = ({ tiffBlob, detectionData, imageMetadata }) => {
  const [swipeEnabled, setSwipeEnabled] = useState(false);
  const [swipePct, setSwipePct] = useState(50);
  const [tiffLoading, setTiffLoading] = useState(false);

  const mapRef = useRef(null);
  const [clipTargetEl, setClipTargetEl] = useState(null);

  useLayoutEffect(() => {
    setTiffLoading(Boolean(tiffBlob));
  }, [tiffBlob]);

  return (
    <div style={{ position: "relative", height: "100%", width: "100%" }}>
      <GeoTiffLoadingOverlay visible={tiffLoading && Boolean(tiffBlob)} />
      {/* Toggle button */}
      <div style={{ position: "absolute", top: 10, right: 10, zIndex: 1200 }}>
      </div>

      {/* Optional info panel (unchanged behavior) */}
      {imageMetadata && (
        <div
          style={{
            position: "absolute",
            top: "10px",
            left: "10px",
            background: "rgba(255, 255, 255, 0.95)",
            padding: "12px 16px",
            borderRadius: "8px",
            fontSize: "14px",
            zIndex: 1100,
            boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
            maxWidth: "320px",
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          }}
        >
          <div style={{ fontWeight: "bold", color: "#3b82f6", marginBottom: "8px", fontSize: "15px" }}>
            🔍 Detection Results
          </div>
          <div style={{ fontSize: "12px", color: "#666", lineHeight: "1.6" }}>
            <div style={{ marginBottom: "4px" }}>
              <strong>Count:</strong> {imageMetadata.count || 0} detected
            </div>
          </div>
          <div style={{ fontSize: "11px", color: "#999", marginTop: "8px", paddingTop: "6px", borderTop: "1px solid #e5e7eb" }}>
            <strong>CRS:</strong> {imageMetadata.crs || "N/A"}
          </div>
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

        {tiffBlob && (
          <GeoTIFFLayer tiffBlob={tiffBlob} onRasterLoadFinished={() => setTiffLoading(false)} />
        )}

        {detectionData && (
          <DetectionOverlay
            detectionData={detectionData}
            imageMetadata={imageMetadata}
            disableAutoFit={swipeEnabled}
          />
        )}

        <SwipePredictionsClip enabled={swipeEnabled} positionPct={swipePct} onTargetEl={setClipTargetEl} />
      </MapContainer>
    </div>
  );
};

export default GeoTIFFMap;





