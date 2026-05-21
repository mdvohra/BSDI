import React, { useMemo } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import LULCGeoTIFFMap from "./GeoTIFFMap";
import { LULC_BASE_URL } from "../services/api";

const ImageViewer = ({
  imageData,
  file,
  classificationData,
  streamingOverlayUrl,
  streamingBounds,
  isClassificationStreaming,
  roiDrawActive,
  onRoiDrawActiveChange,
  roiGeometry,
  onRoiGeometryChange,
  onRasterMapBoundsSwne,
}) => {
  const isTiff = file && (file.type === "image/tiff" || file.name?.toLowerCase().endsWith('.tif') || file.name?.toLowerCase().endsWith('.tiff'));
  const predictionOverlayUrl = classificationData?.prediction_image_b64
    ? `data:image/png;base64,${classificationData.prediction_image_b64}`
    : null;
  const compositeOverlayUrl = classificationData?.image_b64
    ? `data:image/png;base64,${classificationData.image_b64}`
    : null;
  const finalOverlayUrl = predictionOverlayUrl || compositeOverlayUrl;
  const overlayImageUrl =
    isClassificationStreaming && streamingOverlayUrl ? streamingOverlayUrl : finalOverlayUrl;
  const overlayOpacity =
    isClassificationStreaming && streamingOverlayUrl ? 0.72 : 1;
  const mapBounds =
    isClassificationStreaming &&
    Array.isArray(streamingBounds) &&
    streamingBounds.length === 4
      ? streamingBounds
      : classificationData?.bounds;

  const buildingDetectionUrl = useMemo(() => {
    const u = classificationData?.building_detection?.geojson_url;
    if (!u) return null;
    return u.startsWith("http") ? u : `${LULC_BASE_URL}${u}`;
  }, [classificationData?.building_detection?.geojson_url]);

  if (isTiff) {
    return (
      <div style={{ width: "100%", height: "100%", minHeight: 0 }}>
        <LULCGeoTIFFMap
          tiffBlob={file}
          overlayImageUrl={overlayImageUrl}
          bounds={mapBounds}
          overlayOpacity={overlayOpacity}
          overlayAutoFitBounds={!isClassificationStreaming}
          roiToolsEnabled
          roiDrawActive={roiDrawActive}
          onRoiDrawActiveChange={onRoiDrawActiveChange}
          roiGeometry={roiGeometry}
          onRoiGeometryChange={onRoiGeometryChange}
          onRasterMapBoundsSwne={onRasterMapBoundsSwne}
          buildingDetectionUrl={buildingDetectionUrl}
        />
      </div>
    );
  }

  const staticOverlayUrl = predictionOverlayUrl || compositeOverlayUrl;
  const displayImage =
    (isClassificationStreaming && streamingOverlayUrl
      ? streamingOverlayUrl
      : staticOverlayUrl) || imageData;

  if (!displayImage) {
    return (
      <div className="lulc-map-placeholder">
        Select a file in the panel, then run classification. The map or preview will appear here.
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: "100%", minHeight: 0, position: "relative" }}>
      <TransformWrapper
        initialScale={1}
        initialPositionX={0}
        initialPositionY={0}
        options={{
          limitToBounds: true,
          minScale: 0.5,
          maxScale: 3,
          centerContent: true,
          wheel: { step: 0.2 },
          doubleClick: { step: 1 },
          panning: { velocityDisabled: true },
        }}
      >
        {({ zoomIn, zoomOut, resetTransform }) => (
          <div style={{ height: '100%' }}>
            <div style={{
              display: "flex",
              justifyContent: "center",
              marginBottom: "0.1rem",
              gap: "1rem",
              position: 'absolute',
              top: '10px',
              right: '10px',
              zIndex: 10
            }}>
              <i onClick={zoomIn} className="fi fi-rr-zoom-in" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
              <i onClick={zoomOut} className="fi fi-rr-zoom-out" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
              <i onClick={resetTransform} className="fi fi-rr-rotate-right" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
            </div>
            <TransformComponent wrapperStyle={{ width: '100%', height: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%' }}>
                <img style={{ maxHeight: "80vh", maxWidth: "100%" }} src={displayImage} alt="Land Cover Classification" loading="lazy" />
              </div>
            </TransformComponent>
          </div>
        )}
      </TransformWrapper>
    </div>
  );
};

export default ImageViewer;
