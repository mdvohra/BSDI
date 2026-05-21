import React, { useRef, useEffect, useState, useCallback } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import { MapContainer, TileLayer } from "react-leaflet";
import GeoTIFFMap from "./GeoTIFFMap";
import SuperResolutionMap from "./SuperResolutionMap";

/** Browsers often leave file.type empty for .tif; GeoTIFF must use the map path, not <img>. */
function isTiffFile(file) {
  if (!file) return false;
  const n = file.name || "";
  if (/\.(tif|tiff)$/i.test(n)) return true;
  const t = (file.type || "").toLowerCase();
  return t === "image/tiff" || t === "image/x-tiff";
}

const ImageViewer = ({
  imageData,
  fileType,
  file,
  detectionData,
  imageMetadata,
  overlayImage,
  detectionModelName,
  detectionModelFamily,
  segmentationOverlayUrl,
  segmentationOverlayBounds,
  oilSpillLegendEntries,
  roiDrawActive,
  onRoiDrawActiveChange,
  roiGeometry,
  onRoiGeometryChange,
  onRasterMapBoundsSwne,
}) => {
  const canvasRef = useRef(null);
  const [leftReady, setLeftReady] = useState(false);
  const [rightReady, setRightReady] = useState(false);
  const [compositeImage, setCompositeImage] = useState(null);

  const leftMapRef = useRef(null);
  const rightMapRef = useRef(null);
  const isSyncingRef = useRef(false);

  const isSuperResolution = imageMetadata?.scale_factor !== undefined;

  const syncMaps = useCallback((sourceRef, targetRef) => {
    if (isSyncingRef.current) return;
    const sourceMap = sourceRef.current;
    const targetMap = targetRef.current;
    if (!sourceMap || !targetMap || sourceMap === targetMap) return;

    isSyncingRef.current = true;
    try {
      targetMap.setView(sourceMap.getCenter(), sourceMap.getZoom(), { animate: false, duration: 0 });
    } catch (error) {
      console.warn("Map sync error:", error);
    } finally {
      setTimeout(() => { isSyncingRef.current = false; }, 100);
    }
  }, []);

  useEffect(() => {
    if (!imageData || !overlayImage || isTiffFile(file)) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const baseImg = new Image();
    const overlayImg = new Image();
    baseImg.crossOrigin = "anonymous";
    overlayImg.crossOrigin = "anonymous";

    let baseLoaded = false;
    let overlayLoaded = false;

    const drawComposite = () => {
      if (!baseLoaded || !overlayLoaded) return;
      canvas.width = baseImg.width;
      canvas.height = baseImg.height;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(baseImg, 0, 0);
      ctx.globalAlpha = 0.7;
      ctx.drawImage(overlayImg, 0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = 1.0;
      canvas.toBlob((blob) => {
        if (blob) setCompositeImage(URL.createObjectURL(blob));
      }, "image/png");
    };

    baseImg.onload = () => { baseLoaded = true; drawComposite(); };
    overlayImg.onload = () => { overlayLoaded = true; drawComposite(); };
    baseImg.src = imageData;
    overlayImg.src = overlayImage;

    return () => {
      if (compositeImage) URL.revokeObjectURL(compositeImage);
    };
  }, [imageData, overlayImage, file]);

  useEffect(() => {
    if (!leftReady || !leftMapRef.current) return;
    const map = leftMapRef.current;
    let syncTimeout;
    const handleLeftMove = () => {
      clearTimeout(syncTimeout);
      syncTimeout = setTimeout(() => syncMaps(leftMapRef, rightMapRef), 50);
    };
    map.on('moveend', handleLeftMove);
    map.on('zoomend', handleLeftMove);
    return () => {
      map.off('moveend', handleLeftMove);
      map.off('zoomend', handleLeftMove);
      if (syncTimeout) clearTimeout(syncTimeout);
    };
  }, [leftReady, syncMaps]);

  useEffect(() => {
    if (!rightReady || !rightMapRef.current) return;
    const map = rightMapRef.current;
    let syncTimeout;
    const handleRightMove = () => {
      clearTimeout(syncTimeout);
      syncTimeout = setTimeout(() => syncMaps(rightMapRef, leftMapRef), 50);
    };
    map.on('moveend', handleRightMove);
    map.on('zoomend', handleRightMove);
    return () => {
      map.off('moveend', handleRightMove);
      map.off('zoomend', handleRightMove);
      if (syncTimeout) clearTimeout(syncTimeout);
    };
  }, [rightReady, syncMaps]);

  useEffect(() => {
    if (leftReady && rightReady && leftMapRef.current && rightMapRef.current) {
      syncMaps(leftMapRef, rightMapRef);
    }
  }, [leftReady, rightReady, syncMaps]);

  /* Default map when nothing is loaded */
  if (!file && !imageData && !detectionData) {
    return (
      <div style={{ width: "100%", height: "100%" }}>
        <MapContainer
          center={[20.5937, 78.9629]}
          zoom={5}
          maxZoom={20}
          minZoom={2}
          style={{ height: "100%", width: "100%" }}
          zoomControl={true}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
            attribution="&copy; OpenStreetMap"
          />
        </MapContainer>
      </div>
    );
  }

  const displayImage = compositeImage || overlayImage || imageData;

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <canvas ref={canvasRef} style={{ display: "none" }} />

      {/* TIFF detection mode (also used for loading saved prediction polygons without the original TIFF) */}
      {((file && isTiffFile(file) && !isSuperResolution) ||
        (!file && !!detectionData && !isSuperResolution)) ? (
        <GeoTIFFMap
          tiffBlob={file && isTiffFile(file) ? file : null}
          detectionData={detectionData}
          imageMetadata={imageMetadata}
          detectionModelName={detectionModelName}
          detectionModelFamily={detectionModelFamily}
          segmentationOverlayUrl={segmentationOverlayUrl}
          segmentationOverlayBounds={segmentationOverlayBounds}
          oilSpillLegendEntries={oilSpillLegendEntries}
          roiDrawActive={roiDrawActive}
          onRoiDrawActiveChange={onRoiDrawActiveChange}
          roiGeometry={roiGeometry}
          onRoiGeometryChange={onRoiGeometryChange}
          onRasterMapBoundsSwne={onRasterMapBoundsSwne}
        />
      ) : isSuperResolution && overlayImage && imageMetadata?.bounds ? (
        <div style={{ width: "100%", height: "100%", display: "flex", gap: "4px" }}>
          <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
            <div style={{
              position: "absolute", top: 10, left: 10, zIndex: 1000,
              background: "rgba(15,23,42,0.8)", backdropFilter: "blur(8px)",
              color: "#f1f5f9", padding: "5px 12px", borderRadius: "8px",
              fontSize: "11px", fontWeight: 600, letterSpacing: "0.5px"
            }}>
              ORIGINAL
            </div>
            <SuperResolutionMap
              overlayUrl={null}
              originalTiffBlob={file && isTiffFile(file) ? file : null}
              imageMetadata={imageMetadata}
              onMapReady={(map) => { leftMapRef.current = map; setLeftReady(true); }}
            />
          </div>
          <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
            <div style={{
              position: "absolute", top: 10, left: 10, zIndex: 1000,
              background: "rgba(15,23,42,0.8)", backdropFilter: "blur(8px)",
              color: "var(--geoai-od-accent-text-strong)", padding: "5px 12px", borderRadius: "8px",
              fontSize: "11px", fontWeight: 600, letterSpacing: "0.5px"
            }}>
              SUPER RESOLUTION
            </div>
            <SuperResolutionMap
              overlayUrl={overlayImage}
              originalTiffBlob={null}
              imageMetadata={imageMetadata}
              onMapReady={(map) => { rightMapRef.current = map; setRightReady(true); }}
            />
          </div>
        </div>
      ) : (
        <TransformWrapper
          initialScale={1}
          initialPositionX={0}
          initialPositionY={0}
          options={{
            limitToBounds: true, minScale: 0.5, maxScale: 3, centerContent: true,
            wheel: { step: 0.2 }, doubleClick: { step: 1 },
            panning: { velocityDisabled: true },
          }}
        >
          {({ zoomIn, zoomOut, resetTransform }) => (
            <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column" }}>
              <div style={{
                position: "absolute", top: 16, right: 16, zIndex: 1000,
                display: "flex", flexDirection: "column", gap: "4px"
              }}>
                {[
                  { fn: zoomIn, icon: "M12 5v14M5 12h14" },
                  { fn: zoomOut, icon: "M5 12h14" },
                  { fn: resetTransform, icon: "M1 4v6h6M23 20v-6h-6M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" },
                ].map((item, i) => (
                  <button
                    key={i}
                    onClick={() => item.fn()}
                    style={{
                      width: 36, height: 36, borderRadius: 8,
                      background: "rgba(15,23,42,0.8)", backdropFilter: "blur(8px)",
                      border: "1px solid rgba(255,255,255,0.08)", color: "#e2e8f0",
                      cursor: "pointer", display: "flex", alignItems: "center",
                      justifyContent: "center", transition: "all 0.2s",
                    }}
                    onMouseOver={(e) => { e.currentTarget.style.background = "rgba(15,23,42,0.95)"; }}
                    onMouseOut={(e) => { e.currentTarget.style.background = "rgba(15,23,42,0.8)"; }}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d={item.icon} />
                    </svg>
                  </button>
                ))}
              </div>
              <div style={{ flex: 1, display: "flex", justifyContent: "center", alignItems: "center" }}>
                <TransformComponent wrapperStyle={{ width: "100%", height: "100%" }}>
                  <img style={{ maxHeight: "100%", maxWidth: "100%", objectFit: "contain" }} src={displayImage} alt="Satellite" loading="lazy" />
                </TransformComponent>
              </div>
            </div>
          )}
        </TransformWrapper>
      )}
    </div>
  );
};

export default ImageViewer;
