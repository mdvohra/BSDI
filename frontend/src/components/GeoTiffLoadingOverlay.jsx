import React from "react";
import "./GeoTiffLoadingOverlay.css";

export const GEOTIFF_LOADING_MESSAGE =
  "Please wait a moment while we load your image, detect the CRS, and prepare it for the map.";

export default function GeoTiffLoadingOverlay({ visible, message = GEOTIFF_LOADING_MESSAGE }) {
  if (!visible) return null;
  return (
    <div className="geotiff-map-loading-overlay" role="status" aria-live="polite">
      <div className="geotiff-map-loading-spinner" aria-hidden />
      <p className="geotiff-map-loading-text">{message}</p>
    </div>
  );
}
