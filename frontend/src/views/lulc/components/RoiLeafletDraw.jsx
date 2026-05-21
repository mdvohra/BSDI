import React, { useEffect, useRef, useState } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-draw/dist/leaflet.draw.css";
import "leaflet-draw";

function isValidPolygonGeometry(geom) {
  if (!geom || geom.type !== "Polygon" || !Array.isArray(geom.coordinates)) return false;
  const ring = geom.coordinates[0];
  return Array.isArray(ring) && ring.length >= 4;
}

/**
 * ROI polygon in WGS84 (GeoJSON geometry). Leaflet.draw CREATED/EDITED emit GeoJSON lon/lat.
 * @param {string} [drawControlPosition] - Leaflet corner for the draw toolbar (default "topleft"). Use "topright" on full-screen maps where the app sidebar hides topleft.
 */
function RoiLeafletDraw({
  drawActive,
  geometry,
  onGeometryChange,
  drawControlPosition = "topleft",
}) {
  const map = useMap();
  const [featureGroup, setFeatureGroup] = useState(null);
  const drawControlRef = useRef(null);
  const onGeometryChangeRef = useRef(onGeometryChange);
  onGeometryChangeRef.current = onGeometryChange;

  useEffect(() => {
    const fg = new L.FeatureGroup();
    map.addLayer(fg);
    setFeatureGroup(fg);

    const onCreated = (e) => {
      fg.clearLayers();
      fg.addLayer(e.layer);
      const geom = e.layer.toGeoJSON()?.geometry;
      if (isValidPolygonGeometry(geom)) {
        onGeometryChangeRef.current(geom);
      }
    };
    const onEdited = (e) => {
      e.layers.eachLayer((layer) => {
        const geom = layer.toGeoJSON()?.geometry;
        if (isValidPolygonGeometry(geom)) {
          onGeometryChangeRef.current(geom);
        }
      });
    };
    const onDeleted = () => {
      onGeometryChangeRef.current(null);
    };

    map.on(L.Draw.Event.CREATED, onCreated);
    map.on(L.Draw.Event.EDITED, onEdited);
    map.on(L.Draw.Event.DELETED, onDeleted);

    return () => {
      map.off(L.Draw.Event.CREATED, onCreated);
      map.off(L.Draw.Event.EDITED, onEdited);
      map.off(L.Draw.Event.DELETED, onDeleted);
      map.removeLayer(fg);
      setFeatureGroup(null);
    };
  }, [map]);

  useEffect(() => {
    if (!featureGroup) return;
    featureGroup.clearLayers();
    if (isValidPolygonGeometry(geometry)) {
      const gj = L.geoJSON(
        { type: "Feature", properties: {}, geometry },
        {
          style: {
            color: "#2563eb",
            weight: 2,
            fillOpacity: 0.12,
          },
        }
      );
      gj.eachLayer((layer) => featureGroup.addLayer(layer));
    }
  }, [geometry, featureGroup]);

  useEffect(() => {
    if (!featureGroup) return;
    if (drawControlRef.current) {
      map.removeControl(drawControlRef.current);
      drawControlRef.current = null;
    }
    if (drawActive) {
      const drawControl = new L.Control.Draw({
        position: drawControlPosition,
        draw: {
          polygon: {
            allowIntersection: false,
            // Leaflet 1.9+ breaks leaflet-draw's readableArea (ReferenceError: type is not defined)
            showArea: false,
          },
          polyline: false,
          rectangle: false,
          circle: false,
          marker: false,
          circlemarker: false,
        },
        edit: {
          featureGroup,
          remove: true,
        },
      });
      map.addControl(drawControl);
      drawControlRef.current = drawControl;
    }
    return () => {
      if (drawControlRef.current) {
        map.removeControl(drawControlRef.current);
        drawControlRef.current = null;
      }
    };
  }, [map, drawActive, featureGroup, drawControlPosition]);

  return null;
}

export default RoiLeafletDraw;
