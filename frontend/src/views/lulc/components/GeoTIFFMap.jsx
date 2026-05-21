import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import GeoTiffLoadingOverlay from "../../../components/GeoTiffLoadingOverlay";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

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

/** Building footprints saved with this LULC run (WGS84 GeoJSON). */
const BuildingDetectionOverlay = ({ detectionUrlOrData }) => {
  const map = useMap();
  const layerRef = useRef(null);

  useEffect(() => {
    if (!detectionUrlOrData) return;

    if (!map._predictionsRenderer) {
      map._predictionsRenderer = L.canvas({ pane: "predictions-pane" });
    }
    if (layerRef.current && map.hasLayer(layerRef.current)) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    const style = {
      color: "#ef4444",
      weight: 2,
      opacity: 0.95,
      fillColor: "#f87171",
      fillOpacity: 0.2,
    };

    const addGeoJson = (geojson) => {
      const geoJsonLayer = L.geoJSON(geojson, {
        pane: "predictions-pane",
        renderer: map._predictionsRenderer,
        style: () => style,
      }).addTo(map);
      layerRef.current = geoJsonLayer;
    };

    let abort;
    if (typeof detectionUrlOrData === "string") {
      abort = new AbortController();
      fetch(detectionUrlOrData, { signal: abort.signal })
        .then((res) => {
          if (!res.ok) throw new Error(String(res.status));
          return res.json();
        })
        .then(addGeoJson)
        .catch(() => {});
      return () => {
        abort?.abort();
        if (layerRef.current && map.hasLayer(layerRef.current)) {
          map.removeLayer(layerRef.current);
          layerRef.current = null;
        }
      };
    }

    addGeoJson(detectionUrlOrData);
    return () => {
      if (layerRef.current && map.hasLayer(layerRef.current)) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [detectionUrlOrData, map]);

  return null;
};

import parseGeoraster from "georaster";
import GeoRasterLayer from "georaster-layer-for-leaflet";
import { rawToRgb } from "pixel-utils";
import proj4 from "proj4";

import RoiLeafletDraw from "./RoiLeafletDraw";

/** WGS84 [south, west, north, east] — must match Leaflet ROI polygon coordinates for server plate-carée clip */
function latLngBoundsToSwne(bounds) {
  if (!bounds || typeof bounds.isValid !== "function" || !bounds.isValid()) return null;
  const sw = bounds.getSouthWest();
  const ne = bounds.getNorthEast();
  return [sw.lat, sw.lng, ne.lat, ne.lng];
}

proj4.defs("EPSG:32643", "+proj=utm +zone=43 +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32644", "+proj=utm +zone=44 +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32645", "+proj=utm +zone=45 +datum=WGS84 +units=m +no_defs");
proj4.defs("EPSG:32646", "+proj=utm +zone=46 +datum=WGS84 +units=m +no_defs");
proj4.defs(
  "EPSG:3857",
  "+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs"
);

/**
 * georaster-layer-for-leaflet v4 scales DNs with pixel-utils `rawToRgb` (per-band min/max).
 * Overriding `pixelValuesToColorFn` with raw `rgb(R,G,B)` clipped uint16/float DNs to 0–255,
 * which washes the whole image to white.
 *
 * Here we reuse `rawToRgb` like the library, then hide rectangular bbox padding that is often
 * stored as exact (0,0,0) without GDAL nodata (acute/cropped footprints).
 *
 * Returns null if mins/maxs are missing so the layer uses its built-in coloring.
 */
export function createGeoRasterPixelValuesToColorFn(georaster) {
  if (Array.isArray(georaster.palette) && georaster.palette.length > 0) {
    const palette = georaster.palette;
    return (values) => {
      if (!values?.length) return null;
      const idx = values[0];
      if (idx === undefined) return null;
      const entry = palette[idx];
      return entry !== undefined ? entry : null;
    };
  }

  const mins = georaster.mins;
  const maxs = georaster.maxs;
  if (!Array.isArray(mins) || !Array.isArray(maxs) || mins.length !== maxs.length || mins.length === 0) {
    return null;
  }

  const ranges = mins.map((min, i) => [min, maxs[i]]);
  const toRgbCss = rawToRgb({
    format: "string",
    flip: georaster.numberOfRasters === 1,
    ranges,
    round: true,
    old_no_data_value: georaster.noDataValue,
  });

  return (values) => {
    if (!values?.length) return null;

    if (
      values.length === 3 &&
      Number(values[0]) === 0 &&
      Number(values[1]) === 0 &&
      Number(values[2]) === 0
    ) {
      return null;
    }

    return toRgbCss(values);
  };
}

/** Add georaster layer to map; returns created GeoRasterLayer instance */
function mountGeoRasterOnMap(map, raster, layerRef, autoFitBounds, onMapBoundsSwne) {
  if (layerRef.current && map.hasLayer(layerRef.current)) {
    map.removeLayer(layerRef.current);
    layerRef.current = null;
  }

  const pixelValuesToColorFn = createGeoRasterPixelValuesToColorFn(raster);
  let projCode = raster.projection?.toString() || null;

  const addRaster = (resolution, fitBounds) => {
    const layer = new GeoRasterLayer({
      georaster: raster,
      opacity: 1,
      resolution,
      ...(pixelValuesToColorFn ? { pixelValuesToColorFn } : {}),
    });
    layer.addTo(map);
    layerRef.current = layer;

    if (typeof onMapBoundsSwne === "function" && fitBounds) {
      const swne = latLngBoundsToSwne(fitBounds);
      if (swne) onMapBoundsSwne(swne);
    }

    if (autoFitBounds && fitBounds?.isValid?.() && fitBounds.isValid()) {
      map.fitBounds(fitBounds, { maxZoom: 20, padding: [40, 40] });
    }
  };

  if (!projCode || projCode === "32767" || projCode === "EPSG:32767") {
    const bounds = L.latLngBounds([raster.ymin, raster.xmin], [raster.ymax, raster.xmax]);
    const w = Math.abs(raster.xmax - raster.xmin);
    const h = Math.abs(raster.ymax - raster.ymin);
    const isSmall = w < 0.01 || h < 0.01;
    addRaster(isSmall ? 64 : 256, bounds);
    if (autoFitBounds && isSmall && bounds.isValid()) map.setView(bounds.getCenter(), 18);
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
    if (autoFitBounds && isSmall && bounds.isValid()) map.setView(bounds.getCenter(), 18);
    return;
  }

  if (projCode.includes("4326")) {
    const bounds = L.latLngBounds([raster.ymin, raster.xmin], [raster.ymax, raster.xmax]);
    const bw = bounds.getEast() - bounds.getWest();
    const bh = bounds.getNorth() - bounds.getSouth();
    const isSmall = bw < 0.0001 || bh < 0.0001;

    addRaster(isSmall ? 64 : 256, bounds);
    if (autoFitBounds && isSmall && bounds.isValid()) map.setView(bounds.getCenter(), 18);
    return;
  }

  const layer = new GeoRasterLayer({
    georaster: raster,
    opacity: 1,
    resolution: 256,
    ...(pixelValuesToColorFn ? { pixelValuesToColorFn } : {}),
  });
  layer.addTo(map);
  layerRef.current = layer;
  if (typeof onMapBoundsSwne === "function" && layer.getBounds) {
    const swne = latLngBoundsToSwne(layer.getBounds());
    if (swne) onMapBoundsSwne(swne);
  }
  if (autoFitBounds && layer.getBounds) {
    map.fitBounds(layer.getBounds(), { maxZoom: 20, padding: [40, 40] });
  }
}

/**
 * @param {Blob|File|string} [tiffBlob] - load from blob/url
 * @param {object} [georaster] - pre-parsed georaster (shared across maps)
 * @param {boolean} [autoFitBounds=true] - fit map to raster when layer is added
 */
export const GeoTIFFLayer = ({
  tiffBlob,
  georaster: georasterProp,
  autoFitBounds = true,
  onMapBoundsSwne,
  onRasterLoadFinished,
}) => {
  const map = useMap();
  const layerRef = useRef(null);
  const boundsCbRef = useRef(onMapBoundsSwne);
  boundsCbRef.current = onMapBoundsSwne;
  const onDoneRef = useRef(onRasterLoadFinished);
  onDoneRef.current = onRasterLoadFinished;
  const [raster, setRaster] = useState(georasterProp ?? null);

  useEffect(() => {
    if (georasterProp) {
      setRaster(georasterProp);
      return;
    }
    let cancelled = false;
    const load = async () => {
      if (!tiffBlob) {
        setRaster(null);
        return;
      }
      setRaster(null);
      try {
        let buf;
        if (typeof tiffBlob === "string") {
          const res = await fetch(tiffBlob);
          buf = await res.arrayBuffer();
        } else {
          buf = await tiffBlob.arrayBuffer();
        }
        if (cancelled) return;
        const parsed = await parseGeoraster(buf);
        if (!cancelled) setRaster(parsed);
      } catch (err) {
        console.error("TIFF load error:", err);
        if (!cancelled) {
          setRaster(null);
          onDoneRef.current?.();
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [tiffBlob, georasterProp]);

  useEffect(() => {
    if (!raster) {
      boundsCbRef.current?.(null);
      return undefined;
    }
    try {
      mountGeoRasterOnMap(map, raster, layerRef, autoFitBounds, (swne) =>
        boundsCbRef.current?.(swne)
      );
      onDoneRef.current?.();
    } catch (err) {
      console.error("GeoRaster mount error:", err);
      boundsCbRef.current?.(null);
      onDoneRef.current?.();
    }
    return () => {
      if (layerRef.current && map.hasLayer(layerRef.current)) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [raster, map, autoFitBounds]);

  return null;
};

/**
 * bounds: WGS84 [south, west, north, east] (same as backend get_geobounds)
 */
export const OverlayImageLayer = ({ bounds, imageUrl, opacity = 0.72, autoFitBounds = true }) => {
  const map = useMap();
  const layerRef = useRef(null);

  useEffect(() => {
    if (!bounds || !imageUrl) return;

    if (layerRef.current && map.hasLayer(layerRef.current)) {
      map.removeLayer(layerRef.current);
    }

    const leafletBounds = L.latLngBounds(
      [bounds[0], bounds[1]],
      [bounds[2], bounds[3]]
    );

    const overlay = L.imageOverlay(imageUrl, leafletBounds, { opacity });
    overlay.addTo(map);
    layerRef.current = overlay;
    if (autoFitBounds && leafletBounds.isValid()) {
      map.fitBounds(leafletBounds, { maxZoom: 20, padding: [40, 40] });
    }

    return () => {
      if (layerRef.current && map.hasLayer(layerRef.current)) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [bounds, imageUrl, opacity, autoFitBounds, map]);

  return null;
};

function HexagonGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
      <polygon fill="currentColor" points="12,2 22,8 22,16 12,22 2,16 2,8" />
    </svg>
  );
}

const LULCGeoTIFFMap = ({
  tiffBlob,
  overlayImageUrl,
  bounds,
  overlayAutoFitBounds = true,
  /** 1 = opaque classification (no base imagery through overlay); <1 blends with GeoTIFF below */
  overlayOpacity = 0.72,
  roiToolsEnabled = false,
  roiDrawActive = false,
  onRoiDrawActiveChange,
  roiGeometry,
  onRoiGeometryChange,
  onRasterMapBoundsSwne,
  buildingDetectionUrl,
}) => {
  const [tiffLoading, setTiffLoading] = useState(false);

  useLayoutEffect(() => {
    setTiffLoading(Boolean(tiffBlob));
  }, [tiffBlob]);

  return (
    <div className="lulc-geotiff-map-wrap">
      <GeoTiffLoadingOverlay visible={tiffLoading && Boolean(tiffBlob)} />
      <MapContainer
        center={[20.5937, 78.9629]}
        zoom={5}
        maxZoom={22}
        minZoom={2}
        style={{ height: "100%", width: "100%" }}
        zoomControl
      >
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />

        <PredictionsPaneInit />
        {tiffBlob && (
          <GeoTIFFLayer
            tiffBlob={tiffBlob}
            onMapBoundsSwne={onRasterMapBoundsSwne}
            onRasterLoadFinished={() => setTiffLoading(false)}
          />
        )}
        {overlayImageUrl && bounds && (
          <OverlayImageLayer
            bounds={bounds}
            imageUrl={overlayImageUrl}
            opacity={overlayOpacity}
            autoFitBounds={overlayAutoFitBounds}
          />
        )}
        {buildingDetectionUrl ? <BuildingDetectionOverlay detectionUrlOrData={buildingDetectionUrl} /> : null}
        {roiToolsEnabled && tiffBlob && (
          <RoiLeafletDraw
            drawActive={roiDrawActive}
            geometry={roiGeometry}
            onGeometryChange={onRoiGeometryChange}
          />
        )}
      </MapContainer>
      {roiToolsEnabled && tiffBlob && (
        <div className="lulc-roi-toolbar">
          <button
            type="button"
            className={`lulc-roi-fab ${roiDrawActive ? "lulc-roi-fab-active" : ""}`}
            title={
              roiDrawActive
                ? "Exit draw mode (polygon toolbar hides)"
                : "Draw polygon: classify inside this area only"
            }
            onClick={() => onRoiDrawActiveChange?.(!roiDrawActive)}
          >
            <HexagonGlyph />
          </button>
          {roiGeometry && (
            <button
              type="button"
              className="lulc-roi-clear"
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

export default LULCGeoTIFFMap;
