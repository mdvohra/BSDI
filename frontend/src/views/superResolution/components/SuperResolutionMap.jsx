// import React, { useEffect, useMemo, useRef, useState } from "react";
// import { MapContainer, TileLayer, useMap } from "react-leaflet";
// import L from "leaflet";
// import "leaflet/dist/leaflet.css";

// import parseGeoraster from "georaster";
// import GeoRasterLayer from "georaster-layer-for-leaflet";
// import proj4 from "proj4";

// proj4.defs("EPSG:32643", "+proj=utm +zone=43 +datum=WGS84 +units=m +no_defs");
// proj4.defs("EPSG:32644", "+proj=utm +zone=44 +datum=WGS84 +units=m +no_defs");
// proj4.defs("EPSG:32645", "+proj=utm +zone=45 +datum=WGS84 +units=m +no_defs");
// proj4.defs("EPSG:32646", "+proj=utm +zone=46 +datum=WGS84 +units=m +no_defs");
// proj4.defs(
//   "EPSG:3857",
//   "+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs"
// );

// // ---------- Fit bounds ----------
// const FitBounds = ({ bounds }) => {
//   const map = useMap();

//   useEffect(() => {
//     if (!bounds || !Array.isArray(bounds) || bounds.length !== 2) return;
//     const leafletBounds = L.latLngBounds(bounds);
//     if (!leafletBounds.isValid()) return;

//     const w = leafletBounds.getEast() - leafletBounds.getWest();
//     const h = leafletBounds.getNorth() - leafletBounds.getSouth();
//     const isSmall = w < 0.0001 || h < 0.0001;

//     if (isSmall) map.setView(leafletBounds.getCenter(), 18);
//     else map.fitBounds(leafletBounds, { maxZoom: 18, padding: [50, 50] });
//   }, [bounds, map]);

//   return null;
// };

// // ---------- Original TIFF base layer ----------
// const GeoTIFFLayer = ({ tiffBlob }) => {
//   const map = useMap();
//   const layerRef = useRef(null);

//   useEffect(() => {
//     if (!tiffBlob) return;
//     let cancelled = false;

//     const load = async () => {
//       try {
//         if (layerRef.current && map.hasLayer(layerRef.current)) {
//           map.removeLayer(layerRef.current);
//           layerRef.current = null;
//         }

//         const buf = await tiffBlob.arrayBuffer();
//         if (cancelled) return;

//         const raster = await parseGeoraster(buf);
//         let projCode = raster.projection?.toString() || null;

//         const addRaster = (resolution, fitBounds) => {
//           const layer = new GeoRasterLayer({ georaster: raster, opacity: 1, resolution });
//           layer.addTo(map);
//           layerRef.current = layer;

//           if (fitBounds?.isValid?.() && fitBounds.isValid()) {
//             map.fitBounds(fitBounds, { maxZoom: 18, padding: [50, 50] });
//           }
//         };

//         if (!projCode || projCode === "32767" || projCode === "EPSG:32767") {
//           const bounds = L.latLngBounds([raster.ymin, raster.xmin], [raster.ymax, raster.xmax]);
//           const w = Math.abs(raster.xmax - raster.xmin);
//           const h = Math.abs(raster.ymax - raster.ymin);
//           const isSmall = w < 0.01 || h < 0.01;
//           addRaster(isSmall ? 64 : 256, bounds);
//           if (isSmall && bounds.isValid()) map.setView(bounds.getCenter(), 18);
//           return;
//         }

//         const numeric = parseInt(projCode.replace("EPSG:", ""), 10);
//         const isUTM =
//           (numeric >= 32601 && numeric <= 32660) || (numeric >= 32701 && numeric <= 32760);

//         if (isUTM) {
//           const epsg = `EPSG:${numeric}`;
//           if (!proj4.defs(epsg)) {
//             const zone = numeric % 100;
//             const south = numeric >= 32700;
//             proj4.defs(
//               epsg,
//               `+proj=utm +zone=${zone} ${south ? "+south" : ""} +datum=WGS84 +units=m +no_defs`
//             );
//           }

//           const corners = [
//             [raster.xmin, raster.ymin],
//             [raster.xmin, raster.ymax],
//             [raster.xmax, raster.ymax],
//             [raster.xmax, raster.ymin],
//           ];

//           const wgsCorners = corners.map(([x, y]) => proj4(epsg, "EPSG:4326", [x, y]).reverse());
//           const lats = wgsCorners.map((c) => c[0]);
//           const lngs = wgsCorners.map((c) => c[1]);

//           const bounds = L.latLngBounds(
//             [Math.min(...lats), Math.min(...lngs)],
//             [Math.max(...lats), Math.max(...lngs)]
//           );

//           const bw = bounds.getEast() - bounds.getWest();
//           const bh = bounds.getNorth() - bounds.getSouth();
//           const isSmall = bw < 0.0001 || bh < 0.0001;

//           addRaster(isSmall ? 64 : 256, bounds);
//           if (isSmall && bounds.isValid()) map.setView(bounds.getCenter(), 18);
//           return;
//         }

//         if (projCode.includes("4326")) {
//           const bounds = L.latLngBounds([raster.ymin, raster.xmin], [raster.ymax, raster.xmax]);
//           const bw = bounds.getEast() - bounds.getWest();
//           const bh = bounds.getNorth() - bounds.getSouth();
//           const isSmall = bw < 0.0001 || bh < 0.0001;

//           addRaster(isSmall ? 64 : 256, bounds);
//           if (isSmall && bounds.isValid()) map.setView(bounds.getCenter(), 18);
//           return;
//         }

//         const layer = new GeoRasterLayer({ georaster: raster, opacity: 1, resolution: 256 });
//         layer.addTo(map);
//         layerRef.current = layer;
//         if (layer.getBounds) map.fitBounds(layer.getBounds(), { maxZoom: 18, padding: [50, 50] });
//       } catch (err) {
//         console.error("❌ TIFF load error:", err);
//       }
//     };

//     load();

//     return () => {
//       cancelled = true;
//       if (layerRef.current && map.hasLayer(layerRef.current)) {
//         map.removeLayer(layerRef.current);
//         layerRef.current = null;
//       }
//     };
//   }, [tiffBlob, map]);

//   return null;
// };

// // ---------- Draggable divider overlay (fixed) ----------
// const DraggableDivider = ({ enabled, targetEl, mapRef, swipePct, setSwipePct }) => {
//   const draggingRef = useRef(false);
//   const interactionPrevRef = useRef(null);
//   const [, forceRerender] = useState(0);

//   const safeForceRerender = () => forceRerender((v) => (v + 1) % 1000000);

//   // Keep divider position synced with overlay while the map is moving/zooming/resizing
//   useEffect(() => {
//     if (!enabled) return;
//     const map = mapRef.current;
//     if (!map) return;

//     const refresh = () => safeForceRerender();

//     map.on("move", refresh);
//     map.on("moveend", refresh);
//     map.on("zoom", refresh);
//     map.on("zoomend", refresh);
//     map.on("resize", refresh);

//     return () => {
//       map.off("move", refresh);
//       map.off("moveend", refresh);
//       map.off("zoom", refresh);
//       map.off("zoomend", refresh);
//       map.off("resize", refresh);
//     };
//   }, [enabled, mapRef]);

//   useEffect(() => {
//     if (!enabled || !targetEl) return;

//     const stop = () => {
//       draggingRef.current = false;

//       const map = mapRef.current;
//       if (map) {
//         map.dragging.enable();

//         // Restore zoom interactions that were temporarily disabled while dragging
//         const prev = interactionPrevRef.current;
//         if (prev) {
//           if (prev.scrollWheelZoom) map.scrollWheelZoom.enable();
//           if (prev.doubleClickZoom) map.doubleClickZoom.enable();
//           if (prev.touchZoom) map.touchZoom.enable();
//           if (prev.boxZoom) map.boxZoom.enable();
//           interactionPrevRef.current = null;
//         }
//       }
//     };

//     const move = (e) => {
//       if (!draggingRef.current || !targetEl) return;

//       const rect = targetEl.getBoundingClientRect();
//       const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
//       setSwipePct((x / rect.width) * 100);
//     };

//     window.addEventListener("pointerup", stop, { passive: true });
//     window.addEventListener("pointercancel", stop, { passive: true });
//     window.addEventListener("pointermove", move, { passive: true });

//     return () => {
//       window.removeEventListener("pointerup", stop);
//       window.removeEventListener("pointercancel", stop);
//       window.removeEventListener("pointermove", move);
//     };
//   }, [enabled, targetEl, mapRef, setSwipePct]);

//   if (!enabled || !targetEl) return null;

//   const targetRect = targetEl.getBoundingClientRect();

//   const map = mapRef.current;
//   const containerEl = map?.getContainer?.();
//   const containerRect = containerEl?.getBoundingClientRect?.();

//   const pct = Math.max(0, Math.min(100, swipePct));
//   const xOnTarget = (pct / 100) * targetRect.width;

//   // IMPORTANT FIX:
//   // Place divider relative to the map container, not relative to the viewport.
//   const leftPx = containerRect
//     ? (targetRect.left - containerRect.left) + xOnTarget
//     : xOnTarget;

//   return (
//     <div
//       onPointerDown={(e) => {
//         e.preventDefault();
//         e.stopPropagation();

//         draggingRef.current = true;

//         const m = mapRef.current;
//         if (m) {
//           // Save and disable interactions that commonly interfere with a drag-to-swipe UI
//           interactionPrevRef.current = {
//             scrollWheelZoom: m.scrollWheelZoom?.enabled?.() ?? true,
//             doubleClickZoom: m.doubleClickZoom?.enabled?.() ?? true,
//             touchZoom: m.touchZoom?.enabled?.() ?? true,
//             boxZoom: m.boxZoom?.enabled?.() ?? true,
//           };

//           m.dragging.disable();
//           m.scrollWheelZoom?.disable?.();
//           m.doubleClickZoom?.disable?.();
//           m.touchZoom?.disable?.();
//           m.boxZoom?.disable?.();
//         }
//       }}
//       style={{
//         position: "absolute",
//         top: 0,
//         bottom: 0,
//         left: `${leftPx}px`,
//         width: 22,
//         transform: "translateX(-11px)",
//         zIndex: 9999,
//         cursor: "col-resize",
//         pointerEvents: "auto",
//         display: "flex",
//         alignItems: "center",
//         justifyContent: "center",
//         touchAction: "none", // prevents mobile browser gestures from hijacking the drag
//       }}
//     >
//       <div style={{ width: 2, height: "100%", background: "rgba(16,185,129,0.95)" }} />
//       <div
//         style={{
//           position: "absolute",
//           width: 18,
//           height: 42,
//           borderRadius: 10,
//           background: "rgba(255,255,255,0.95)",
//           border: "1px solid rgba(0,0,0,0.15)",
//           boxShadow: "0 2px 8px rgba(0,0,0,0.20)",
//         }}
//       />
//     </div>
//   );
// };

// // ---------- SR overlay with swipe clip ----------
// const SROverlayWithSwipe = ({ overlayUrl, bounds, swipeEnabled, swipePct, onTargetEl, mapRef }) => {
//   const map = useMap();
//   const overlayRef = useRef(null);

//   useEffect(() => {
//     if (!overlayUrl || !bounds) return;

//     if (overlayRef.current) {
//       try {
//         map.removeLayer(overlayRef.current);
//       } catch {}
//       overlayRef.current = null;
//     }

//     const overlay = L.imageOverlay(overlayUrl, bounds, { opacity: 1.0 });
//     overlay.addTo(map);
//     overlayRef.current = overlay;

//     // Attempt to capture target element after it has been added to the map
//     window.setTimeout(() => {
//       const el = overlay.getElement ? overlay.getElement() : overlay._image;
//       if (el) onTargetEl?.(el);
//     }, 0);

//     return () => {
//       // clear clip target
//       onTargetEl?.(null);

//       if (overlayRef.current) {
//         try {
//           map.removeLayer(overlayRef.current);
//         } catch {}
//         overlayRef.current = null;
//       }
//     };
//   }, [overlayUrl, bounds, map, onTargetEl]);

//   useEffect(() => {
//     const applyClip = () => {
//       const overlay = overlayRef.current;
//       if (!overlay) return;

//       const el = overlay.getElement ? overlay.getElement() : overlay._image;
//       if (!el) return;

//       onTargetEl?.(el);

//       if (!swipeEnabled) {
//         el.style.clipPath = "";
//         el.style.webkitClipPath = "";
//         return;
//       }

//       // const rect = el.getBoundingClientRect();
//       const mapContainer = map.getContainer();
//       const mapRect = mapContainer.getBoundingClientRect();
//       const imgRect = el.getBoundingClientRect();
//       const pct = Math.max(0, Math.min(100, swipePct));
//       // const xPx = Math.round((pct / 100) * rect.width);
//       const visibleLeft = Math.max(imgRect.left, mapRect.left);
//       const visibleRight = Math.min(imgRect.right, mapRect.right);
//       const visibleWidth = Math.max(0, visibleRight - visibleLeft);
//       if (visibleWidth === 0) return;
//       const swipeXVisible = (pct / 100) * visibleWidth;
//       const xPx = Math.round(swipeXVisible + (visibleLeft - imgRect.left));

//       const clipValue = `inset(0px 0px 0px ${xPx}px)`;
//       el.style.clipPath = clipValue;
//       el.style.webkitClipPath = clipValue;
//     };

//     applyClip();

//     // Keep overlay clip synced during pan/zoom/resize
//     map.on("resize", applyClip);
//     map.on("zoom", applyClip);
//     map.on("zoomend", applyClip);
//     map.on("move", applyClip);
//     map.on("moveend", applyClip);

//     const t = window.setTimeout(applyClip, 50);

//     return () => {
//       window.clearTimeout(t);
//       map.off("resize", applyClip);
//       map.off("zoom", applyClip);
//       map.off("zoomend", applyClip);
//       map.off("move", applyClip);
//       map.off("moveend", applyClip);

//       const overlay = overlayRef.current;
//       const el = overlay?.getElement ? overlay.getElement() : overlay?._image;
//       if (el) {
//         el.style.clipPath = "";
//         el.style.webkitClipPath = "";
//       }
//     };
//   }, [swipeEnabled, swipePct, map, onTargetEl]);

//   // also nudge the divider to rerender on map move/zoom while swipe is enabled
//   useEffect(() => {
//     if (!swipeEnabled) return;
//     const m = mapRef?.current;
//     if (!m) return;

//     const refresh = () => onTargetEl?.(overlayRef.current?.getElement?.() || overlayRef.current?._image || null);
//     m.on("move", refresh);
//     m.on("zoom", refresh);
//     return () => {
//       m.off("move", refresh);
//       m.off("zoom", refresh);
//     };
//   }, [swipeEnabled, mapRef, onTargetEl]);

//   return null;
// };

// // ---------- Main SR Map ----------
// const SuperResolutionMap = ({ overlayUrl, imageMetadata, originalTiffBlob , onMapReady  = null }) => {
//   const bounds = imageMetadata?.bounds;
//   const hasRaw = !!originalTiffBlob;
//   const hasSR = !!overlayUrl;

//   if ((!hasRaw && !hasSR) || !bounds || !Array.isArray(bounds) || bounds.length !== 2) {
//     return (
//       <div
//         style={{
//           display: "flex",
//           alignItems: "center",
//           justifyContent: "center",
//           height: "100%",
//           color: "#6B7280",
//         }}
//       >
//         No super-resolution data available to display.
//       </div>
//     );
//   }

//   const [swipeEnabled, setSwipeEnabled] = useState(false);
//   const [swipePct, setSwipePct] = useState(50);

//   const mapRef = useRef(null);
//   const [clipTargetEl, setClipTargetEl] = useState(null);

//   // When swipe is turned off, keep state clean (optional but helps avoid stale refs)
//   useEffect(() => {
//     if (!swipeEnabled) setClipTargetEl(null);
//   }, [swipeEnabled]);

//   return (
//     <div style={{ position: "relative", height: "100%", width: "100%" }}>
//       {/* Toggle button */}
//       <div style={{ position: "absolute", top: 10, right: 10, zIndex: 1200 }}>
//         <button
//           type="button"
//           onClick={() => setSwipeEnabled((v) => !v)}
//           style={{
//             background: swipeEnabled ? "#ef4444" : "#10b981",
//             color: "white",
//             padding: "10px 12px",
//             borderRadius: "8px",
//             border: "none",
//             cursor: "pointer",
//             fontWeight: 600,
//           }}
//         >
//           {swipeEnabled ? "Exit Swipe" : "Swipe Compare"}
//         </button>
//       </div>

//       {/* Draggable divider */}
//       <DraggableDivider
//         enabled={swipeEnabled}
//         targetEl={clipTargetEl}
//         mapRef={mapRef}
//         swipePct={swipePct}
//         setSwipePct={setSwipePct}
//       />

//       <MapContainer
//         whenCreated={(m) => {
//           mapRef.current = m;
//           onMapReady?.(m);
//         }}
//         center={[20.5937, 78.9629]}
//         zoom={5}
//         maxZoom={20}
//         minZoom={2}
//         style={{ height: "100%", width: "100%" }}
//       >
//         <TileLayer
//           url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
//           maxZoom={19}
//           attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
//         />

//         {originalTiffBlob && <GeoTIFFLayer tiffBlob={originalTiffBlob} />}

//         <SROverlayWithSwipe
//           overlayUrl={overlayUrl}
//           bounds={bounds}
//           swipeEnabled={swipeEnabled}
//           swipePct={swipePct}
//           onTargetEl={setClipTargetEl}
//           mapRef={mapRef}
//         />

//         <FitBounds bounds={bounds} />
//       </MapContainer>
//     </div>
//   );
// };

// export default SuperResolutionMap;

////////////////////// NEW LOGIC////////////////////////////////
import React, { useEffect, useMemo, useRef, useState } from "react";
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

// ---------- Fit bounds ----------
const FitBounds = ({ bounds }) => {
  const map = useMap();

  useEffect(() => {
    if (!bounds || !Array.isArray(bounds) || bounds.length !== 2) return;
    const leafletBounds = L.latLngBounds(bounds);
    if (!leafletBounds.isValid()) return;

    const w = leafletBounds.getEast() - leafletBounds.getWest();
    const h = leafletBounds.getNorth() - leafletBounds.getSouth();
    const isSmall = w < 0.0001 || h < 0.0001;

    if (isSmall) map.setView(leafletBounds.getCenter(), 18);
    else map.fitBounds(leafletBounds, { maxZoom: 18, padding: [50, 50] });
  }, [bounds, map]);

  return null;
};

// ---------- Original TIFF base layer ----------
const GeoTIFFLayer = ({ tiffBlob }) => {
  const map = useMap();
  const layerRef = useRef(null);

  useEffect(() => {
    if (!tiffBlob) return;
    let cancelled = false;

    const load = async () => {
      try {
        if (layerRef.current && map.hasLayer(layerRef.current)) {
          map.removeLayer(layerRef.current);
          layerRef.current = null;
        }

        const buf = await tiffBlob.arrayBuffer();
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

// ---------- Draggable divider overlay (fixed) ----------
const DraggableDivider = ({ enabled, targetEl, mapRef, swipePct, setSwipePct }) => {
  const draggingRef = useRef(false);
  const interactionPrevRef = useRef(null);
  const [, forceRerender] = useState(0);

  const safeForceRerender = () => forceRerender((v) => (v + 1) % 1000000);

  // Keep divider position synced with overlay while the map is moving/zooming/resizing
  useEffect(() => {
    if (!enabled) return;
    const map = mapRef.current;
    if (!map) return;

    const refresh = () => safeForceRerender();

    map.on("move", refresh);
    map.on("moveend", refresh);
    map.on("zoom", refresh);
    map.on("zoomend", refresh);
    map.on("resize", refresh);

    return () => {
      map.off("move", refresh);
      map.off("moveend", refresh);
      map.off("zoom", refresh);
      map.off("zoomend", refresh);
      map.off("resize", refresh);
    };
  }, [enabled, mapRef]);

  useEffect(() => {
    if (!enabled || !targetEl) return;

    const stop = () => {
      draggingRef.current = false;

      const map = mapRef.current;
      if (map) {
        map.dragging.enable();

        // Restore zoom interactions that were temporarily disabled while dragging
        const prev = interactionPrevRef.current;
        if (prev) {
          if (prev.scrollWheelZoom) map.scrollWheelZoom.enable();
          if (prev.doubleClickZoom) map.doubleClickZoom.enable();
          if (prev.touchZoom) map.touchZoom.enable();
          if (prev.boxZoom) map.boxZoom.enable();
          interactionPrevRef.current = null;
        }
      }
    };

    const move = (e) => {
      if (!draggingRef.current || !targetEl) return;

      const rect = targetEl.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      setSwipePct((x / rect.width) * 100);
    };

    window.addEventListener("pointerup", stop, { passive: true });
    window.addEventListener("pointercancel", stop, { passive: true });
    window.addEventListener("pointermove", move, { passive: true });

    return () => {
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("pointermove", move);
    };
  }, [enabled, targetEl, mapRef, setSwipePct]);

  if (!enabled || !targetEl) return null;

  const targetRect = targetEl.getBoundingClientRect();

  const map = mapRef.current;
  const containerEl = map?.getContainer?.();
  const containerRect = containerEl?.getBoundingClientRect?.();

  const pct = Math.max(0, Math.min(100, swipePct));
  const xOnTarget = (pct / 100) * targetRect.width;

  // IMPORTANT FIX:
  // Place divider relative to the map container, not relative to the viewport.
  const leftPx = containerRect
    ? (targetRect.left - containerRect.left) + xOnTarget
    : xOnTarget;

  return (
    <div
      onPointerDown={(e) => {
        e.preventDefault();
        e.stopPropagation();

        draggingRef.current = true;

        const m = mapRef.current;
        if (m) {
          // Save and disable interactions that commonly interfere with a drag-to-swipe UI
          interactionPrevRef.current = {
            scrollWheelZoom: m.scrollWheelZoom?.enabled?.() ?? true,
            doubleClickZoom: m.doubleClickZoom?.enabled?.() ?? true,
            touchZoom: m.touchZoom?.enabled?.() ?? true,
            boxZoom: m.boxZoom?.enabled?.() ?? true,
          };

          m.dragging.disable();
          m.scrollWheelZoom?.disable?.();
          m.doubleClickZoom?.disable?.();
          m.touchZoom?.disable?.();
          m.boxZoom?.disable?.();
        }
      }}
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        left: `${leftPx}px`,
        width: 22,
        transform: "translateX(-11px)",
        zIndex: 9999,
        cursor: "col-resize",
        pointerEvents: "auto",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        touchAction: "none", // prevents mobile browser gestures from hijacking the drag
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

// ---------- SR overlay with swipe clip ----------
const SROverlayWithSwipe = ({ overlayUrl, bounds, swipeEnabled, swipePct, onTargetEl, mapRef }) => {
  const map = useMap();
  const overlayRef = useRef(null);

  useEffect(() => {
    if (!overlayUrl || !bounds) return;

    if (overlayRef.current) {
      try {
        map.removeLayer(overlayRef.current);
      } catch {}
      overlayRef.current = null;
    }

    const overlay = L.imageOverlay(overlayUrl, bounds, { opacity: 1.0 });
    overlay.addTo(map);
    overlayRef.current = overlay;

    // Attempt to capture target element after it has been added to the map
    window.setTimeout(() => {
      const el = overlay.getElement ? overlay.getElement() : overlay._image;
      if (el) onTargetEl?.(el);
    }, 0);

    return () => {
      // clear clip target
      onTargetEl?.(null);

      if (overlayRef.current) {
        try {
          map.removeLayer(overlayRef.current);
        } catch {}
        overlayRef.current = null;
      }
    };
  }, [overlayUrl, bounds, map, onTargetEl]);

  useEffect(() => {
    const applyClip = () => {
      const overlay = overlayRef.current;
      if (!overlay) return;

      const el = overlay.getElement ? overlay.getElement() : overlay._image;
      if (!el) return;

      onTargetEl?.(el);

      if (!swipeEnabled) {
        el.style.clipPath = "";
        el.style.webkitClipPath = "";
        return;
      }

      // const rect = el.getBoundingClientRect();
      const mapContainer = map.getContainer();
      const mapRect = mapContainer.getBoundingClientRect();
      const imgRect = el.getBoundingClientRect();
      const pct = Math.max(0, Math.min(100, swipePct));
      // const xPx = Math.round((pct / 100) * rect.width);
      const visibleLeft = Math.max(imgRect.left, mapRect.left);
      const visibleRight = Math.min(imgRect.right, mapRect.right);
      const visibleWidth = Math.max(0, visibleRight - visibleLeft);
      if (visibleWidth === 0) return;
      const swipeXVisible = (pct / 100) * visibleWidth;
      const xPx = Math.round(swipeXVisible + (visibleLeft - imgRect.left));

      const clipValue = `inset(0px 0px 0px ${xPx}px)`;
      el.style.clipPath = clipValue;
      el.style.webkitClipPath = clipValue;
    };

    applyClip();

    // Keep overlay clip synced during pan/zoom/resize
    map.on("resize", applyClip);
    map.on("zoom", applyClip);
    map.on("zoomend", applyClip);
    map.on("move", applyClip);
    map.on("moveend", applyClip);

    const t = window.setTimeout(applyClip, 50);

    return () => {
      window.clearTimeout(t);
      map.off("resize", applyClip);
      map.off("zoom", applyClip);
      map.off("zoomend", applyClip);
      map.off("move", applyClip);
      map.off("moveend", applyClip);

      const overlay = overlayRef.current;
      const el = overlay?.getElement ? overlay.getElement() : overlay?._image;
      if (el) {
        el.style.clipPath = "";
        el.style.webkitClipPath = "";
      }
    };
  }, [swipeEnabled, swipePct, map, onTargetEl]);

  // also nudge the divider to rerender on map move/zoom while swipe is enabled
  useEffect(() => {
    if (!swipeEnabled) return;
    const m = mapRef?.current;
    if (!m) return;

    const refresh = () => onTargetEl?.(overlayRef.current?.getElement?.() || overlayRef.current?._image || null);
    m.on("move", refresh);
    m.on("zoom", refresh);
    return () => {
      m.off("move", refresh);
      m.off("zoom", refresh);
    };
  }, [swipeEnabled, mapRef, onTargetEl]);

  return null;
};

// ---------- Main SR Map ----------
const SuperResolutionMap = ({ overlayUrl, imageMetadata, originalTiffBlob , onMapReady  = null }) => {
  const bounds = imageMetadata?.bounds;
  const hasRaw = !!originalTiffBlob;
  const hasSR = !!overlayUrl;

  if ((!hasRaw && !hasSR) || !bounds || !Array.isArray(bounds) || bounds.length !== 2) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          color: "#6B7280",
        }}
      >
        No super-resolution data available to display.
      </div>
    );
  }

  const [swipeEnabled, setSwipeEnabled] = useState(false);
  const [swipePct, setSwipePct] = useState(50);

  const mapRef = useRef(null);
  const [clipTargetEl, setClipTargetEl] = useState(null);

  // When swipe is turned off, keep state clean (optional but helps avoid stale refs)
  useEffect(() => {
    if (!swipeEnabled) setClipTargetEl(null);
  }, [swipeEnabled]);

  return (
    <div style={{ position: "relative", height: "100%", width: "100%" }}>
      {/* Toggle button */}
      <div style={{ position: "absolute", top: 10, right: 10, zIndex: 1200 }}>
        <button
          type="button"
          onClick={() => setSwipeEnabled((v) => !v)}
          style={{
            background: swipeEnabled ? "#ef4444" : "#10b981",
            color: "white",
            padding: "10px 12px",
            borderRadius: "8px",
            border: "none",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          {swipeEnabled ? "Exit Swipe" : "Swipe Compare"}
        </button>
      </div>

      {/* Draggable divider */}
      <DraggableDivider
        enabled={swipeEnabled}
        targetEl={clipTargetEl}
        mapRef={mapRef}
        swipePct={swipePct}
        setSwipePct={setSwipePct}
      />

      <MapContainer
        // whenCreated={(m) => {
        //   mapRef.current = m;
        //   onMapReady?.(m);
        // }}
        center={[20.5937, 78.9629]}
        zoom={5}
        maxZoom={20}
        minZoom={2}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />

        {originalTiffBlob && <GeoTIFFLayer tiffBlob={originalTiffBlob} />}

        <SROverlayWithSwipe
          overlayUrl={overlayUrl}
          bounds={bounds}
          swipeEnabled={swipeEnabled}
          swipePct={swipePct}
          onTargetEl={setClipTargetEl}
          mapRef={mapRef}
        />

        <FitBounds bounds={bounds} />
      </MapContainer>
    </div>
  );
};

export default SuperResolutionMap;