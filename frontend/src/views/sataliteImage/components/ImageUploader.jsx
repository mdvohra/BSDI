import React, { useState, useEffect } from 'react';
import { uploadImage, fetchModels, fetchModels1, getDemoOrthoSampleUrl, postPredictStream } from '../services/api';
import axios from 'axios';
import ProgressTracker from './ProgressTracker';
import { useLocation } from "react-router-dom";
import { useUiConfig } from '../../../contexts/UiConfigContext';

function modelIsSuperResolution(model) {
  if (!model?.name) return false;
  const lowerName = model.name.toLowerCase();
  return (
    lowerName.includes('srgan') ||
    lowerName.includes('super') ||
    lowerName.includes('resolution')
  );
}

function isGeotiffFile(file) {
  if (!file) return false;
  const n = file.name || '';
  if (/\.(tif|tiff)$/i.test(n)) return true;
  const t = (file.type || '').toLowerCase();
  return t === 'image/tiff' || t === 'image/x-tiff';
}

/** Esri export served via /maskrcnn (EMD + FPN), from GET /models `models_detailed`. */
function isEsriDetectionModel(model) {
  if (!model) return false;
  const fam = String(model.modelFamily || model.model_family || '').toLowerCase();
  const kind = String(model.modelKind || model.model_kind || '').toLowerCase();
  return fam === 'esri' || kind === 'esri_dlpk';
}

/** ResUNet-A solar segmentation via /maskrcnn, from GET /models `models_detailed`. */
function isSolarPanelModel(model) {
  if (!model) return false;
  const fam = String(model.modelFamily || model.model_family || '').toLowerCase();
  const kind = String(model.modelKind || model.model_kind || '').toLowerCase();
  if (fam === 'solar_panel' || kind === 'solar_panel') return true;
  const nameLower = String(model.name || '').toLowerCase();
  return nameLower.includes('solar') || nameLower.includes('solarpanel');
}

function modelUiKindLabel(model) {
  if (!model) return '';
  if (isEsriDetectionModel(model)) return 'Esri';
  if (isSolarPanelModel(model)) return 'Solar panel';
  return model.backend || '';
}

const ImageUploader = ({
  onUploadSuccess,
  onImageSelected,
  setFileType,
  setUploadedFile,
  roiGeometry,
  roiFullBoundsSwne,
  onStreamDetectionEvent,
}) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState(null);
  const [threshold, setThreshold] = useState(0.3);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(0);
  const [collapsed, setCollapsed] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [progressData, setProgressData] = useState({
    progress: 0, phase: 'idle', current_step: '',
    total_chips: 0, processed_chips: 0, eta_seconds: 0, status: 'idle'
  });
  const [usingSseStream, setUsingSseStream] = useState(false);
  const [lulcPredictionId, setLulcPredictionId] = useState('');
  const location = useLocation();
  const { uiConfig, loading: uiCfgLoading } = useUiConfig();

  const getModelType = (model) => {
    if (!model) return 'detection';
    if (modelIsSuperResolution(model)) {
      return 'super-resolution';
    }
    return 'detection';
  };

  const modelType = getModelType(selectedModel);
  const isSuperResolution = modelType === 'super-resolution';
  const isUnetBackend =
    !isSuperResolution &&
    ((((selectedModel?.baseURL || '').toLowerCase().includes('/unet') ||
      (selectedModel?.baseURL || '').toLowerCase().includes('unet')) ||
      (selectedModel?.backend || '').toLowerCase().includes('unet')));

  const getModelThresholdConfig = (model) => {
    if (!model || (!model.backend && !isEsriDetectionModel(model))) {
      return { min: 0, max: 0.5, optimal: 0.3, step: 0.1 };
    }
    const backendLower = (model.backend || '').toLowerCase();
    if (backendLower.includes('srgan') || backendLower.includes('super-resolution')) {
      return { min: 2, max: 8, optimal: 4, step: 2, recommendation: 'Higher scale factor improves resolution but increases processing time' };
    }
    if (isSolarPanelModel(model)) {
      return {
        min: 0,
        max: 1,
        optimal: 0.5,
        step: 0.05,
        recommendation: 'Solar ResUNet: sigmoid mask cutoff (notebook default 0.5)',
      };
    }
    if (isEsriDetectionModel(model) || backendLower.includes('maskrcnn')) {
      return { min: 0, max: 0.7, optimal: 0.2, step: 0.1, recommendation: 'Esri / Mask R-CNN: try 0.2; lower = more detections' };
    }
    const nameLower = (model.name || '').toLowerCase();
    if (
      nameLower === 'water_body.pth' ||
      nameLower.includes('water_body') ||
      nameLower.includes('best_resunet') ||
      nameLower.includes('resunet_finetuned')
    ) {
      return {
        min: 0,
        max: 1,
        optimal: 0.4,
        step: 0.05,
        recommendation: 'Water body ResUNet: sigmoid mask cutoff (notebook default 0.4)',
      };
    }
    if (nameLower.includes('sar') && (nameLower.includes('flood') || nameLower.includes('finetune'))) {
      return { min: 0.2, max: 0.8, optimal: 0.5, step: 0.05, recommendation: 'SAR flood UNet: try 0.5; lower = more sensitive' };
    }
    return { min: 0, max: 0.5, optimal: 0.3, step: 0.1, recommendation: 'UNet works best at 0.3 threshold' };
  };

  useEffect(() => {
    if (uiCfgLoading) return;
    const getModels = async () => {
      try {
        let data;
        if (location.pathname === '/app/superResolution') {
          data = await fetchModels1();
        } else {
          data = await fetchModels();
        }
        let list = data.models || [];
        if (!uiConfig.show_super_resolution) {
          list = list.filter((m) => !modelIsSuperResolution(m));
        }
        setModels(list);
        if (list.length > 0) {
          const firstModel = list[0];
          setSelectedModel(firstModel);
          setThreshold(getModelThresholdConfig(firstModel).optimal);
        } else {
          setSelectedModel(null);
        }
      } catch (err) {
        console.error('Error fetching models:', err);
        setError('Failed to fetch models.');
      }
    };
    getModels();
  }, [location.pathname, uiConfig.show_super_resolution, uiCfgLoading]);

  useEffect(() => {
    if (uiCfgLoading) return;
    const d = uiConfig.default_inference_threshold;
    if (typeof d === 'number' && Number.isFinite(d) && !uiConfig.show_detection_threshold) {
      setThreshold(d);
    }
  }, [uiCfgLoading, uiConfig.default_inference_threshold, uiConfig.show_detection_threshold]);

  useEffect(() => {
    if (!uploading || !selectedModel || usingSseStream) return;
    const getProgressUrl = () => {
      if (selectedModel?.baseURL) return `${selectedModel.baseURL}/progress`;
      return 'http://localhost:8000/maskrcnn/progress';
    };
    const intervalId = setInterval(async () => {
      try {
        const response = await axios.get(getProgressUrl());
        setProgressData(response.data);
        setProgress(response.data.progress);
      } catch (e) { /* ignore */ }
    }, 500);
    return () => clearInterval(intervalId);
  }, [uploading, selectedModel, usingSseStream]);

  const isSatelliteBuildingPage =
    location.pathname.replace(/\/+$/, '').toLowerCase() === '/app/sataliteimage';

  const applySelectedFile = (file) => {
    if (!file) return;
    setFileType(file.type || 'image/tiff');
    setSelectedFile(file);
    setUploadedFile(file);
    onImageSelected(URL.createObjectURL(file));
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    applySelectedFile(file);
  };

  const handleLoadDemoOrtho = async () => {
    if (!isSatelliteBuildingPage || uploading) return;
    setError('');
    setDemoLoading(true);
    try {
      const res = await fetch(getDemoOrthoSampleUrl());
      if (!res.ok) {
        const msg =
          res.status === 404
            ? 'NAKSHA sample missing on server. Add the ortho GeoTIFF under models/samples/demo_ortho (or Eg_files).'
            : `Could not load demo (${res.status})`;
        throw new Error(msg);
      }
      const blob = await res.blob();
      const file = new File([blob], 'NAKSHA.tif', { type: 'image/tiff' });
      applySelectedFile(file);
    } catch (err) {
      setError(err?.message || 'Could not load demo image.');
    } finally {
      setDemoLoading(false);
    }
  };

  const handleModelSelection = (e) => {
    const selected = models.find((m) => m.name === e.target.value);
    setSelectedModel(selected);
    if (selected) {
      setThreshold(getModelThresholdConfig(selected).optimal);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile || !selectedModel) return;
    setUploading(true);
    setError('');
    setProgress(0);

    const formData = new FormData();
    formData.append('image', selectedFile);

    const baseURL = (selectedModel.baseURL || '').toLowerCase();
    const backendName = (selectedModel.backend || '').toLowerCase();
    const isMaskRcnn =
      !isSuperResolution &&
      (baseURL.includes('maskrcnn') || backendName.includes('maskrcnn'));
    const isUnetBackendReq =
      !isSuperResolution &&
      (baseURL.includes('/unet') || baseURL.includes('unet') || backendName.includes('unet'));
    const isOilSpillReq =
      !isSuperResolution &&
      (baseURL.includes('oil_spill') || backendName.includes('oil spill') || backendName.includes('oil_spill'));
    if (
      (isMaskRcnn || isUnetBackendReq || isOilSpillReq) &&
      isGeotiffFile(selectedFile) &&
      roiGeometry?.type === 'Polygon'
    ) {
      formData.append('roi_geojson', JSON.stringify(roiGeometry));
      if (
        Array.isArray(roiFullBoundsSwne) &&
        roiFullBoundsSwne.length === 4 &&
        roiFullBoundsSwne.every((n) => typeof n === 'number' && Number.isFinite(n))
      ) {
        formData.append('roi_full_bounds_swne', JSON.stringify(roiFullBoundsSwne));
      }
    }

    if (!isSuperResolution && (lulcPredictionId || '').trim()) {
      formData.append('lulc_prediction_id', (lulcPredictionId || '').trim());
    }

    // Incremental SSE for any GeoTIFF + detection backend (not only when ROI is drawn).
    // ROI is still appended above when the user drew a polygon.
    const useIncrementalStream =
      !isSuperResolution &&
      (isMaskRcnn || isUnetBackendReq) &&
      isGeotiffFile(selectedFile);

    const modelName = selectedModel.name || selectedModel;
    const backendURL = selectedModel.baseURL || 'http://localhost:8000/maskrcnn';

    if (useIncrementalStream) {
      setUsingSseStream(true);
      setProgressData({
        progress: 0,
        phase: 'loading_model',
        current_step: 'Uploading image and starting detection…',
        total_chips: 0,
        processed_chips: 0,
        eta_seconds: 0,
        status: 'running',
      });
      postPredictStream(formData, {
        baseURL: backendURL,
        modelName,
        threshold,
        streamIntervalParam: isUnetBackendReq ? 'stream_chip_interval' : 'stream_tile_interval',
        streamInterval: isUnetBackendReq ? 10 : 5,
        onEvent: (ev) => {
          if (ev?.type === 'start') {
            const total = ev.total_chips ?? ev.total_tiles ?? 0;
            setProgressData((prev) => ({
              ...prev,
              phase: 'inference',
              current_step: ev.message || (total ? `Detecting… (${total} tiles/chips)` : 'Detecting…'),
              total_chips: total,
              processed_chips: 0,
              progress: 0,
              status: 'running',
            }));
          } else if (ev?.type === 'progress') {
            const proc = ev.chips_processed ?? ev.tiles_processed ?? 0;
            const total = ev.total_chips ?? ev.total_tiles ?? 0;
            const pct =
              total > 0 ? Math.min(99, Math.round((100 * proc) / total)) : 0;
            setProgressData((prev) => ({
              ...prev,
              phase: 'inference',
              current_step:
                ev.message || `Processing ${proc}/${total}…`,
              total_chips: total,
              processed_chips: proc,
              progress: pct,
              status: 'running',
            }));
            setProgress(pct);
          }
          onStreamDetectionEvent?.(ev, { backendURL });
        },
        onDone: (ev) => {
          setUploading(false);
          setUsingSseStream(false);
          setProgress(100);
          setProgressData((prev) => ({
            ...prev,
            progress: 100,
            phase: 'done',
            current_step: 'Complete',
            status: 'idle',
            processed_chips: prev.total_chips || prev.processed_chips,
          }));
          const { type: _t, ...rest } = ev;
          onUploadSuccess({
            ...rest,
            model_name: rest.model_name || modelName,
            model_family: rest.model_family ?? selectedModel?.modelFamily ?? selectedModel?.model_family,
            _backendURL: backendURL,
            _backendType: 'detection',
          });
        },
        onError: (msg) => {
          setUploading(false);
          setUsingSseStream(false);
          setProgress(0);
          setProgressData((prev) => ({
            ...prev,
            phase: 'error',
            status: 'error',
            current_step: typeof msg === 'string' ? msg : 'Request failed',
          }));
          setError(`Upload failed: ${msg || 'Please try again.'}`);
        },
      });
      return;
    }

    try {
      const data = await uploadImage(formData, modelName, threshold, null, backendURL);
      onUploadSuccess({
        ...data,
        model_name: data.model_name || modelName,
        model_family: data.model_family ?? selectedModel?.modelFamily ?? selectedModel?.model_family,
      });
    } catch (err) {
      setError(`Upload failed: ${err.message || 'Please try again.'}`);
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  const cfg = getModelThresholdConfig(selectedModel);
  const canPredict = selectedFile && selectedModel && !uploading;

  return (
    <div className="glass-panel">
      {/* Header */}
      <div className="glass-panel-header" onClick={() => setCollapsed(!collapsed)}>
        <h3>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--geoai-od-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="2" y1="12" x2="22" y2="12"/>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
          </svg>
          Object Detection
        </h3>
        <button className={`glass-panel-toggle ${collapsed ? 'collapsed' : ''}`}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>
      </div>

      {/* Body */}
      <div className={`glass-panel-body ${collapsed ? 'collapsed' : ''}`}>
        {/* File Input */}
        <div style={{ marginBottom: 14 }}>
          <label className="sat-label">Image File</label>
          <label
            className={`sat-file-btn ${selectedFile ? 'has-file' : ''}`}
            htmlFor="sat-file-input"
          >
            <span className="file-icon">
              {selectedFile ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--geoai-od-success)" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--geoai-od-accent)" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              )}
            </span>
            <span className="file-name">
              {selectedFile ? selectedFile.name : 'Choose file...'}
            </span>
          </label>
          <input
            id="sat-file-input"
            type="file"
            accept="image/*,.tif,.tiff"
            onChange={handleFileChange}
            disabled={uploading}
            style={{ display: 'none' }}
          />
          {isSatelliteBuildingPage && (
            <button
              type="button"
              className="sat-demo-ortho-btn"
              onClick={handleLoadDemoOrtho}
              disabled={uploading || demoLoading}
            >
              {demoLoading ? (
                <>Loading demo…</>
              ) : (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="12" y1="18" x2="12" y2="12" />
                    <line x1="9" y1="15" x2="15" y2="15" />
                  </svg>
                  Load NAKSHA sample
                </>
              )}
            </button>
          )}
        </div>

        <div className="sat-divider" />

        {/* Model Selection */}
        <div style={{ marginBottom: 14 }}>
          <label className="sat-label">Detection Model</label>
          <select
            className="sat-select"
            value={selectedModel?.name || ''}
            onChange={handleModelSelection}
            disabled={uploading || models.length === 0}
          >
            <option value="">Select a model</option>
            {models.map((model, i) => {
              const kindLabel = modelUiKindLabel(model);
              return (
                <option key={i} value={model.name}>
                  {model.name}{kindLabel ? ` (${kindLabel})` : ''}
                </option>
              );
            })}
          </select>
          {selectedModel && (
            <div className="sat-model-info">
              <span className="sat-model-tag">{modelUiKindLabel(selectedModel) || selectedModel.backend || 'Default'}</span>
              <span className="sat-model-tag">{selectedModel.baseURL || 'localhost'}</span>
            </div>
          )}
        </div>

        <div className="sat-divider" />

        {/* Threshold / Scale — hidden when GEOAI_UI_SHOW_DETECTION_THRESHOLD=false (values from API default) */}
        {(isSuperResolution || uiConfig.show_detection_threshold) && (
        <div style={{ marginBottom: 16 }}>
          {isSuperResolution ? (
            <>
              <label className="sat-label">Upscaling Factor</label>
              <div className="sat-slider-wrapper">
                <div className="sat-slider-header">
                  <span className="sat-slider-value">{threshold}x</span>
                </div>
                <input
                  type="range"
                  className="sat-range"
                  min={2} max={6} step={2}
                  value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value))}
                  disabled={uploading}
                />
                <div className="sat-slider-labels">
                  <span>2x</span>
                  <span>4x</span>
                  <span>6x</span>
                </div>
              </div>
            </>
          ) : (
            <>
              <label className="sat-label">Detection Threshold</label>
              <div className="sat-slider-wrapper">
                <div className="sat-slider-header">
                  <span className="sat-slider-value">{threshold}</span>
                  <button
                    className="sat-slider-optimal-btn"
                    onClick={() => setThreshold(cfg.optimal)}
                    disabled={uploading}
                  >
                    Optimal
                  </button>
                </div>
                <input
                  type="range"
                  className="sat-range"
                  min={cfg.min} max={cfg.max} step={cfg.step}
                  value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value))}
                  disabled={uploading}
                />
                <div className="sat-slider-labels">
                  <span>{cfg.min}</span>
                  <span style={{ color: 'var(--geoai-od-accent)' }}>Optimal: {cfg.optimal}</span>
                  <span>{cfg.max}</span>
                </div>
              </div>
            </>
          )}
        </div>
        )}

        {!isSuperResolution && uiConfig.show_lulc_fields && (
          <div style={{ marginBottom: 14 }}>
            <label className="sat-label">LULC prediction ID (optional)</label>
            <input
              type="text"
              className="sat-select"
              style={{ width: '100%', padding: '8px 10px', fontSize: 12, boxSizing: 'border-box' }}
              placeholder="e.g. 20260416_110409_9ea6981b"
              value={lulcPredictionId}
              onChange={(e) => setLulcPredictionId(e.target.value)}
              disabled={uploading}
              autoComplete="off"
            />
            <p style={{ fontSize: 11, color: 'var(--geoai-od-text-muted)', marginTop: 6, lineHeight: 1.35 }}>
              Paste the ID from the land-cover page after classification. Use the same GeoTIFF and run detection
              once; buildings are stored with that prediction and load when you reopen it.
            </p>
          </div>
        )}

        {!isSuperResolution &&
          isGeotiffFile(selectedFile) &&
          roiGeometry?.type === 'Polygon' &&
          (((selectedModel?.baseURL || '').toLowerCase().includes('maskrcnn') ||
            (selectedModel?.backend || '').toLowerCase().includes('maskrcnn')) ||
            ((selectedModel?.baseURL || '').toLowerCase().includes('unet') ||
              (selectedModel?.backend || '').toLowerCase().includes('unet'))) && (
            <p className="sat-roi-hint">
              Detection will run only inside the polygon drawn on the map.
            </p>
          )}

        {/* Predict Button */}
        <button
          className={`sat-predict-btn ${uploading ? 'processing' : canPredict ? 'ready' : 'disabled'}`}
          onClick={handleUpload}
          disabled={!canPredict}
        >
          {uploading ? (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ animation: 'satSpin 1s linear infinite' }}>
                <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
              </svg>
              Processing {progress}%
            </>
          ) : (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              Predict
            </>
          )}
        </button>

        {!selectedFile && !selectedModel && (
          <div className="sat-missing-info">
            Select an image and model to begin
          </div>
        )}
        {selectedFile && !selectedModel && (
          <div className="sat-missing-info">Select a detection model</div>
        )}
        {!selectedFile && selectedModel && (
          <div className="sat-missing-info">Select an image file</div>
        )}

        {/* Progress Tracker */}
        {uploading && (
          <ProgressTracker
            progress={progressData.progress}
            phase={progressData.phase}
            currentStep={progressData.current_step}
            totalChips={progressData.total_chips}
            processedChips={progressData.processed_chips}
            etaSeconds={progressData.eta_seconds}
            status={progressData.status}
          />
        )}

        {/* Error */}
        {error && <div className="sat-error">{error}</div>}
      </div>
    </div>
  );
};

export default ImageUploader;
