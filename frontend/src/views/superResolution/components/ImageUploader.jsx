import React, { useState, useEffect } from 'react';
import { uploadImage, fetchModels, fetchModels1 } from '../services/api';
import axios from 'axios';
import ProgressTracker from './ProgressTracker';
import { useLocation } from "react-router-dom";

const ImageUploader = ({ onUploadSuccess, onImageSelected, setFileType, setUploadedFile }) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState(null);
  const [threshold, setThreshold] = useState(0.3); // Default UNet optimal
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(0);
  const [showThresholdInfo, setShowThresholdInfo] = useState(false);
  const [progressData, setProgressData] = useState({
    progress: 0,
    phase: 'idle',
    current_step: '',
    total_chips: 0,
    processed_chips: 0,
    eta_seconds: 0,
    status: 'idle'
  });
  const location = useLocation();

  const getModelType = (model) => {
    if (!model) return 'detection';
    const lowerName = model.name.toLowerCase();
    if (lowerName.includes('srgan') || lowerName.includes('super') || lowerName.includes('resolution')) {
      return 'super-resolution';
    }
    return 'detection';
  };

  const modelType = getModelType(selectedModel);
  const isSuperResolution = modelType === 'super-resolution';
  // ENHANCED: Model-specific threshold configurations
  const getModelThresholdConfig = (model) => {
    if (!model || !model.backend) {
      return { min: 0, max: 0.5, optimal: 0.3, step: 0.1 };
    }

    const backendLower = model.backend.toLowerCase();

    if (backendLower.includes('srgan') || backendLower.includes('super-resolution')) {
      return {
        min: 2,
        max: 8,
        optimal: 4,
        step: 2,
        recommendation: 'Higher scale factor improves resolution but increases processing time'
      };
    }

    if (backendLower.includes('maskrcnn')) {
      return {
        min: 0,
        max: 0.7,
        optimal: 0.2,
        step: 0.1,
        recommendation: 'MaskRCNN models work best with threshold 0.2 for optimal detection accuracy'
      };
    }
    const nameLower = (model.name || '').toLowerCase();
    if (nameLower.includes('sar') && (nameLower.includes('flood') || nameLower.includes('finetune'))) {
      return {
        min: 0.2,
        max: 0.8,
        optimal: 0.5,
        step: 0.05,
        recommendation: 'SAR flood UNet: try 0.5; lower = more sensitive'
      };
    }
    return {
      min: 0,
      max: 0.5,
      optimal: 0.3,
      step: 0.1,
      recommendation: 'UNet models work best with threshold 0.3 for optimal building detection'
    };
  };

  // Enhanced model fetching
  useEffect(() => {
    const getModels = async () => {
      try {
        console.log('🔄 Fetching models for Super Resolution page...');
        const data = await fetchModels1();

        console.log('✅ Fetched models:', data.models);
        setModels(data.models);

        if (data.models.length > 0) {
          const firstModel = data.models[0];
          setSelectedModel(firstModel);

          // Set optimal threshold for first model
          const thresholdConfig = getModelThresholdConfig(firstModel);
          setThreshold(thresholdConfig.optimal);

          console.log('🎯 Default selected model:', firstModel);
        } else {
          console.warn('⚠️ No models returned for Super Resolution.');
        }
      } catch (err) {
        console.error('❌ Error fetching models:', err);
        setError('Failed to fetch models. Please ensure the backend on port 8002 is running.');
      }
    };
    getModels();
  }, [onImageSelected]); // Add minimal dependency to trigger if needed, or leave [] if preferred

  // Dynamic progress tracking
  useEffect(() => {
    if (!uploading || !selectedModel) return;

    const getProgressUrl = () => {
      if (selectedModel && selectedModel.baseURL) {
        return `${selectedModel.baseURL}/progress`;
      }
      return 'http://localhost:8000/maskrcnn/progress';
    };

    const intervalId = setInterval(async () => {
      try {
        const progressUrl = getProgressUrl();
        const response = await axios.get(progressUrl);
        setProgressData(response.data);
        setProgress(response.data.progress); // Keep existing progress for backward compatibility
      } catch (error) {
        console.error('Error fetching progress:', error);
      }
    }, 500); // Poll every 500ms for smoother updates

    return () => clearInterval(intervalId);
  }, [uploading, selectedModel]);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    console.log('📁 Selected file:', file);
    setFileType(file.type);
    setSelectedFile(file);
    setUploadedFile(file);
    const imageUrl = URL.createObjectURL(file);
    onImageSelected(imageUrl);
  };
  const handleModelSelection = (e) => {
    const selectedOption = models.find((m) => m.name === e.target.value);
    setSelectedModel(selectedOption);

    if (selectedOption) {
      const thresholdConfig = getModelThresholdConfig(selectedOption);
      setThreshold(thresholdConfig.optimal);

      const newModelType = getModelType(selectedOption);
      if (newModelType !== 'super-resolution') {
        setShowThresholdInfo(true);
        setTimeout(() => setShowThresholdInfo(false), 6000);
      }

      console.log(`🔧 Switched to ${newModelType} mode, value=${thresholdConfig.optimal}`);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError('Please select a file to upload.');
      return;
    }
    if (!selectedModel) {
      setError('Please select a model.');
      return;
    }

    setUploading(true);
    setError('');
    setProgress(0);

    const formData = new FormData();
    formData.append('image', selectedFile);

    try {
      const modelName = typeof selectedModel === 'string' ? selectedModel : selectedModel?.name || '';
      const backendInfo = selectedModel.backend || 'Default Backend';
      const backendURL = selectedModel.baseURL || 'Default URL';

      console.log('🚀 Starting upload with:');
      console.log(`   Model: ${modelName}`);
      console.log(`   Backend: ${backendInfo}`);
      console.log(`   URL: ${backendURL}`);
      console.log(`   Threshold: ${threshold}`);

      const data = await uploadImage(formData, modelName, threshold, null, backendURL);

      console.log('✅ Upload successful:', data);
      onUploadSuccess(data);
    } catch (err) {
      console.error('❌ Upload failed:', err);
      setError(`Upload failed: ${err.message || 'Please try again.'}`);
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  // Get current threshold configuration
  const currentThresholdConfig = getModelThresholdConfig(selectedModel);

  return (
    <div className="image-uploader">
      <div className="upload-section">
        <input
          type="file"
          accept="image/*,.tif,.tiff"
          onChange={handleFileChange}
          disabled={uploading}
          className="file-input"
        />

        {/* Enhanced model selection */}
        <div className="model-selection">
          <label htmlFor="model-select">Select Detection Model:</label>
          <select
            id="model-select"
            value={selectedModel?.name || ''}
            onChange={handleModelSelection}
            disabled={uploading || models.length === 0}
            className="model-select"
          >
            <option value="">Select a model</option>
            {models.map((model, index) => (
              <option key={index} value={model.name}>
                {model.name} {model.backend && `(${model.backend})`}
              </option>
            ))}
          </select>

          {/* Model info display */}
          {selectedModel && (
            <div className="model-info" style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>
              <div>Backend: {selectedModel.backend || 'Unknown'}</div>
              <div>URL: {selectedModel.baseURL || 'Unknown'}</div>
            </div>
          )}
        </div>

        {/* ENHANCED: Dynamic threshold/scale selection based on model type */}
        <div className="threshold-section">
          {isSuperResolution ? (
            // Super-Resolution: Scale Factor selector
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <label htmlFor="scale-factor">Upscaling Factor: {threshold}x</label>
              </div>
              <input
                id="scale-factor"
                type="range"
                min={2}
                max={6}
                step={2}
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                disabled={uploading}
                className="threshold-slider"
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#888' }}>
                <span>2x</span>
                <span style={{ color: '#007bff', fontWeight: 'bold' }}>4x (Recommended)</span>
                <span>6x</span>
              </div>
              <div style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>
                Higher scale = Better resolution but slower processing
              </div>
            </>
          ) : (
            // Detection: Threshold selector (existing code)
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <label htmlFor="threshold">Detection Threshold: {threshold}</label>
                <button
                  type="button"
                  onClick={() => setThreshold(currentThresholdConfig.optimal)}
                  disabled={uploading}
                  style={{
                    padding: '2px 8px',
                    fontSize: '10px',
                    backgroundColor: '#007bff',
                    color: 'white',
                    border: 'none',
                    borderRadius: '3px',
                    cursor: 'pointer',
                  }}
                  title={`Set optimal threshold (${currentThresholdConfig.optimal})`}
                >
                  Optimal
                </button>
              </div>
              <input
                id="threshold"
                type="range"
                min={currentThresholdConfig.min}
                max={currentThresholdConfig.max}
                step={currentThresholdConfig.step}
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                disabled={uploading}
                className="threshold-slider"
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#888' }}>
                <span>{currentThresholdConfig.min}</span>
                <span style={{ color: '#007bff', fontWeight: 'bold' }}>
                  Optimal: {currentThresholdConfig.optimal}
                </span>
                <span>{currentThresholdConfig.max}</span>
              </div>
            </>
          )}
        </div>


        {/* ENHANCED: Threshold recommendation popup */}
        {showThresholdInfo && currentThresholdConfig.recommendation && (
          <div style={{
            backgroundColor: '#e7f3ff',
            border: '1px solid #b3d9ff',
            borderRadius: '5px',
            padding: '10px',
            margin: '10px 0',
            fontSize: '13px',
            color: '#0056b3',
            position: 'relative',
            animation: 'fadeIn 0.3s ease-in'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '16px' }}>💡</span>
              <span>{currentThresholdConfig.recommendation}</span>
              <button
                onClick={() => setShowThresholdInfo(false)}
                style={{
                  position: 'absolute',
                  right: '5px',
                  top: '5px',
                  background: 'none',
                  border: 'none',
                  fontSize: '14px',
                  cursor: 'pointer',
                  color: '#0056b3'
                }}
              >
                ×
              </button>
            </div>
          </div>
        )}
        <button
          onClick={handleUpload}
          disabled={uploading || !selectedFile || !selectedModel}
          style={{
            backgroundColor: uploading || !selectedFile || !selectedModel ? '#cccccc' : '#10b981',
            color: 'white',
            padding: '12px 24px',
            fontSize: '16px',
            fontWeight: '600',
            border: 'none',
            borderRadius: '8px',
            cursor: uploading || !selectedFile || !selectedModel ? 'not-allowed' : 'pointer',
            transition: 'all 0.3s ease',
            boxShadow: '0 2px 4px rgba(16, 185, 129, 0.2)',
            minWidth: '180px'
          }}
          onMouseOver={(e) => {
            if (!uploading && selectedFile && selectedModel) {
              e.target.style.backgroundColor = '#059669';
              e.target.style.transform = 'translateY(-1px)';
            }
          }}
          onMouseOut={(e) => {
            if (!uploading && selectedFile && selectedModel) {
              e.target.style.backgroundColor = '#10b981';
              e.target.style.transform = 'translateY(0)';
            }
          }}
        >
          {uploading ? `Processing... ${progress}%` : 'Predict'}
        </button>

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


        {/* Progress indicator */}
        {uploading && (
          <div className="progress-info">
            <div>Progress: {progress}%</div>
            {selectedModel && (
              <div style={{ fontSize: '12px' }}>
                Using: {selectedModel.backend} ({selectedModel.baseURL})
                <br />
                Threshold: {threshold} (Range: {currentThresholdConfig.min}-{currentThresholdConfig.max})
              </div>
            )}
          </div>
        )}

        {/* Error display */}
        {error && (
          <div className="error-message" style={{ color: 'red', marginTop: '10px' }}>
            {error}
          </div>
        )}
      </div>

      {/* CSS for fade-in animation */}
      <style jsx>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-10px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
};

export default ImageUploader;