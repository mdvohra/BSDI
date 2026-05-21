// src/components/ProgressTracker.jsx
import React from 'react';

const ProgressTracker = ({ progress, phase, currentStep, totalChips, processedChips, etaSeconds, status }) => {
  // Phase configurations
  const phases = {
    idle: { color: '#6b7280', label: 'Ready', icon: '⏸️' },
    initializing: { color: '#3b82f6', label: 'Initializing', icon: '🔄' },
    loading: { color: '#10b981', label: 'Loading Image', icon: '📁' },
    preprocessing: { color: '#f59e0b', label: 'Preprocessing', icon: '⚙️' },
    model_loading: { color: '#8b5cf6', label: 'Loading Model', icon: '🧠' },
    prediction: { color: '#ef4444', label: 'AI Prediction', icon: '🤖' },
    postprocessing: { color: '#06b6d4', label: 'Post-processing', icon: '🔧' },
    exporting: { color: '#84cc16', label: 'Generating Output', icon: '📤' },
    completed: { color: '#10b981', label: 'Completed', icon: '✅' },
    error: { color: '#ef4444', label: 'Error', icon: '❌' }
  };

  const currentPhase = phases[phase] || phases.idle;

  // Format ETA
  const formatETA = (seconds) => {
    if (!seconds || seconds <= 0) return '';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return mins > 0 ? `${mins}m ${secs}s remaining` : `${secs}s remaining`;
  };

  // Progress bar color based on phase
  const getProgressBarColor = () => {
    if (status === 'error') return '#ef4444';
    if (progress === 100) return '#10b981';
    return currentPhase.color;
  };

  return (
    <div style={{
      backgroundColor: '#f8fafc',
      border: '1px solid #e2e8f0',
      borderRadius: '12px',
      padding: '20px',
      margin: '15px 0',
      fontFamily: 'system-ui, sans-serif'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '15px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '18px' }}>{currentPhase.icon}</span>
          <span style={{
            fontWeight: '600',
            fontSize: '16px',
            color: currentPhase.color
          }}>
            {currentPhase.label}
          </span>
        </div>
        <div style={{
          fontSize: '18px',
          fontWeight: '700',
          color: getProgressBarColor()
        }}>
          {progress}%
        </div>
      </div>

      {/* Progress Bar */}
      <div style={{
        width: '100%',
        height: '8px',
        backgroundColor: '#e2e8f0',
        borderRadius: '4px',
        overflow: 'hidden',
        marginBottom: '12px'
      }}>
        <div style={{
          width: `${progress}%`,
          height: '100%',
          backgroundColor: getProgressBarColor(),
          transition: 'width 0.3s ease',
          borderRadius: '4px'
        }} />
      </div>

      {/* Current Step */}
      <div style={{
        fontSize: '14px',
        color: '#374151',
        marginBottom: '8px',
        minHeight: '20px'
      }}>
        {currentStep}
      </div>

      {/* Detailed Info */}
      {(totalChips > 0 || etaSeconds > 0) && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: '12px',
          marginTop: '12px',
          padding: '12px',
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          fontSize: '12px'
        }}>
          {totalChips > 0 && (
            <div>
              <div style={{ color: '#6b7280', marginBottom: '2px' }}>Chip Progress</div>
              <div style={{ fontWeight: '600', color: '#1f2937' }}>
                {processedChips} / {totalChips}
              </div>
            </div>
          )}
          {etaSeconds > 0 && (
            <div>
              <div style={{ color: '#6b7280', marginBottom: '2px' }}>Time Remaining</div>
              <div style={{ fontWeight: '600', color: '#1f2937' }}>
                {formatETA(etaSeconds)}
              </div>
            </div>
          )}
          {phase === 'prediction' && totalChips > 0 && (
            <div>
              <div style={{ color: '#6b7280', marginBottom: '2px' }}>Processing Rate</div>
              <div style={{ fontWeight: '600', color: '#1f2937' }}>
                {processedChips > 0 ? `${Math.round(processedChips / ((Date.now() - Date.now()) / 1000 + 1))} chips/sec` : '--'}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Phase Indicators */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginTop: '15px',
        padding: '8px 0'
      }}>
        {['loading', 'preprocessing', 'prediction', 'postprocessing', 'exporting'].map((phaseKey, index) => {
          const phaseConfig = phases[phaseKey];
          const isActive = phase === phaseKey;
          const isCompleted = ['loading', 'preprocessing', 'model_loading'].includes(phaseKey) && 
                           ['prediction', 'postprocessing', 'exporting', 'completed'].includes(phase);
          
          return (
            <div
              key={phaseKey}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                opacity: isActive || isCompleted ? 1 : 0.3,
                transition: 'opacity 0.3s ease'
              }}
            >
              <div style={{
                width: '24px',
                height: '24px',
                borderRadius: '50%',
                backgroundColor: isActive || isCompleted ? phaseConfig.color : '#e2e8f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '10px',
                marginBottom: '4px',
                color: 'white'
              }}>
                {isCompleted ? '✓' : index + 1}
              </div>
              <div style={{
                fontSize: '10px',
                textAlign: 'center',
                color: isActive || isCompleted ? phaseConfig.color : '#6b7280',
                fontWeight: isActive ? '600' : '400'
              }}>
                {phaseConfig.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ProgressTracker;
