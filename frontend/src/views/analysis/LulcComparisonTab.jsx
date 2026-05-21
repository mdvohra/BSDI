import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert } from 'react-bootstrap';
import parseGeoraster from 'georaster';

/** Matches backend/lulc/app.py CLASS_COLORS for legend swatches */
const CLASS_COLORS = [
  [34, 197, 94],
  [163, 230, 53],
  [251, 146, 60],
  [52, 211, 153],
  [192, 38, 211],
  [14, 165, 233],
  [59, 130, 246],
  [132, 204, 22],
  [250, 204, 21],
  [56, 189, 248],
  [37, 99, 235],
  [244, 114, 182],
  [101, 163, 13],
  [253, 224, 71],
  [239, 68, 68],
];

function hexFromRgb([r, g, b]) {
  const h = (n) => n.toString(16).padStart(2, '0');
  return `#${h(r)}${h(g)}${h(b)}`;
}

function joinUrl(base, path) {
  if (!path) return null;
  const b = (base || '').replace(/\/$/, '');
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${b}${p}`;
}

function readId2Label(bundle) {
  const meta = bundle?.raw?.lulc_meta_json;
  if (!meta || typeof meta.id2label !== 'object') return {};
  return meta.id2label;
}

function mergeClassIndices(bundleA, bundleB) {
  const a = readId2Label(bundleA);
  const b = readId2Label(bundleB);
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  const indices = [...keys]
    .map((k) => Number(k))
    .filter((n) => Number.isFinite(n))
    .sort((x, y) => x - y);
  return indices.map((idx) => ({
    index: idx,
    label: a[String(idx)] || b[String(idx)] || `class ${idx}`,
  }));
}

function sampleClass(geo, x, y, imgW, imgH) {
  if (!geo?.values?.[0]) return null;
  const band = geo.values[0];
  const gw = geo.width;
  const gh = geo.height;
  const gx = Math.min(gw - 1, Math.max(0, Math.floor((x / Math.max(imgW, 1)) * gw)));
  const gy = Math.min(gh - 1, Math.max(0, Math.floor((y / Math.max(imgH, 1)) * gh)));
  return band[gy][gx];
}

function isNodata(v, explicit) {
  if (v == null || Number.isNaN(v)) return true;
  if (explicit !== undefined && explicit !== null && Number(v) === Number(explicit)) return true;
  return Number(v) === 255;
}

/**
 * Decode overlay (+ optional base) PNG and apply class mask when selectedIdx is set.
 */
function drawPanel(canvas, overlayImg, baseImg, geo, selectedIdx, nodataHint) {
  const nodataResolved =
    nodataHint !== undefined && nodataHint !== null ? nodataHint : geo?.noDataValue ?? 255;
  const ctx = canvas.getContext('2d');
  if (!ctx || !overlayImg) return;

  const w = overlayImg.naturalWidth;
  const h = overlayImg.naturalHeight;
  if (!w || !h) return;

  canvas.width = w;
  canvas.height = h;

  if (baseImg && baseImg.complete && baseImg.naturalWidth) {
    ctx.drawImage(baseImg, 0, 0, w, h);
  } else {
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, w, h);
  }

  if (selectedIdx == null || !geo?.values?.[0]) {
    ctx.drawImage(overlayImg, 0, 0);
    return;
  }

  ctx.drawImage(overlayImg, 0, 0);
  const imgData = ctx.getImageData(0, 0, w, h);
  const d = imgData.data;

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const cls = sampleClass(geo, x, y, w, h);
      const clsN = Math.round(Number(cls));
      const keep = !isNodata(cls, nodataResolved) && clsN === Number(selectedIdx);
      const i = (y * w + x) * 4;
      if (!keep) {
        d[i + 3] = 0;
      }
    }
  }
  ctx.putImageData(imgData, 0, 0);
}

function ComparisonCanvas({ label, apiBase, visual, selectedClassIdx }) {
  const canvasRef = useRef(null);
  const [overlayImg, setOverlayImg] = useState(null);
  const [baseImg, setBaseImg] = useState(null);
  const [geo, setGeo] = useState(null);
  const [loadErr, setLoadErr] = useState('');

  const overlayUrl = joinUrl(apiBase, visual?.overlay_png_path);
  const baseUrl = joinUrl(apiBase, visual?.base_png_path);
  const tiffUrl = joinUrl(apiBase, visual?.classes_geotiff_path);
  const nodataHint = visual?.class_grid_nodata;

  useEffect(() => {
    setOverlayImg(null);
    setBaseImg(null);
    setGeo(null);
    setLoadErr('');
    if (!overlayUrl) {
      setLoadErr('No overlay PNG path in bundle (file may be missing on server).');
      return;
    }

    let cancelled = false;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      if (!cancelled) {
        setLoadErr('');
        setOverlayImg(img);
      }
    };
    img.onerror = () => {
      if (!cancelled) setLoadErr('Could not load overlay PNG.');
    };
    img.src = overlayUrl;

    return () => {
      cancelled = true;
    };
  }, [overlayUrl]);

  useEffect(() => {
    setBaseImg(null);
    if (!baseUrl) return;
    let cancelled = false;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      if (!cancelled) setBaseImg(img);
    };
    img.onerror = () => {};
    img.src = baseUrl;
    return () => {
      cancelled = true;
    };
  }, [baseUrl]);

  useEffect(() => {
    setGeo(null);
    if (!tiffUrl) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(tiffUrl);
        if (!res.ok) throw new Error(String(res.status));
        const buf = await res.arrayBuffer();
        if (cancelled) return;
        const parsed = await parseGeoraster(buf);
        if (!cancelled) setGeo(parsed);
      } catch {
        if (!cancelled) setLoadErr('Could not load class GeoTIFF.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tiffUrl]);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c || !overlayImg) return;
    drawPanel(c, overlayImg, baseImg, geo, selectedClassIdx, nodataHint);
  }, [overlayImg, baseImg, geo, selectedClassIdx, nodataHint]);

  const hasClassRaster = Boolean(tiffUrl && geo?.values?.[0]);

  return (
    <div className="lulc-comparison-panel">
      <div className="lulc-comparison-panel-title small text-secondary mb-2">{label}</div>
      {loadErr && (
        <Alert variant="warning" className="py-2 small mb-2">
          {loadErr}
        </Alert>
      )}
      <div className="lulc-comparison-canvas-wrap">
        <canvas ref={canvasRef} className="lulc-comparison-canvas" />
      </div>
      {selectedClassIdx != null && !hasClassRaster && (
        <p className="small text-secondary mb-0 mt-2">Class mask unavailable for this run.</p>
      )}
    </div>
  );
}

export default function LulcComparisonTab({ apiBase, bundleA, bundleB }) {
  const [selectedClassIdx, setSelectedClassIdx] = useState(null);

  const classes = useMemo(() => mergeClassIndices(bundleA, bundleB), [bundleA, bundleB]);

  const va = bundleA?.derived?.visual;
  const vb = bundleB?.derived?.visual;

  const filterAvailable = Boolean(va?.classes_geotiff_path && vb?.classes_geotiff_path);

  const onChipClick = useCallback(
    (idx) => {
      setSelectedClassIdx((prev) => (prev === idx ? null : idx));
    },
    []
  );

  return (
    <div className="lulc-comparison-tab">
      <p className="small text-secondary mb-3">
        Side-by-side predicted overlays (cached PNG). Click a class to show only that land-cover in both maps; click
        again to show all classes.
      </p>
      {!filterAvailable && (
        <Alert variant="secondary" className="py-2 small mb-3">
          Class isolation needs the class-index GeoTIFF on <strong>both</strong> runs (GeoTIFF predictions). PNG previews
          still load below.
        </Alert>
      )}
      <div className="lulc-comparison-pair">
        <ComparisonCanvas
          label="Baseline (older · A)"
          apiBase={apiBase}
          visual={va}
          selectedClassIdx={selectedClassIdx}
        />
        <ComparisonCanvas
          label="Newer (B)"
          apiBase={apiBase}
          visual={vb}
          selectedClassIdx={selectedClassIdx}
        />
      </div>
      <div className="lulc-comparison-legend mt-3">
        <div className="small text-secondary mb-2">Classes</div>
        <div className="lulc-comparison-chips">
          {classes.length === 0 && (
            <span className="small text-secondary">No class names in saved metadata (id2label).</span>
          )}
          {classes.map(({ index, label }) => {
            const active = selectedClassIdx === index;
            const rgb = CLASS_COLORS[index] || [148, 163, 184];
            return (
              <button
                key={index}
                type="button"
                className={`lulc-comparison-chip ${active ? 'lulc-comparison-chip-active' : ''}`}
                onClick={() => onChipClick(index)}
                title={label}
              >
                <span className="lulc-comparison-chip-swatch" style={{ backgroundColor: hexFromRgb(rgb) }} />
                <span className="lulc-comparison-chip-label">{label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
