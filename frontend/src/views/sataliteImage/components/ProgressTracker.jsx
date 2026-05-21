import React from 'react';

const phaseMap = {
  idle: { color: 'var(--geoai-od-on-light-muted)', label: 'Ready' },
  loading_model: { color: 'var(--geoai-od-accent)', label: 'Loading Model' },
  inference: { color: 'var(--geoai-od-accent)', label: 'AI Inference' },
  post_processing: { color: 'var(--geoai-od-accent-hover)', label: 'Post-processing' },
  done: { color: 'var(--geoai-od-accent)', label: 'Complete' },
  error: { color: '#ef4444', label: 'Error' },
};

const phaseOrder = ['loading_model', 'inference', 'post_processing', 'done'];

const ProgressTracker = ({ progress, phase, currentStep, totalChips, processedChips, etaSeconds, status }) => {
  const currentPhase = phaseMap[phase] || phaseMap.idle;
  const barColor =
    status === 'error' ? '#ef4444' : progress === 100 ? 'var(--geoai-od-success)' : currentPhase.color;

  const currentPhaseIdx = phaseOrder.indexOf(phase);

  const formatETA = (s) => {
    if (!s || s <= 0) return null;
    const mins = Math.floor(s / 60);
    const secs = Math.round(s % 60);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  return (
    <div className="sat-progress">
      {/* Header */}
      <div className="sat-progress-header">
        <div className="sat-progress-phase" style={{ color: currentPhase.color }}>
          {currentPhase.label}
        </div>
        <div className="sat-progress-pct" style={{ color: barColor }}>
          {progress}%
        </div>
      </div>

      {/* Progress bar */}
      <div className="sat-progress-bar-bg">
        <div
          className="sat-progress-bar-fill"
          style={{ width: `${progress}%`, backgroundColor: barColor }}
        />
      </div>

      {/* Current step */}
      {currentStep && (
        <div className="sat-progress-step">{currentStep}</div>
      )}

      {/* Details row */}
      {(totalChips > 0 || etaSeconds > 0) && (
        <div className="sat-progress-details">
          {totalChips > 0 && (
            <div>
              Tiles: <span className="sat-progress-detail-value">{processedChips}/{totalChips}</span>
            </div>
          )}
          {formatETA(etaSeconds) && (
            <div>
              ETA: <span className="sat-progress-detail-value">{formatETA(etaSeconds)}</span>
            </div>
          )}
        </div>
      )}

      {/* Phase dots */}
      <div className="sat-progress-dots">
        {phaseOrder.map((key, i) => {
          const isCompleted = currentPhaseIdx > i;
          const isActive = phase === key;
          return (
            <React.Fragment key={key}>
              {i > 0 && (
                <div className={`sat-progress-dot-line ${isCompleted ? 'completed' : ''}`} />
              )}
              <div
                className={`sat-progress-dot ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
                title={phaseMap[key]?.label}
              />
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

export default ProgressTracker;
