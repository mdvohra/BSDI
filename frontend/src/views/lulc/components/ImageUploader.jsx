import React, { useState } from 'react';
import { uploadImageStreaming } from '../services/api';
import ProgressTracker from './ProgressTracker';

const ImageUploader = ({
  onUploadSuccess,
  onImageSelected,
  setUploadedFile,
  roiGeometry,
  geotiffSelected,
  roiFullBoundsSwne,
  onStreamBegin,
  onStreamStart,
  onStreamProgress,
  onStreamEnd,
}) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [segMode, setSegMode] = useState('fast');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [streamProgress, setStreamProgress] = useState(0);
  const [progressImage, setProgressImage] = useState(null);
  const [activeXhr, setActiveXhr] = useState(null);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setSelectedFile(file);
    setUploadedFile(file);
    const imageUrl = URL.createObjectURL(file);
    onImageSelected(imageUrl);
    setError('');
  };

  const handleUpload = (withPreview) => {
    if (!selectedFile) {
      setError('Please select an image file.');
      return;
    }

    setUploading(true);
    setError('');
    setStreamProgress(0);
    setProgressImage(null);
    onStreamBegin?.();

    const formData = new FormData();
    formData.append('image', selectedFile);
    formData.append('stream_patch_interval', '5');
    formData.append('stream_preview', withPreview ? '1' : '0');
    if (geotiffSelected && roiGeometry && roiGeometry.type === 'Polygon') {
      formData.append('roi_geojson', JSON.stringify(roiGeometry));
      if (
        Array.isArray(roiFullBoundsSwne) &&
        roiFullBoundsSwne.length === 4 &&
        roiFullBoundsSwne.every((n) => typeof n === 'number' && Number.isFinite(n))
      ) {
        formData.append('roi_full_bounds_swne', JSON.stringify(roiFullBoundsSwne));
      }
    }

    const xhr = uploadImageStreaming(
      formData,
      segMode,
      (progressEvent) => {
        if (progressEvent.type === 'start') {
          onStreamStart?.(progressEvent);
        }
        if (progressEvent.progress !== undefined) {
          setStreamProgress(Math.round(progressEvent.progress * 100));
        }
        if (progressEvent.image_b64) {
          const url = `data:image/png;base64,${progressEvent.image_b64}`;
          setProgressImage(url);
          onStreamProgress?.({ ...progressEvent, imageDataUrl: url });
        }
      },
      (doneEvent) => {
        setUploading(false);
        setStreamProgress(100);
        onStreamEnd?.();
        onUploadSuccess(doneEvent);
      },
      (errorMsg) => {
        setUploading(false);
        onStreamEnd?.();
        setError(`Classification failed: ${errorMsg}`);
      }
    );
    setActiveXhr(xhr);
  };

  const handleCancel = () => {
    if (activeXhr) {
      activeXhr.abort();
      setActiveXhr(null);
    }
    setUploading(false);
    setStreamProgress(0);
    setProgressImage(null);
    onStreamEnd?.();
  };

  return (
    <div className="lulc-uploader">
      <div className="lulc-section-label">Input</div>

      <div className="lulc-file-picker">
        <label className="lulc-file-picker-label">
          <input
            type="file"
            accept="image/*,.tif,.tiff"
            onChange={handleFileChange}
            disabled={uploading}
          />
          <span className="lulc-file-trigger">Choose file</span>
          <span className="lulc-file-name">{selectedFile ? selectedFile.name : 'No file selected'}</span>
        </label>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <label htmlFor="seg-mode-select" className="lulc-form-label">
          Segmentation mode
        </label>
        <select
          id="seg-mode-select"
          value={segMode}
          onChange={(e) => setSegMode(e.target.value)}
          disabled={uploading}
          className="lulc-select"
        >
          <option value="fast">Fast — larger steps, quicker</option>
          <option value="pixel">Pixel — finer steps, slower</option>
        </select>
        <p className="lulc-hint">
          {segMode === 'fast'
            ? 'Fast mode: ~50% overlap stride between spatial patches (backend PATCH_SIZE).'
            : '1 px stride: slow but smoother overlay.'}
        </p>
      </div>

      <div className="lulc-info-callout">
        <div className="lulc-info-callout-title">15 land cover classes</div>
        <p className="lulc-info-callout-text">
          Woodland, cropland, water, built-up, grassland, and more — see summary after classification.
        </p>
      </div>

      {geotiffSelected && roiGeometry?.type === 'Polygon' && (
        <p className="lulc-roi-hint">
          Classification will run only inside the polygon drawn on the map.
        </p>
      )}

      {uploading ? (
        <button
          type="button"
          onClick={handleCancel}
          className="lulc-btn-primary lulc-btn-danger"
        >
          Cancel classification
        </button>
      ) : (
        <div className="d-flex gap-2">
          <button
            type="button"
            onClick={() => handleUpload(true)}
            disabled={!selectedFile}
            className="lulc-btn-primary flex-grow-1"
          >
            Run with preview
          </button>
          <button
            type="button"
            onClick={() => handleUpload(false)}
            disabled={!selectedFile}
            className="lulc-btn-secondary flex-grow-1"
          >
            Run without preview
          </button>
        </div>
      )}

      {uploading && <ProgressTracker progress={streamProgress} progressImage={progressImage} />}

      {error && <div className="lulc-error">{error}</div>}
    </div>
  );
};

export default ImageUploader;
