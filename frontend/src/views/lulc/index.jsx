import React, { useState, useEffect, useCallback } from 'react';
import UiScopedView from '../../components/UiScopedView';
import ImageUploader from './components/ImageUploader';
import ImageViewer from './components/ImageViewer';
import ExportButton from './components/ExportButton';
import SwipeComparison from './components/SwipeComparison';
import LULCTiffCompareMaps from './components/LULCTiffCompareMaps';
import LULCLegendPanel from './components/LULCLegendPanel';
import {
  downloadGeoTIFF,
  fetchPredictions,
  fetchPrediction,
  deletePrediction,
  deleteAllPredictions,
} from './services/api';
import { Row, Col, Container, Card } from 'react-bootstrap';
import 'leaflet/dist/leaflet.css';
import './lulc.css';

const LandCoverClassificationInner = () => {
  const [classificationData, setClassificationData] = useState(null);
  const [uploadedImage, setUploadedImage] = useState(null);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [showSwipe, setShowSwipe] = useState(false);
  const [roiGeometry, setRoiGeometry] = useState(null);
  const [roiDrawActive, setRoiDrawActive] = useState(false);
  const [geotiffBoundsSwne, setGeotiffBoundsSwne] = useState(null);
  const [streamingOverlayUrl, setStreamingOverlayUrl] = useState(null);
  const [streamingBounds, setStreamingBounds] = useState(null);
  const [isClassificationStreaming, setIsClassificationStreaming] = useState(false);
  const [savedPredictions, setSavedPredictions] = useState([]);
  const [savedPredLoading, setSavedPredLoading] = useState(false);
  const [selectedPrevId, setSelectedPrevId] = useState('');
  const [deleteBusy, setDeleteBusy] = useState(false);

  const refreshSavedPredictions = useCallback(async () => {
    setSavedPredLoading(true);
    try {
      const d = await fetchPredictions();
      setSavedPredictions(d.predictions || []);
    } catch {
      setSavedPredictions([]);
    } finally {
      setSavedPredLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshSavedPredictions();
  }, [refreshSavedPredictions]);

  const handleStreamBegin = useCallback(() => {
    setStreamingOverlayUrl(null);
    setStreamingBounds(null);
    setIsClassificationStreaming(true);
  }, []);

  const handleStreamStart = useCallback((e) => {
    if (e.bounds && Array.isArray(e.bounds) && e.bounds.length === 4) {
      setStreamingBounds(e.bounds);
    }
  }, []);

  const handleStreamProgress = useCallback((e) => {
    if (e.imageDataUrl) {
      setStreamingOverlayUrl(e.imageDataUrl);
    }
  }, []);

  const handleStreamEnd = useCallback(() => {
    setIsClassificationStreaming(false);
    setStreamingOverlayUrl(null);
    setStreamingBounds(null);
  }, []);

  useEffect(() => {
    return () => {
      if (uploadedImage) {
        URL.revokeObjectURL(uploadedImage);
      }
    };
  }, [uploadedImage]);

  const handleRasterMapBoundsSwne = useCallback((swne) => {
    setGeotiffBoundsSwne(swne && swne.length === 4 ? swne : null);
  }, []);

  const handleUploadSuccess = (data) => {
    setClassificationData(data);
    refreshSavedPredictions();
  };

  const handleLoadSavedPrediction = async () => {
    if (!selectedPrevId) return;
    try {
      const data = await fetchPrediction(selectedPrevId);
      setClassificationData(data);
    } catch (err) {
      console.error(err);
      alert('Could not load that saved prediction.');
    }
  };

  const handleDeleteSelectedPrediction = async () => {
    if (!selectedPrevId) return;
    const id = selectedPrevId;
    if (!window.confirm('Delete this saved land-cover run from the server? This cannot be undone.')) return;
    setDeleteBusy(true);
    try {
      await deletePrediction(id);
      setSelectedPrevId('');
      if (classificationData?.prediction_id === id) {
        setClassificationData(null);
      }
      await refreshSavedPredictions();
    } catch (e) {
      alert(e?.response?.data?.error || e.message || 'Delete failed');
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleDeleteAllPredictions = async () => {
    if (
      !window.confirm(
        'Delete ALL saved land-cover runs on this server? This cannot be undone.'
      )
    ) {
      return;
    }
    setDeleteBusy(true);
    try {
      await deleteAllPredictions();
      setSelectedPrevId('');
      setClassificationData(null);
      await refreshSavedPredictions();
    } catch (e) {
      alert(e?.response?.data?.error || e.message || 'Delete all failed');
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleImageSelected = (imageUrl) => {
    setUploadedImage(imageUrl);
    setClassificationData(null);
    setShowSwipe(false);
    setRoiGeometry(null);
    setRoiDrawActive(false);
    setGeotiffBoundsSwne(null);
    setStreamingOverlayUrl(null);
    setStreamingBounds(null);
    setIsClassificationStreaming(false);
  };

  const handleRoiGeometryChange = useCallback((geom) => {
    setRoiGeometry(geom);
  }, []);

  const handleExport = async (format) => {
    if (!classificationData) {
      alert('No classification data available to export!');
      return;
    }

    try {
      const pngB64 =
        classificationData.prediction_image_b64 || classificationData.image_b64;
      if (format === 'png' && pngB64) {
        const byteCharacters = atob(pngB64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: 'image/png' });

        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `lulc_classification.png`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      } else if (format === 'geotiff' && classificationData.prediction_id) {
        const blob = await downloadGeoTIFF(classificationData.prediction_id);
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `lulc_classification.tif`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Error downloading file:', error);
      alert('Failed to download file.');
    }
  };

  const overlayImageUrl =
    classificationData?.prediction_image_b64
      ? `data:image/png;base64,${classificationData.prediction_image_b64}`
      : classificationData?.image_b64
        ? `data:image/png;base64,${classificationData.image_b64}`
        : null;

  const baseImageUrl = classificationData?.base_image_b64
    ? `data:image/png;base64,${classificationData.base_image_b64}`
    : uploadedImage;

  const isTiff =
    uploadedFile &&
    (uploadedFile.type === 'image/tiff' ||
      uploadedFile.name?.toLowerCase().endsWith('.tif') ||
      uploadedFile.name?.toLowerCase().endsWith('.tiff'));

  const canMapCompare =
    isTiff && classificationData?.bounds && Array.isArray(classificationData.bounds) && classificationData.bounds.length >= 4;

  const hasResult = Boolean(classificationData && overlayImageUrl && baseImageUrl);

  return (
    <Container fluid className="lulc-page px-3 px-md-4 py-3">
      <header className="lulc-page-header mb-3 mb-md-4">
        <h1>Land use / land cover classification</h1>
        <p className="lulc-page-subtitle">
          Upload GeoTIFF, PNG, or JPEG. Results use patch-based SigLIP labels; GeoTIFFs can be viewed on an interactive map.
        </p>
      </header>

      <Row className="g-3 g-lg-4 align-items-stretch">
        <Col lg={4} xl={3}>
          <Card className="lulc-sidebar-card h-100">
            <Card.Body className="d-flex flex-column">
              <ImageUploader
                onUploadSuccess={handleUploadSuccess}
                onImageSelected={handleImageSelected}
                setUploadedFile={setUploadedFile}
                roiGeometry={roiGeometry}
                geotiffSelected={isTiff}
                roiFullBoundsSwne={geotiffBoundsSwne}
                onStreamBegin={handleStreamBegin}
                onStreamStart={handleStreamStart}
                onStreamProgress={handleStreamProgress}
                onStreamEnd={handleStreamEnd}
              />

              <div className="mt-3 pt-3 border-top border-secondary border-opacity-25">
                <div className="lulc-form-label mb-1">Saved predictions</div>
                <p className="lulc-hint mb-2" style={{ fontSize: 12 }}>
                  Reload a past land-cover result (and any building outlines stored with it).
                </p>
                <div className="d-flex gap-2 align-items-stretch flex-wrap">
                  <select
                    className="lulc-select flex-grow-1"
                    style={{ minWidth: 0 }}
                    value={selectedPrevId}
                    onChange={(e) => setSelectedPrevId(e.target.value)}
                    disabled={savedPredLoading || deleteBusy}
                  >
                    <option value="">{savedPredLoading ? 'Loading…' : 'Select saved run…'}</option>
                    {savedPredictions.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.id.slice(0, 18)}… {p.top_class || ''}{p.has_buildings ? ' · buildings' : ''}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="lulc-btn-secondary"
                    disabled={!selectedPrevId || deleteBusy}
                    onClick={handleLoadSavedPrediction}
                  >
                    Load
                  </button>
                  <button
                    type="button"
                    className="lulc-btn-secondary text-danger border-danger"
                    disabled={!selectedPrevId || deleteBusy}
                    onClick={handleDeleteSelectedPrediction}
                  >
                    Delete
                  </button>
                  <button type="button" className="lulc-btn-secondary" disabled={deleteBusy} onClick={refreshSavedPredictions}>
                    Refresh
                  </button>
                </div>
                <button
                  type="button"
                  className="lulc-btn-secondary w-100 mt-2 text-danger border-danger"
                  disabled={deleteBusy || savedPredictions.length === 0}
                  onClick={handleDeleteAllPredictions}
                >
                  {deleteBusy ? 'Working…' : 'Delete all saved runs'}
                </button>
              </div>

              {classificationData?.prediction_id && (
                <div className="mt-2 p-2 rounded small" style={{ background: 'rgba(15,23,42,0.45)', fontSize: 12 }}>
                  <span className="text-secondary">Prediction ID (for satellite detection link): </span>
                  <code className="user-select-all">{classificationData.prediction_id}</code>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-light ms-2 py-0"
                    onClick={() =>
                      navigator.clipboard.writeText(classificationData.prediction_id).catch(() => {})
                    }
                  >
                    Copy
                  </button>
                </div>
              )}

              {hasResult && (
                <button
                  type="button"
                  onClick={() => setShowSwipe(!showSwipe)}
                  className={`lulc-btn-secondary ${showSwipe ? 'lulc-btn-active' : ''}`}
                >
                  {showSwipe
                    ? 'Single map view'
                    : canMapCompare
                      ? 'Compare on map (side by side)'
                      : 'Before / after swipe'}
                </button>
              )}

              {classificationData && (
                <>
                  <div className="lulc-legend-section">
                    <LULCLegendPanel placement="sidebar" classificationData={classificationData} />
                  </div>
                  <div className="mt-2">
                    <ExportButton
                      onExport={handleExport}
                      geotiffAvailable={classificationData?.geotiff_available}
                      disabled={
                        !classificationData?.image_b64 &&
                        !classificationData?.prediction_image_b64
                      }
                    />
                  </div>
                </>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col lg={8} xl={9}>
          <div className="lulc-map-shell">
            {showSwipe && overlayImageUrl && baseImageUrl && canMapCompare ? (
              <LULCTiffCompareMaps
                tiffBlob={uploadedFile}
                overlayImageUrl={overlayImageUrl}
                bounds={classificationData.bounds}
              />
            ) : showSwipe && overlayImageUrl && baseImageUrl ? (
              <SwipeComparison
                beforeImage={overlayImageUrl}
                afterImage={baseImageUrl}
                beforeLabel="Classified"
                afterLabel="Original"
              />
            ) : (
              <ImageViewer
                file={uploadedFile}
                imageData={uploadedImage}
                classificationData={classificationData}
                streamingOverlayUrl={streamingOverlayUrl}
                streamingBounds={streamingBounds}
                isClassificationStreaming={isClassificationStreaming}
                roiDrawActive={roiDrawActive}
                onRoiDrawActiveChange={setRoiDrawActive}
                roiGeometry={roiGeometry}
                onRoiGeometryChange={handleRoiGeometryChange}
                onRasterMapBoundsSwne={handleRasterMapBoundsSwne}
              />
            )}
          </div>
        </Col>
      </Row>
    </Container>
  );
};

export default function LandCoverClassification() {
  return (
    <UiScopedView flag="show_lulc">
      <LandCoverClassificationInner />
    </UiScopedView>
  );
}
