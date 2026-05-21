import React, { useCallback, useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import parseGeoraster from "georaster";
import "leaflet/dist/leaflet.css";

import { GeoTIFFLayer, OverlayImageLayer } from "./GeoTIFFMap";

function MapInstanceReady({ mapRef, onReady }) {
  const map = useMap();
  useEffect(() => {
    mapRef.current = map;
    onReady?.();
    return () => {
      mapRef.current = null;
    };
  }, [map, mapRef, onReady]);
  return null;
}

/**
 * Side-by-side Leaflet maps (like object detection / super-resolution): same GeoTIFF parsed once,
 * native map zoom shows full raster detail. Left = satellite only, right = satellite + classification overlay.
 */
const LULCTiffCompareMaps = ({ tiffBlob, overlayImageUrl, bounds }) => {
  const [georaster, setGeoraster] = useState(null);
  const leftMapRef = useRef(null);
  const rightMapRef = useRef(null);
  const [leftReady, setLeftReady] = useState(false);
  const [rightReady, setRightReady] = useState(false);
  const isSyncingRef = useRef(false);

  const markLeftReady = useCallback(() => setLeftReady(true), []);
  const markRightReady = useCallback(() => setRightReady(true), []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tiffBlob) {
        setGeoraster(null);
        return;
      }
      try {
        const buf = await tiffBlob.arrayBuffer();
        if (cancelled) return;
        setGeoraster(await parseGeoraster(buf));
      } catch (e) {
        console.error("LULC compare: GeoTIFF parse failed", e);
        if (!cancelled) setGeoraster(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tiffBlob]);

  const syncMaps = useCallback((sourceRef, targetRef) => {
    if (isSyncingRef.current) return;
    const source = sourceRef.current;
    const target = targetRef.current;
    if (!source || !target || source === target) return;
    isSyncingRef.current = true;
    try {
      target.setView(source.getCenter(), source.getZoom(), { animate: false, duration: 0 });
    } catch (e) {
      console.warn("Map sync:", e);
    } finally {
      setTimeout(() => {
        isSyncingRef.current = false;
      }, 50);
    }
  }, []);

  useEffect(() => {
    if (!leftReady || !leftMapRef.current) return;
    const map = leftMapRef.current;
    let t;
    const onMove = () => {
      clearTimeout(t);
      t = setTimeout(() => syncMaps(leftMapRef, rightMapRef), 40);
    };
    map.on("moveend", onMove);
    map.on("zoomend", onMove);
    return () => {
      map.off("moveend", onMove);
      map.off("zoomend", onMove);
      clearTimeout(t);
    };
  }, [leftReady, syncMaps]);

  useEffect(() => {
    if (!rightReady || !rightMapRef.current) return;
    const map = rightMapRef.current;
    let t;
    const onMove = () => {
      clearTimeout(t);
      t = setTimeout(() => syncMaps(rightMapRef, leftMapRef), 40);
    };
    map.on("moveend", onMove);
    map.on("zoomend", onMove);
    return () => {
      map.off("moveend", onMove);
      map.off("zoomend", onMove);
      clearTimeout(t);
    };
  }, [rightReady, syncMaps]);

  useEffect(() => {
    if (leftReady && rightReady && leftMapRef.current && rightMapRef.current) {
      syncMaps(leftMapRef, rightMapRef);
    }
  }, [leftReady, rightReady, georaster, syncMaps]);

  const mapStyle = { height: "100%", width: "100%" };
  const labelStyle = {
    position: "absolute",
    top: 10,
    left: 10,
    zIndex: 1000,
    background: "rgba(15,23,42,0.85)",
    color: "#f1f5f9",
    padding: "6px 12px",
    borderRadius: "8px",
    fontSize: "11px",
    fontWeight: 600,
    letterSpacing: "0.4px",
    pointerEvents: "none",
  };

  return (
    <div style={{ position: "relative", height: "100%", width: "100%" }}>
      <div
        style={{
          position: "absolute",
          bottom: 12,
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 1200,
          background: "rgba(15,23,42,0.9)",
          color: "#e2e8f0",
          padding: "8px 14px",
          borderRadius: "10px",
          fontSize: "12px",
          pointerEvents: "none",
          textAlign: "center",
          maxWidth: "90%",
        }}
      >
        Scroll or use +/- to zoom in — same as object detection maps. Pans stay in sync on both panels.
      </div>

      <div style={{ display: "flex", gap: 4, height: "100%", width: "100%" }}>
        <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
          <div style={{ ...labelStyle, left: 10 }}>ORIGINAL (GeoTIFF)</div>
          <MapContainer
            center={[20.5937, 78.9629]}
            zoom={5}
            maxZoom={22}
            minZoom={2}
            style={mapStyle}
            zoomControl
          >
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />
            <MapInstanceReady mapRef={leftMapRef} onReady={markLeftReady} />
            {georaster && <GeoTIFFLayer georaster={georaster} autoFitBounds />}
          </MapContainer>
        </div>

        <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
          <div style={{ ...labelStyle, background: "rgba(16,185,129,0.9)", color: "#fff" }}>
            CLASSIFIED + SATELLITE
          </div>
          <MapContainer
            center={[20.5937, 78.9629]}
            zoom={5}
            maxZoom={22}
            minZoom={2}
            style={mapStyle}
            zoomControl
          >
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />
            <MapInstanceReady mapRef={rightMapRef} onReady={markRightReady} />
            {georaster && <GeoTIFFLayer georaster={georaster} autoFitBounds={false} />}
            {overlayImageUrl && bounds && (
              <OverlayImageLayer
                bounds={bounds}
                imageUrl={overlayImageUrl}
                opacity={0.78}
                autoFitBounds={false}
              />
            )}
          </MapContainer>
        </div>
      </div>
    </div>
  );
};

export default LULCTiffCompareMaps;
