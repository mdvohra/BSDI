/**
 * WGS84 [south, west, north, east] for full raster extent — same idea as GeoTIFFMap.jsx (Leaflet).
 * Used to send roi_full_bounds_swne with ROI so the server can clip without GDAL/PROJ transforms.
 */
import proj4 from 'proj4';

proj4.defs('EPSG:32643', '+proj=utm +zone=43 +datum=WGS84 +units=m +no_defs');
proj4.defs('EPSG:32644', '+proj=utm +zone=44 +datum=WGS84 +units=m +no_defs');
proj4.defs('EPSG:32645', '+proj=utm +zone=45 +datum=WGS84 +units=m +no_defs');
proj4.defs('EPSG:32646', '+proj=utm +zone=46 +datum=WGS84 +units=m +no_defs');
proj4.defs(
  'EPSG:3857',
  '+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +wktext +no_defs'
);

function ensureUtmDef(epsgNum) {
  const epsg = `EPSG:${epsgNum}`;
  if (proj4.defs(epsg)) return epsg;
  const zone = epsgNum % 100;
  const south = epsgNum >= 32700;
  proj4.defs(
    epsg,
    `+proj=utm +zone=${zone} ${south ? '+south' : ''} +datum=WGS84 +units=m +no_defs`
  );
  return epsg;
}

/**
 * @param {import('georaster').default} raster - parsed georaster
 * @returns {[number, number, number, number]|null} south, west, north, east
 */
export function wgs84BoundsSwneFromGeoraster(raster) {
  if (!raster) return null;
  const projCode = raster.projection?.toString() || null;
  const { xmin, xmax, ymin, ymax } = raster;

  const spanX = Math.abs(xmax - xmin);
  const spanY = Math.abs(ymax - ymin);

  if (!projCode || projCode === '32767' || projCode === 'EPSG:32767') {
    const south = Math.min(ymin, ymax);
    const north = Math.max(ymin, ymax);
    const west = Math.min(xmin, xmax);
    const east = Math.max(xmin, xmax);
    if (spanX < 1e-10 || spanY < 1e-10) return null;
    return [south, west, north, east];
  }

  if (String(projCode).includes('4326')) {
    const south = Math.min(ymin, ymax);
    const north = Math.max(ymin, ymax);
    const west = Math.min(xmin, xmax);
    const east = Math.max(xmin, xmax);
    return [south, west, north, east];
  }

  const m = /^EPSG:(\d+)$/i.exec(projCode);
  if (!m) return null;
  const numeric = parseInt(m[1], 10);
  if (numeric === 3857) {
    const corners = [
      [xmin, ymin],
      [xmin, ymax],
      [xmax, ymax],
      [xmax, ymin],
    ];
    const wgsCorners = corners.map(([x, y]) => {
      const [lng, lat] = proj4('EPSG:3857', 'EPSG:4326', [x, y]);
      return [lat, lng];
    });
    const lats = wgsCorners.map((c) => c[0]);
    const lngs = wgsCorners.map((c) => c[1]);
    return [Math.min(...lats), Math.min(...lngs), Math.max(...lats), Math.max(...lngs)];
  }
  const isUTM =
    (numeric >= 32601 && numeric <= 32660) || (numeric >= 32701 && numeric <= 32760);
  if (isUTM) {
    const epsg = ensureUtmDef(numeric);
    const corners = [
      [xmin, ymin],
      [xmin, ymax],
      [xmax, ymax],
      [xmax, ymin],
    ];
    const wgsCorners = corners.map(([x, y]) => {
      const [lng, lat] = proj4(epsg, 'EPSG:4326', [x, y]);
      return [lat, lng];
    });
    const lats = wgsCorners.map((c) => c[0]);
    const lngs = wgsCorners.map((c) => c[1]);
    const south = Math.min(...lats);
    const north = Math.max(...lats);
    const west = Math.min(...lngs);
    const east = Math.max(...lngs);
    return [south, west, north, east];
  }

  return null;
}
