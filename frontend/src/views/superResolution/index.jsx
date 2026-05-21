import React, { useState, useEffect } from 'react';
import UiScopedView from '../../components/UiScopedView';
import ImageUploader from './components/ImageUploader';
import ImageViewer from './components/ImageViewer';
import ExportButton from './components/ExportButton';
import { downloadGeoJSON, downloadShapefile } from './services/api';
import { Row, Col, Container } from 'react-bootstrap';
import 'leaflet/dist/leaflet.css';

const SuperResolutionInner = () => {
  const [predictionData, setPredictionData] = useState(null);
  const [uploadedImage, setUploadedImage] = useState(null);
  const [predictionImageUrl, setPredictionImageUrl] = useState(null);
  const [fileType, setFileType] = useState(null);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [currentBackendUrl, setCurrentBackendUrl] = useState('http://localhost:8000/maskrcnn');

  useEffect(() => {
    return () => {
      if (uploadedImage) {
        URL.revokeObjectURL(uploadedImage);
      }
      if (predictionImageUrl) {
        URL.revokeObjectURL(predictionImageUrl);
      }
    };
  }, [uploadedImage, predictionImageUrl]);

  const handleUploadSuccess = async (data) => {
    console.log("✅ Upload success data:", data);
    // DEBUG: Check bounds format
    console.log("🔍 Raw overlay_bounds:", data.overlay_bounds);
    console.log("🔍 Is Array?", Array.isArray(data.overlay_bounds));
    console.log("🔍 Bounds length:", data.overlay_bounds?.length);
    console.log("🔍 Bounds[0]:", data.overlay_bounds?.[0]);
    console.log("🔍 Bounds[1]:", data.overlay_bounds?.[1]);

    const backendUrl = data._backendURL || 'http://localhost:8000/maskrcnn';
    const backendType = data._backendType || 'detection';

    console.log("🔧 Backend type:", backendType);
    console.log("🔧 Using backend URL:", backendUrl);

    if (backendType === 'super-resolution') {
      // ========== SUPER-RESOLUTION WORKFLOW ==========
      console.log("🎨 Processing super-resolution result");

      const overlayUrl = data.overlay_url;
      const fullOverlayUrl = overlayUrl?.startsWith('http')
        ? overlayUrl
        : `${backendUrl}${overlayUrl}`;

      setPredictionImageUrl(fullOverlayUrl);

      // Extract bounds - IMPORTANT: Access the array properly
      const bounds = data.overlay_bounds;
      console.log("🗺️ SR overlay bounds:", bounds);
      console.log("🗺️ Bounds type:", Array.isArray(bounds) ? "Array" : typeof bounds);

      // Validate bounds format
      if (!bounds || !Array.isArray(bounds) || bounds.length !== 2) {
        console.error("❌ Invalid bounds format:", bounds);
        alert("Error: Invalid geographic bounds received from server");
        return;
      }

      setPredictionData({
        ...data,
        image: fullOverlayUrl,
        detectionData: null,  // No detections for SR
        imageMetadata: {
          bounds: bounds,  // [[south, west], [north, east]]
          crs: data.crs || "EPSG:4326",
          width: data.output_width,
          height: data.output_height,
          // SR-specific metadata
          original_width: data.original_width,
          original_height: data.original_height,
          scale_factor: data.scale_factor,
          psnr_improvement: data.psnr_improvement,
          ssim_improvement: data.ssim_improvement
        },
        _backendURL: backendUrl,
        _backendType: backendType
      });

      console.log("✅ Super-resolution data set:", {
        overlayUrl: fullOverlayUrl,
        bounds: bounds,
        crs: data.crs,
        dimensions: `${data.output_width}×${data.output_height}`
      });

    } else {
      // ========== DETECTION WORKFLOW ==========
      console.log("🔍 Processing detection result");

      const overlayUrl = data.overlay_url;
      const fullOverlayUrl = overlayUrl?.startsWith('http')
        ? overlayUrl
        : `${backendUrl}${overlayUrl}`;

      setPredictionImageUrl(fullOverlayUrl);

      // Handle GeoJSON
      let detectionGeoJSON = null;
      if (data.geojson_url) {
        const geoJsonUrl = data.geojson_url.startsWith('http')
          ? data.geojson_url
          : `${backendUrl}${data.geojson_url}`;

        console.log("📥 Fetching GeoJSON from:", geoJsonUrl);

        try {
          const response = await fetch(geoJsonUrl);
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          const geoJson = await response.json();
          console.log("✅ GeoJSON loaded successfully:", geoJson);
          detectionGeoJSON = geoJson;
        } catch (err) {
          console.error("❌ Failed to load GeoJSON:", err);
          detectionGeoJSON = geoJsonUrl;
        }
      }

      const bounds = data.overlay_bounds;
      console.log("🗺️ Detection overlay bounds:", bounds);

      setPredictionData({
        ...data,
        image: fullOverlayUrl,
        detectionData: detectionGeoJSON,
        imageMetadata: {
          bounds: bounds,
          crs: data.crs || "EPSG:4326",
          width: data.width,
          height: data.height,
          total_area: data.total_area,
          count: data.count,
          average_area: data.average_area
        },
        _backendURL: backendUrl,
        _backendType: backendType
      });

      console.log("✅ Detection data set:", {
        overlayUrl: fullOverlayUrl,
        bounds: bounds,
        crs: data.crs,
        hasDetections: !!detectionGeoJSON
      });
    }
  };


  const handleImageSelected = (imageUrl) => {
    setUploadedImage(imageUrl);
    setPredictionData(null);
    setPredictionImageUrl(null);
  };

  const handleExport = async (format) => {
    if (!predictionData) {
      alert('No data available to export!');
      return;
    }

    try {
      const backendURL = predictionData._backendURL || 'http://localhost:8000/maskrcnn';
      const runId = predictionData.run_id;

      let fileData;
      let fileName;

      if (format === 'geojson') {
        const arrayBuffer = await downloadGeoJSON(runId, backendURL);
        fileData = new Blob([arrayBuffer], { type: 'application/geo+json' });
        fileName = 'export.geojson';
      } else if (format === 'shapefile') {
        const arrayBuffer = await downloadShapefile(runId, backendURL);
        fileData = new Blob([arrayBuffer], { type: 'application/zip' });
        fileName = 'export.zip';
      }

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
      alert('Failed to download file.');
    }
  };

  return (
    <Container>
      <div className="super-resolution-page">
        <h2 className="mb-4">Super Resolution</h2>
        <Row>
          <Col lg={3}>
            <ImageUploader
              onUploadSuccess={handleUploadSuccess}
              onImageSelected={handleImageSelected}
              setFileType={setFileType}
              setUploadedFile={setUploadedFile}
            />
          </Col>
          <Col lg={9}>
            <div style={{ height: '75vh', overflow: 'hidden' }}>
              <ImageViewer
                file={uploadedFile}
                fileType={fileType}
                imageData={uploadedImage}
                overlayImage={predictionImageUrl}
                detectionData={predictionData?.detectionData}
                imageMetadata={predictionData?.imageMetadata}
              />
            </div>
          </Col>
        </Row>
        <div>
          <ExportButton onExport={handleExport} />
        </div>
      </div>
    </Container>
  );
};

export default function SuperResolution() {
  return (
    <UiScopedView flag="show_super_resolution">
      <SuperResolutionInner />
    </UiScopedView>
  );
}