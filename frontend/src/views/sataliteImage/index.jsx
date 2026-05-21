// import React, { useState, useEffect } from 'react';
// import ImageUploader from './components/ImageUploader';
// import ImageViewer from './components/ImageViewer';
// // import Chat from './components/Chat';
// import ExportButton from './components/ExportButton';
// import { downloadGeoJSON, downloadShapefile } from './services/api';
// import { Row, Col, Container } from 'react-bootstrap';
// // import MapViewer from './components/MapViewer';
// import 'leaflet/dist/leaflet.css';
// import { MapContainer, TileLayer, useMap } from 'react-leaflet';
// import GeoTIFFMap from './components/GeoTIFFMap';
// import { useNavigate } from 'react-router-dom';

// const SatelliteImage = () => {
//   const [predictionData, setPredictionData] = useState(null);
//   const [uploadedImage, setUploadedImage] = useState(null);
//   const [predictionImageUrl, setPredictionImageUrl] = useState(null);
//   const [fileType, setFileType] = useState(null);
//   const [uploadedFile, setUploadedFile] = useState(null);
//   useEffect(() => {
//     // Cleanup function to revoke object URLs when component unmounts
//     return () => {
//       if (uploadedImage) {
//         URL.revokeObjectURL(uploadedImage);
//       }
//       if (predictionImageUrl) {
//         URL.revokeObjectURL(predictionImageUrl);
//       }
//     };
//   }, [uploadedImage, predictionImageUrl]);

//   // const handleUploadSuccess = (data) => {
//   //   // Convert the hex string back to a Blob URL for image display
//   //   const byteArray = new Uint8Array(
//   //     data.image.match(/.{1,2}/g).map((byte) => parseInt(byte, 16))
//   //   );
//   //   const blob = new Blob([byteArray], { type: 'image/png' });
//   //   const imageUrl = URL.createObjectURL(blob);

//   //   // Update the prediction data with the new image URL
//   //   setPredictionData({
//   //     ...data,
//   //     image: imageUrl, // Use the Blob URL for image display
//   //     detectionData: data.detection_data,
//   //     imageMetadata: {
//   //       bounds: data.image_bounds,
//   //       crs: data.crs,
//   //     },
//   //   });

//   //   // Clean up the previous uploaded image URL
//   //   if (uploadedImage) {
//   //     URL.revokeObjectURL(uploadedImage);
//   //     setUploadedImage(null);
//   //   }
//   // };

//   // 
//   const handleUploadSuccess = (data) => {
//     console.log("✅ Upload success data:", data);

//     // Extract the overlay URL from the response
//     const overlayUrl = data.overlay_url || data.overlay_uri;
//     const fullOverlayUrl = overlayUrl.startsWith('http') 
//       ? overlayUrl 
//       : `${import.meta.env.VITE_API_BASE_URL}${overlayUrl}`;

//     setPredictionImageUrl(fullOverlayUrl);

//     // Parse the GeoJSON from the response
//     let detectionGeoJSON = null;
//     if (data.geojson_url || data.geojson_uri) {
//       // If backend provides GeoJSON URL, fetch it
//       const geoJsonUrl = data.geojson_url || data.geojson_uri;
//       const fullGeoJsonUrl = geoJsonUrl.startsWith('http')
//         ? geoJsonUrl
//         : `${import.meta.env.VITE_API_BASE_URL}${geoJsonUrl}`;

//       // Fetch the GeoJSON file
//       fetch(fullGeoJsonUrl)
//         .then(res => res.json())
//         .then(geoJson => {
//           console.log("📊 Loaded GeoJSON:", geoJson);
//           setPredictionData(prev => ({
//             ...prev,
//             detectionData: geoJson.features || geoJson
//           }));
//         })
//         .catch(err => console.error("❌ Failed to load GeoJSON:", err));
//     }

//     // Parse overlay_bounds - it's an array of 2 arrays: [[minLat, minLon], [maxLat, maxLon]]
//     const bounds = data.overlay_bounds;

//     setPredictionData({
//       ...data,
//       image: fullOverlayUrl,
//       detectionData: detectionGeoJSON,
//       imageMetadata: {
//         bounds: bounds, // Format: [[south, west], [north, east]]
//         crs: data.crs || "EPSG:2230",
//         width: data.width,
//         height: data.height,
//         total_area: data.total_area,
//         count: data.count,
//         average_area: data.average_area
//       },
//     });

//     console.log("📊 Overlay URL:", fullOverlayUrl);
//     console.log("🗺️ Image bounds:", bounds);
//     console.log("🗺️ CRS:", data.crs);
//   };


//   const handleImageSelected = (imageUrl) => {
//     setUploadedImage(imageUrl);
//     setPredictionData(null); // Reset prediction data when a new image is selected
//   };
//   // const handleImageSelected = (file) => {
//   //   setUploadedImage(file);
//   //   setPredictionData(null); // Reset prediction data when a new image is selected
//   // };

//   const handleExport = async (format) => {
//     if (!predictionData) {
//       alert('No data available to export!');
//       return;
//     }

//     try {
//       let fileData;
//       let fileName;

//       if (format === 'geojson') {
//         if (!predictionData.geojson_filename) {
//           alert('GeoJSON file not available.');
//           return;
//         }
//         const arrayBuffer = await downloadGeoJSON(predictionData.geojson_filename);
//         fileData = new Blob([arrayBuffer], { type: 'application/geo+json' });
//         fileName = 'export.geojson';
//       } else if (format === 'shapefile') {
//         if (!predictionData.shapefile_filename) {
//           alert('Shapefile not available.');
//           return;
//         }
//         const arrayBuffer = await downloadShapefile(predictionData.shapefile_filename);
//         fileData = new Blob([arrayBuffer], { type: 'application/zip' });
//         fileName = 'export.zip';
//       }

//       const url = window.URL.createObjectURL(fileData);

//       // Trigger the download
//       const link = document.createElement('a');
//       link.href = url;
//       link.setAttribute('download', fileName);
//       document.body.appendChild(link);
//       link.click();
//       document.body.removeChild(link);
//       window.URL.revokeObjectURL(url); // Clean up URL
//     } catch (error) {
//       console.error('Error downloading file:', error);
//       alert('Failed to download file.');
//     }
//   };

//   return (
//     <Container>
//       <div>
//         {/* <h2>Tree crown Delination</h2> */}
//         <Row>
//           <Col lg={3}>
//             <ImageUploader
//               onUploadSuccess={handleUploadSuccess}
//               onImageSelected={handleImageSelected}
//               setFileType={setFileType}
//               setUploadedFile={setUploadedFile}
//             />
//           </Col>
//           <Col lg={9} >
//             <div style={{
//               marginTop: '0.7rem',
//             }}>
//               <ImageViewer file={uploadedFile} fileType={fileType} imageData={predictionData?.image || uploadedImage} detectionData={predictionData?.detectionData} imageMetadata={predictionData?.imageMetadata} />
//             </div>
//           </Col>
//         </Row>
//         <div>

//           {/* <Chat
//             treeCount={predictionData?.tree_count || 0}
//             totalArea={predictionData?.total_area || 0.0}
//             averageTreeArea={predictionData?.average_tree_area || 0.0}
//             imageMetadata={{
//               width: predictionData?.image_width || 'N/A',
//               height: predictionData?.image_height || 'N/A',
//               crs: predictionData?.crs || 'N/A',
//               transform: predictionData?.transform || 'N/A',
//             }}
//           /> */}

//           <ExportButton onExport={handleExport} />

//         </div>
//       </div>
//     </Container>
//   );
// };

// export default SatelliteImage;


import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ImageUploader from './components/ImageUploader';
import ImageViewer from './components/ImageViewer';
import { OIL_SPILL_CLASS_COLORS_HEX } from './constants/oilSpillLegendColors';
import ExportButton from './components/ExportButton';
import {
  downloadGeoJSON,
  downloadShapefile,
  downloadPredictionGeoTiff,
  fetchSavedDetectionRuns,
  filterGeoJsonByConfidence,
  fetchUnetGeojsonAtThreshold,
  postprocessLabPreview,
  postprocessLabApply,
} from './services/api';
import 'leaflet/dist/leaflet.css';
import './styles.css';
import { useUiConfig } from '../../contexts/UiConfigContext';

/** Feature count for top-right "Objects Detected" during incremental SSE. */
function geoJsonFeatureCount(gj) {
  if (!gj) return 0;
  if (Array.isArray(gj.features)) return gj.features.length;
  if (Array.isArray(gj)) return gj.length;
  return 0;
}

function boundsFromGeoJson(gj) {
  const feats = Array.isArray(gj?.features) ? gj.features : [];
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  const walk = (coords) => {
    if (!Array.isArray(coords)) return;
    if (typeof coords[0] === 'number' && typeof coords[1] === 'number') {
      const lon = Number(coords[0]);
      const lat = Number(coords[1]);
      if (Number.isFinite(lon) && Number.isFinite(lat)) {
        minLon = Math.min(minLon, lon);
        minLat = Math.min(minLat, lat);
        maxLon = Math.max(maxLon, lon);
        maxLat = Math.max(maxLat, lat);
      }
      return;
    }
    coords.forEach(walk);
  };
  feats.forEach((f) => walk(f?.geometry?.coordinates));
  if (![minLon, minLat, maxLon, maxLat].every(Number.isFinite)) return null;
  return [[minLat, minLon], [maxLat, maxLon]];
}

const SatelliteImage = () => {
  const { uiConfig, loading: uiCfgLoading } = useUiConfig();
  const [predictionData, setPredictionData] = useState(null);
  const [uploadedImage, setUploadedImage] = useState(null);
  const [predictionImageUrl, setPredictionImageUrl] = useState(null);
  const [fileType, setFileType] = useState(null);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [roiGeometry, setRoiGeometry] = useState(null);
  const [roiDrawActive, setRoiDrawActive] = useState(false);
  const [geotiffBoundsSwne, setGeotiffBoundsSwne] = useState(null);
  /** Post-inference display threshold (Mask R-CNN: filter full GeoJSON; UNet: re-vectorize API). */
  const [displayThreshold, setDisplayThreshold] = useState(0.3);
  const [fullMaskrcnnGeoJson, setFullMaskrcnnGeoJson] = useState(null);
  const [unetThresholdGeoJson, setUnetThresholdGeoJson] = useState(null);
  /** When set, map shows this preview instead of normal threshold / full_geojson pipeline (post-process lab). */
  const [postprocessPreviewGeoJson, setPostprocessPreviewGeoJson] = useState(null);
  const [postprocessBusy, setPostprocessBusy] = useState(false);
  const [ppRegularizeMode, setPpRegularizeMode] = useState('off');
  const [ppTolerance, setPpTolerance] = useState(2);
  const [ppIou, setPpIou] = useState('');
  const [ppGap, setPpGap] = useState('');
  const [ppMergeTouching, setPpMergeTouching] = useState(false);
  const [ppAdvancedOpen, setPpAdvancedOpen] = useState(false);
  const postprocessLabEnabled = import.meta.env.VITE_ENABLE_POSTPROCESS_LAB === 'true';
  const [savedRuns, setSavedRuns] = useState([]);
  const [selectedSavedRunKey, setSelectedSavedRunKey] = useState('');
  const [savedRunsLoading, setSavedRunsLoading] = useState(false);

  useEffect(() => {
    if (uiCfgLoading) return;
    const d = Number(uiConfig.default_inference_threshold);
    if (!Number.isFinite(d)) return;
    if (!uiConfig.show_detection_threshold) {
      setDisplayThreshold(d);
    }
  }, [uiCfgLoading, uiConfig.default_inference_threshold, uiConfig.show_detection_threshold]);

  const handleRoiGeometryChange = useCallback((geom) => {
    setRoiGeometry(geom);
  }, []);

  const handleRasterMapBoundsSwne = useCallback((swne) => {
    setGeotiffBoundsSwne(swne && swne.length === 4 ? swne : null);
  }, []);

  const handleStreamDetectionEvent = useCallback((ev, ctx) => {
    const backendUrl = ctx?.backendURL || 'http://localhost:8000/maskrcnn';
    const isMaskrcnn = /8001|maskrcnn/i.test(backendUrl || '');
    const taskHint = ev.task;
    if (ev.type === 'start') {
      setPredictionImageUrl(null);
      setPredictionData({
        detectionData: { type: 'FeatureCollection', features: [] },
        imageMetadata: {
          bounds: ev.overlay_bounds,
          crs: ev.crs || 'EPSG:4326',
          width: ev.width,
          height: ev.height,
          count: 0,
        },
        _backendURL: backendUrl,
        _backendType: 'detection',
        task: taskHint ?? (isMaskrcnn ? 'maskrcnn' : 'unet'),
        model_family: ev.model_family,
        ...(ev.model_name != null && ev.model_name !== ''
          ? { model_name: ev.model_name }
          : {}),
      });
      return;
    }
    if (ev.type === 'progress' && ev.geojson) {
      const count = geoJsonFeatureCount(ev.geojson);
      setPredictionData((prev) => ({
        ...(prev || {}),
        task: prev?.task ?? taskHint ?? (isMaskrcnn ? 'maskrcnn' : 'unet'),
        detectionData: ev.geojson,
        imageMetadata: {
          ...(prev?.imageMetadata || {}),
          bounds: prev?.imageMetadata?.bounds ?? ev.overlay_bounds,
          count,
        },
        _backendURL: backendUrl,
        _backendType: 'detection',
        model_family: ev.model_family ?? prev?.model_family,
        ...(ev.model_name != null && ev.model_name !== ''
          ? { model_name: ev.model_name }
          : {}),
      }));
    }
  }, []);

  useEffect(() => {
    return () => {
      if (uploadedImage) URL.revokeObjectURL(uploadedImage);
      if (predictionImageUrl) URL.revokeObjectURL(predictionImageUrl);
    };
  }, [uploadedImage, predictionImageUrl]);

  const refreshSavedRuns = useCallback(async () => {
    setSavedRunsLoading(true);
    try {
      const runs = await fetchSavedDetectionRuns(60);
      setSavedRuns(runs);
      if (runs.length > 0 && !selectedSavedRunKey) {
        setSelectedSavedRunKey(`${runs[0]._backendURL}|${runs[0].task}|${runs[0].run_id}`);
      }
    } catch (err) {
      console.error('Failed to load saved runs:', err);
      setSavedRuns([]);
    } finally {
      setSavedRunsLoading(false);
    }
  }, [selectedSavedRunKey]);

  useEffect(() => {
    refreshSavedRuns();
  }, [refreshSavedRuns]);

  const handleLoadSavedRun = useCallback(async () => {
    const selected = savedRuns.find(
      (r) => `${r._backendURL}|${r.task}|${r.run_id}` === selectedSavedRunKey
    );
    if (!selected) return;
    const backendUrl = selected._backendURL;
    const geoJsonUrl = selected.geojson_url
      ? (selected.geojson_url.startsWith('http')
        ? selected.geojson_url
        : `${backendUrl}${selected.geojson_url}`)
      : null;
    if (!geoJsonUrl) return;
    try {
      const resp = await fetch(geoJsonUrl);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const gj = await resp.json();
      const b = boundsFromGeoJson(gj);
      setPredictionImageUrl(null);
      setPredictionData({
        task: selected.task,
        run_id: selected.run_id,
        model_name: selected.model_name || '',
        detectionData: gj,
        imageMetadata: {
          bounds: b,
          crs: 'EPSG:4326',
          count: geoJsonFeatureCount(gj),
          width: selected.width,
          height: selected.height,
        },
        _backendURL: backendUrl,
        _backendType: 'detection',
        full_geojson_url: selected.full_geojson_url || null,
        confidence_bundle_saved: selected.confidence_bundle_saved,
        inference_threshold: selected.inference_threshold,
      });
      setDisplayThreshold(
        Number.isFinite(Number(selected.inference_threshold))
          ? Number(selected.inference_threshold)
          : 0.3
      );
      setRoiDrawActive(false);
      setRoiGeometry(null);
      setGeotiffBoundsSwne(null);
    } catch (err) {
      console.error('Failed to load saved run:', err);
    }
  }, [savedRuns, selectedSavedRunKey]);

  const handleUploadSuccess = async (data) => {
    const backendUrl = data._backendURL || 'http://localhost:8000/maskrcnn';
    const backendType = data._backendType || 'detection';

    if (backendType === 'super-resolution') {
      const overlayUrl = data.overlay_url;
      const fullOverlayUrl = overlayUrl?.startsWith('http')
        ? overlayUrl
        : `${backendUrl}${overlayUrl}`;

      setPredictionImageUrl(fullOverlayUrl);

      const bounds = data.overlay_bounds;
      if (!bounds || !Array.isArray(bounds) || bounds.length !== 2) {
        console.error('Invalid bounds format:', bounds);
        return;
      }

      setPredictionData({
        ...data,
        image: fullOverlayUrl,
        detectionData: null,
        imageMetadata: {
          bounds,
          crs: data.crs || 'EPSG:4326',
          width: data.output_width,
          height: data.output_height,
          original_width: data.original_width,
          original_height: data.original_height,
          scale_factor: data.scale_factor,
          psnr_improvement: data.psnr_improvement,
          ssim_improvement: data.ssim_improvement
        },
        _backendURL: backendUrl,
        _backendType: backendType
      });
    } else {
      const overlayUrl = data.overlay_url;
      const fullOverlayUrl = overlayUrl?.startsWith('http')
        ? overlayUrl
        : `${backendUrl}${overlayUrl}`;

      setPredictionImageUrl(fullOverlayUrl);

      let detectionGeoJSON = null;
      if (data.geojson_url) {
        const geoJsonUrl = data.geojson_url.startsWith('http')
          ? data.geojson_url
          : `${backendUrl}${data.geojson_url}`;

        try {
          const response = await fetch(geoJsonUrl);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          detectionGeoJSON = await response.json();
        } catch (err) {
          console.error('Failed to load GeoJSON:', err);
          detectionGeoJSON = geoJsonUrl;
        }
      }

      let inferredTask = data.task;
      if (!inferredTask) {
        if (/oil_spill/i.test(backendUrl)) inferredTask = 'oil_spill';
        else if (/8001|maskrcnn/i.test(backendUrl)) inferredTask = 'maskrcnn';
        else inferredTask = 'unet';
      }
      setPredictionData((prev) => ({
        ...data,
        task: inferredTask,
        model_name: data.model_name || prev?.model_name || '',
        model_family: data.model_family ?? prev?.model_family,
        image: fullOverlayUrl,
        detectionData: detectionGeoJSON,
        imageMetadata: {
          bounds: data.overlay_bounds,
          crs: data.crs || 'EPSG:4326',
          width: data.width,
          height: data.height,
          total_area: data.total_area,
          count: data.count,
          average_area: data.average_area,
          prediction_geotiff_url: data.prediction_geotiff_url || null,
          class_legend: data.class_legend || null,
        },
        _backendURL: backendUrl,
        _backendType: backendType
      }));
      setPostprocessPreviewGeoJson(null);
      refreshSavedRuns();
    }
  };

  const handleImageSelected = (imageUrl) => {
    setUploadedImage(imageUrl);
    setPredictionData(null);
    setPredictionImageUrl(null);
    setRoiGeometry(null);
    setRoiDrawActive(false);
    setGeotiffBoundsSwne(null);
    setFullMaskrcnnGeoJson(null);
    setUnetThresholdGeoJson(null);
    setPostprocessPreviewGeoJson(null);
  };

  useEffect(() => {
    if (!predictionData?.run_id) return undefined;
    const { task, full_geojson_url, _backendURL, inference_threshold } = predictionData;
    // Solar ResUNet: API `inference_threshold` is the sigmoid *mask* cutoff (like the Python script),
    // not a confidence score. Do not drive the Mask R-CNN "display threshold" slider from it — that
    // slider filters `properties.confidence` (mean probability), which is usually much lower.
    if (
      typeof inference_threshold === 'number' &&
      !Number.isNaN(inference_threshold) &&
      task !== 'solar_panel'
    ) {
      setDisplayThreshold(inference_threshold);
    }
    if ((task === 'maskrcnn' || task === 'solar_panel') && full_geojson_url) {
      const url = full_geojson_url.startsWith('http')
        ? full_geojson_url
        : `${_backendURL}${full_geojson_url}`;
      let cancelled = false;
      fetch(url)
        .then((r) => r.json())
        .then((gj) => {
          if (!cancelled) setFullMaskrcnnGeoJson(gj);
        })
        .catch(() => {});
      return () => {
        cancelled = true;
      };
    }
    setFullMaskrcnnGeoJson(null);
    return undefined;
  }, [predictionData?.run_id, predictionData?.full_geojson_url, predictionData?.task]);

  useEffect(() => {
    if (predictionData?.task !== 'unet' || !predictionData?.run_id) return undefined;
    if (predictionData.confidence_bundle_saved === false) {
      setUnetThresholdGeoJson(null);
      return undefined;
    }
    const run = () => {
      fetchUnetGeojsonAtThreshold(
        predictionData.run_id,
        displayThreshold,
        predictionData._backendURL,
      )
        .then(setUnetThresholdGeoJson)
        .catch(() => setUnetThresholdGeoJson(null));
    };
    const id = window.setTimeout(run, 250);
    return () => window.clearTimeout(id);
  }, [
    predictionData?.task,
    predictionData?.run_id,
    predictionData?._backendURL,
    predictionData?.confidence_bundle_saved,
    displayThreshold,
  ]);

  const mapDetectionData = useMemo(() => {
    if (
      postprocessPreviewGeoJson &&
      postprocessPreviewGeoJson.type === 'FeatureCollection'
    ) {
      return postprocessPreviewGeoJson;
    }
    if (!predictionData) return null;
    if (predictionData.task === 'oil_spill') return null;
    if (predictionData._backendType === 'super-resolution') return predictionData.detectionData;
    if (predictionData.task === 'unet') {
      return unetThresholdGeoJson ?? predictionData.detectionData;
    }
    // Solar: mask threshold already applied server-side; `confidence` is mean probability (often << 0.2).
    if (predictionData.task === 'solar_panel' && fullMaskrcnnGeoJson?.features?.length) {
      return fullMaskrcnnGeoJson;
    }
    if (predictionData.task === 'maskrcnn' && fullMaskrcnnGeoJson?.features?.length) {
      return filterGeoJsonByConfidence(fullMaskrcnnGeoJson, displayThreshold);
    }
    return predictionData.detectionData;
  }, [
    postprocessPreviewGeoJson,
    predictionData,
    fullMaskrcnnGeoJson,
    displayThreshold,
    unetThresholdGeoJson,
  ]);

  const mapImageMetadata = useMemo(() => {
    const base = predictionData?.imageMetadata || {};
    if (!mapDetectionData || mapDetectionData.type !== 'FeatureCollection') return base;
    const n = mapDetectionData.features?.length ?? 0;
    return { ...base, count: n };
  }, [predictionData?.imageMetadata, mapDetectionData]);

  /** Oil spill: API `class_legend` + palette matching map overlay colors. */
  const oilSpillLegendEntries = useMemo(() => {
    if (!predictionData || predictionData.task !== 'oil_spill') return null;
    const lg =
      predictionData.class_legend ||
      predictionData.imageMetadata?.class_legend ||
      null;
    if (!lg || typeof lg !== 'object') return null;
    return [0, 1, 2, 3, 4].map((i) => {
      const raw = lg[String(i)] ?? lg[i];
      const labelRaw = raw != null ? String(raw) : `class_${i}`;
      const label = labelRaw.replace(/_/g, ' ');
      const color = OIL_SPILL_CLASS_COLORS_HEX[i] || '#888888';
      return {
        key: `oil-class-${i}`,
        classId: i,
        label,
        color,
        hex: color,
      };
    });
  }, [predictionData]);

  useEffect(() => {
    setPostprocessPreviewGeoJson(null);
  }, [predictionData?.run_id]);

  const buildPostprocessLabBody = useCallback(() => {
    if (!predictionData?.run_id) return null;
    const task = predictionData.task;
    const base = {
      run_id: predictionData.run_id,
      task,
      regularize_mode: ppRegularizeMode === 'off' ? null : ppRegularizeMode,
      regularize_tolerance:
        ppRegularizeMode === 'simplify' ? Number(ppTolerance) || undefined : undefined,
      iou_threshold: ppIou === '' ? undefined : Number(ppIou),
      seam_merge_gap: ppGap === '' ? undefined : Number(ppGap),
    };
    if (task === 'maskrcnn') {
      return { ...base, inference_threshold: displayThreshold, merge_touching: ppMergeTouching };
    }
    if (task === 'solar_panel') {
      const out = { ...base };
      delete out.merge_touching;
      return out;
    }
    if (task === 'unet') {
      return {
        run_id: predictionData.run_id,
        task: 'unet',
        inference_threshold: displayThreshold,
        regularize_mode: base.regularize_mode,
        regularize_tolerance: base.regularize_tolerance,
        iou_threshold: base.iou_threshold,
        seam_merge_gap: base.seam_merge_gap,
      };
    }
    return null;
  }, [
    predictionData?.run_id,
    predictionData?.task,
    ppRegularizeMode,
    ppTolerance,
    ppIou,
    ppGap,
    ppMergeTouching,
    displayThreshold,
  ]);

  const handlePostprocessPreview = useCallback(async () => {
    const body = buildPostprocessLabBody();
    if (!body || !predictionData?._backendURL) return;
    setPostprocessBusy(true);
    try {
      const data = await postprocessLabPreview(predictionData._backendURL, body);
      if (data?.geojson) setPostprocessPreviewGeoJson(data.geojson);
    } catch (e) {
      console.error('Post-process preview failed:', e);
    } finally {
      setPostprocessBusy(false);
    }
  }, [buildPostprocessLabBody, predictionData?._backendURL]);

  const handlePostprocessReset = useCallback(() => {
    setPostprocessPreviewGeoJson(null);
  }, []);

  const handlePostprocessApply = useCallback(async () => {
    const body = buildPostprocessLabBody();
    if (!body || !predictionData?._backendURL) return;
    const taskBefore = predictionData.task;
    setPostprocessBusy(true);
    try {
      const data = await postprocessLabApply(predictionData._backendURL, body);
      const gj = data?.geojson;
      const n = data?.count ?? geoJsonFeatureCount(gj);
      const total = data?.total_area;
      setPredictionData((prev) => {
        if (!prev) return prev;
        const avg =
          n > 0 && typeof total === 'number' ? total / n : prev.imageMetadata?.average_area;
        const next = {
          ...prev,
          detectionData: gj ?? prev.detectionData,
          imageMetadata: {
            ...prev.imageMetadata,
            count: n,
            ...(typeof total === 'number' ? { total_area: total, average_area: avg } : {}),
          },
        };
        if (prev.task === 'unet') {
          next.inference_threshold = displayThreshold;
        }
        return next;
      });
      if (taskBefore === 'maskrcnn' || taskBefore === 'solar_panel') {
        setFullMaskrcnnGeoJson(null);
      }
      setPostprocessPreviewGeoJson(null);
      setUnetThresholdGeoJson(null);
      refreshSavedRuns();
    } catch (e) {
      console.error('Post-process apply failed:', e);
    } finally {
      setPostprocessBusy(false);
    }
  }, [buildPostprocessLabBody, predictionData?._backendURL, predictionData?.task, displayThreshold, refreshSavedRuns]);

  const handleExport = async (format) => {
    if (!predictionData) return;

    try {
      const backendURL = predictionData._backendURL || 'http://localhost:8000/maskrcnn';
      const runId = predictionData.run_id;
      let fileData, fileName;

      if (format === 'geojson') {
        const arrayBuffer = await downloadGeoJSON(runId, backendURL);
        fileData = new Blob([arrayBuffer], { type: 'application/geo+json' });
        fileName = 'export.geojson';
      } else if (format === 'shapefile') {
        const arrayBuffer = await downloadShapefile(runId, backendURL);
        fileData = new Blob([arrayBuffer], { type: 'application/zip' });
        fileName = 'export.zip';
      } else if (format === 'geotiff') {
        const rel = predictionData.prediction_geotiff_url;
        if (!rel) return;
        const arrayBuffer = await downloadPredictionGeoTiff(rel, backendURL);
        fileData = new Blob([arrayBuffer], { type: 'image/tiff' });
        fileName = `oil_spill_classes_${runId?.slice(0, 8) || 'pred'}.tif`;
      }

      if (!fileData || !fileName) return;

      const url = window.URL.createObjectURL(fileData);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', fileName);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading file:', error);
    }
  };

  return (
    <div className="sat-page">
      {/* Full-screen map background */}
      <div className="sat-map-bg">
        <ImageViewer
          file={uploadedFile}
          fileType={fileType}
          imageData={uploadedImage}
          overlayImage={predictionImageUrl}
          detectionModelName={predictionData?.model_name}
          detectionModelFamily={predictionData?.model_family}
          segmentationOverlayUrl={
            predictionData?.task === 'oil_spill' && predictionImageUrl ? predictionImageUrl : null
          }
          segmentationOverlayBounds={
            predictionData?.task === 'oil_spill' ? predictionData?.imageMetadata?.bounds : null
          }
          oilSpillLegendEntries={oilSpillLegendEntries}
          detectionData={mapDetectionData ?? predictionData?.detectionData}
          imageMetadata={mapImageMetadata}
          roiDrawActive={roiDrawActive}
          onRoiDrawActiveChange={setRoiDrawActive}
          roiGeometry={roiGeometry}
          onRoiGeometryChange={handleRoiGeometryChange}
          onRasterMapBoundsSwne={handleRasterMapBoundsSwne}
        />
      </div>

      {/* Floating control panel */}
      <div className="sat-controls-panel">
        <ImageUploader
          onUploadSuccess={handleUploadSuccess}
          onImageSelected={handleImageSelected}
          setFileType={setFileType}
          setUploadedFile={setUploadedFile}
          roiGeometry={roiGeometry}
          roiFullBoundsSwne={geotiffBoundsSwne}
          onStreamDetectionEvent={handleStreamDetectionEvent}
        />
        <div className="sat-side-card">
          <div className="sat-side-card__title">Saved Predictions</div>
          <select
            value={selectedSavedRunKey}
            onChange={(e) => setSelectedSavedRunKey(e.target.value)}
            className="sat-select"
            style={{
              width: '100%',
              padding: '8px',
              fontSize: 12,
            }}
          >
            <option value="">{savedRunsLoading ? 'Loading...' : 'Select a saved run'}</option>
            {savedRuns.map((r) => (
              <option
                key={`${r._backendURL}-${r.task}-${r.run_id}`}
                value={`${r._backendURL}|${r.task}|${r.run_id}`}
              >
                [{r.task}] {r.run_id.slice(0, 8)} · {r.model_name || 'model'} · {r.created_at || ''}
              </option>
            ))}
          </select>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button
              type="button"
              onClick={handleLoadSavedRun}
              disabled={!selectedSavedRunKey}
              style={{
                flex: 1,
                borderRadius: 8,
                border: '1px solid rgba(206,17,38,0.35)',
                background: 'rgba(26,22,24,0.94)',
                color: '#fff',
                padding: '7px 10px',
                fontSize: 12,
                cursor: selectedSavedRunKey ? 'pointer' : 'not-allowed',
              }}
            >
              Load
            </button>
            <button
              type="button"
              onClick={refreshSavedRuns}
              style={{
                borderRadius: 8,
                border: '1px solid rgba(206,17,38,0.2)',
                background: 'rgba(255,255,255,0.96)',
                color: '#475569',
                padding: '7px 10px',
                fontSize: 12,
              }}
            >
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Floating export panel */}
      {predictionData && (
        <div className="sat-export-panel">
          {uiConfig.show_detection_threshold &&
            predictionData._backendType === 'detection' &&
            (predictionData.task === 'maskrcnn' ||
              predictionData.task === 'solar_panel' ||
              predictionData.task === 'unet') && (
            <div
              style={{
                marginBottom: 10,
                padding: '10px 12px',
                background: 'rgba(255,255,255,0.98)',
                borderRadius: 10,
                border: '1px solid rgba(206,17,38,0.18)',
                minWidth: 220,
              }}
            >
              <div style={{ fontSize: 11, color: 'var(--geoai-od-on-light-muted)', marginBottom: 6 }}>
                {predictionData.task === 'solar_panel'
                  ? 'Solar mask threshold (set at run)'
                  : 'Display threshold'}
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={displayThreshold}
                onChange={(e) => setDisplayThreshold(Number(e.target.value))}
                disabled={
                  predictionData.task === 'solar_panel' ||
                  (predictionData.task === 'unet' && predictionData.confidence_bundle_saved === false)
                }
                style={{ width: '100%' }}
              />
              <div style={{ fontSize: 12, color: 'var(--geoai-od-on-light-text)', marginTop: 4 }}>
                {predictionData.task === 'solar_panel'
                  ? typeof predictionData.inference_threshold === 'number'
                    ? predictionData.inference_threshold.toFixed(2)
                    : '—'
                  : displayThreshold.toFixed(2)}
                {predictionData.task === 'unet' && predictionData.confidence_bundle_saved === false && (
                  <span style={{ color: '#f87171', marginLeft: 8 }}>(saved grid unavailable)</span>
                )}
              </div>
            </div>
          )}
          {postprocessLabEnabled &&
            predictionData._backendType === 'detection' &&
            predictionData.run_id &&
            (predictionData.task === 'maskrcnn' ||
              predictionData.task === 'solar_panel' ||
              predictionData.task === 'unet') && (
            <div
              style={{
                marginBottom: 10,
                padding: '10px 12px',
                background: 'rgba(255,255,255,0.98)',
                borderRadius: 10,
                border: '1px solid rgba(206,17,38,0.18)',
                minWidth: 220,
              }}
            >
              <div style={{ fontSize: 11, color: 'var(--geoai-od-on-light-muted)', marginBottom: 6 }}>
                Post-process lab (preview / apply)
              </div>
              <div style={{ fontSize: 10, color: 'var(--geoai-od-on-light-muted)', marginBottom: 8 }}>
                Tolerance uses CRS units (e.g. metres on projected rasters). Requires ENABLE_POSTPROCESS_LAB on
                the API.
              </div>
              <label style={{ fontSize: 11, color: 'var(--geoai-od-on-light-muted)', display: 'block', marginBottom: 4 }}>
                Regularize mode
              </label>
              <select
                value={ppRegularizeMode}
                onChange={(e) => setPpRegularizeMode(e.target.value)}
                disabled={
                  postprocessBusy ||
                  (predictionData.task === 'unet' && predictionData.confidence_bundle_saved === false)
                }
                style={{
                  width: '100%',
                  marginBottom: 8,
                  background: 'rgba(255,255,255,0.96)',
                  color: '#334155',
                  border: '1px solid rgba(148,163,184,0.3)',
                  borderRadius: 6,
                  padding: '6px',
                  fontSize: 12,
                }}
              >
                <option value="off">off</option>
                <option value="simplify">simplify</option>
                <option value="oriented_rectangle">oriented_rectangle</option>
                <option value="axis_aligned_envelope">axis_aligned_envelope</option>
              </select>
              {ppRegularizeMode === 'simplify' && (
                <label style={{ fontSize: 11, color: 'var(--geoai-od-on-light-muted)', display: 'block', marginBottom: 4 }}>
                  Tolerance
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    value={ppTolerance}
                    onChange={(e) => setPpTolerance(Number(e.target.value))}
                    disabled={postprocessBusy}
                    style={{
                      width: '100%',
                      marginTop: 4,
                      padding: 6,
                      borderRadius: 6,
                      border: '1px solid rgba(148,163,184,0.3)',
                      background: 'rgba(255,255,255,0.96)',
                      color: '#334155',
                    }}
                  />
                </label>
              )}
              {predictionData.task === 'maskrcnn' && (
                <label style={{ fontSize: 11, color: 'var(--geoai-od-on-light-muted)', display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                  <input
                    type="checkbox"
                    checked={ppMergeTouching}
                    onChange={(e) => setPpMergeTouching(e.target.checked)}
                    disabled={postprocessBusy}
                  />
                  Merge touching (legacy union)
                </label>
              )}
              <button
                type="button"
                onClick={() => setPpAdvancedOpen((o) => !o)}
                style={{
                  marginTop: 8,
                  fontSize: 11,
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--geoai-od-accent)',
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                {ppAdvancedOpen ? '▼' : '▶'} Advanced (IoU / seam gap)
              </button>
              {ppAdvancedOpen && (
                <div style={{ marginTop: 8 }}>
                  <label style={{ fontSize: 11, color: 'var(--geoai-od-on-light-muted)', display: 'block' }}>
                    IoU dedupe (0 = off)
                    <input
                      type="text"
                      placeholder="default"
                      value={ppIou}
                      onChange={(e) => setPpIou(e.target.value)}
                      disabled={postprocessBusy}
                      style={{ width: '100%', marginTop: 4, padding: 6, borderRadius: 6 }}
                    />
                  </label>
                  <label style={{ fontSize: 11, color: 'var(--geoai-od-on-light-muted)', display: 'block', marginTop: 6 }}>
                    Seam merge gap (empty = auto)
                    <input
                      type="text"
                      placeholder="auto"
                      value={ppGap}
                      onChange={(e) => setPpGap(e.target.value)}
                      disabled={postprocessBusy}
                      style={{ width: '100%', marginTop: 4, padding: 6, borderRadius: 6 }}
                    />
                  </label>
                </div>
              )}
              {predictionData.task === 'unet' && predictionData.confidence_bundle_saved === false && (
                <div style={{ fontSize: 11, color: '#f87171', marginTop: 8 }}>
                  Saved confidence grid unavailable — lab preview/apply disabled.
                </div>
              )}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
                <button
                  type="button"
                  onClick={handlePostprocessPreview}
                  disabled={
                    postprocessBusy ||
                    (predictionData.task === 'unet' && predictionData.confidence_bundle_saved === false)
                  }
                  style={{
                    flex: 1,
                    minWidth: 72,
                    borderRadius: 8,
                    border: '1px solid rgba(206,17,38,0.35)',
                    background: 'rgba(26,22,24,0.94)',
                    color: '#fff',
                    padding: '7px 8px',
                    fontSize: 12,
                    cursor: postprocessBusy ? 'wait' : 'pointer',
                  }}
                >
                  Preview
                </button>
                <button
                  type="button"
                  onClick={handlePostprocessReset}
                  disabled={postprocessBusy || !postprocessPreviewGeoJson}
                  style={{
                    flex: 1,
                    minWidth: 72,
                    borderRadius: 8,
                    border: '1px solid rgba(206,17,38,0.2)',
                    background: 'rgba(255,255,255,0.96)',
                    color: '#475569',
                    padding: '7px 8px',
                    fontSize: 12,
                  }}
                >
                  Reset
                </button>
                <button
                  type="button"
                  onClick={handlePostprocessApply}
                  disabled={
                    postprocessBusy ||
                    (predictionData.task === 'unet' && predictionData.confidence_bundle_saved === false)
                  }
                  style={{
                    flex: '1 1 100%',
                    borderRadius: 8,
                    border: '1px solid rgba(206,17,38,0.4)',
                    background: 'rgba(206,17,38,0.1)',
                    color: 'var(--geoai-od-accent)',
                    padding: '7px 8px',
                    fontSize: 12,
                    cursor: postprocessBusy ? 'wait' : 'pointer',
                  }}
                >
                  Apply to saved outputs
                </button>
              </div>
            </div>
          )}
          <ExportButton
            onExport={handleExport}
            showGeoTiffOnly={predictionData?.task === 'oil_spill'}
          />
        </div>
      )}
    </div>
  );
};

export default SatelliteImage;