import React from 'react';

const ProgressTracker = ({ progress, progressImage }) => {
  const getColor = () => {
    if (progress >= 100) return '#10b981';
    if (progress >= 50) return '#3b82f6';
    return '#f59e0b';
  };

  return (
    <div style={{
      backgroundColor: '#f8fafc',
      border: '1px solid #e2e8f0',
      borderRadius: '10px',
      padding: '12px 14px',
      marginTop: '0.75rem',
      fontFamily: 'system-ui, sans-serif'
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '10px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontWeight: '600', fontSize: '13px', color: getColor() }}>
            {progress >= 100 ? 'Complete' : 'Classifying…'}
          </span>
        </div>
        <div style={{ fontSize: '16px', fontWeight: '700', color: getColor() }}>
          {progress}%
        </div>
      </div>

      <div style={{
        width: '100%',
        height: '8px',
        backgroundColor: '#e2e8f0',
        borderRadius: '4px',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${progress}%`,
          height: '100%',
          backgroundColor: getColor(),
          transition: 'width 0.3s ease',
          borderRadius: '4px'
        }} />
      </div>

      {progressImage && (
        <div style={{ marginTop: '10px', textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '4px' }}>Live Preview</div>
          <img
            src={progressImage}
            alt="Classification progress"
            style={{
              maxWidth: '100%',
              maxHeight: '120px',
              borderRadius: '6px',
              border: '1px solid #e2e8f0'
            }}
          />
        </div>
      )}
    </div>
  );
};

export default ProgressTracker;
