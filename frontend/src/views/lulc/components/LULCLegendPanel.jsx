import React from 'react';
import { lulcColorForClass } from '../constants/classColors';

/**
 * Land-cover class list + scores.
 * placement="sidebar" — docked in the control column (default for main app).
 * placement="overlay" — on-map floating (optional).
 */
const LULCLegendPanel = ({ classificationData, placement = 'sidebar' }) => {
  if (!classificationData) return null;

  const entries = classificationData.predictions
    ? Object.entries(classificationData.predictions).sort(([, a], [, b]) => b - a)
    : [];

  const isSidebar = placement === 'sidebar';

  return (
    <div
      className={isSidebar ? 'lulc-legend-panel lulc-legend-panel--sidebar' : 'lulc-legend-panel lulc-legend-panel--overlay'}
      style={
        isSidebar
          ? {
              position: 'relative',
              width: '100%',
              maxHeight: 260,
              overflowY: 'auto',
              padding: 0,
              fontSize: '12px',
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            }
          : {
              position: 'absolute',
              bottom: 52,
              left: 12,
              background: 'rgba(255, 255, 255, 0.96)',
              padding: '12px 14px',
              borderRadius: '10px',
              fontSize: '13px',
              zIndex: 1100,
              boxShadow: '0 2px 12px rgba(0, 0, 0, 0.18)',
              maxWidth: 'min(320px, 42vw)',
              maxHeight: 'min(340px, 45vh)',
              overflowY: 'auto',
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
              pointerEvents: 'auto',
            }
      }
    >
      <div
        style={{
          fontWeight: 700,
          color: '#059669',
          marginBottom: '8px',
          fontSize: isSidebar ? '11px' : '14px',
          textTransform: isSidebar ? 'uppercase' : 'none',
          letterSpacing: isSidebar ? '0.05em' : 'normal',
        }}
      >
        {isSidebar ? 'Classification summary' : 'Land cover'}
      </div>
      <div style={{ fontWeight: 600, color: '#111827', marginBottom: '10px', lineHeight: 1.35 }}>
        {classificationData.top_class}{' '}
        <span style={{ color: '#047857' }}>({classificationData.top_pct}%)</span>
      </div>
      {entries.length > 0 && (
        <div style={{ fontSize: '12px', color: '#374151', lineHeight: 1.65 }}>
          {entries.map(([cls, pct]) => (
            <div
              key={cls}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
                marginBottom: '4px',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                <span
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: 3,
                    flexShrink: 0,
                    background: lulcColorForClass(cls),
                    border: '1px solid rgba(0,0,0,0.12)',
                  }}
                />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cls}</span>
              </span>
              <span style={{ fontWeight: 600, flexShrink: 0, color: '#065f46' }}>
                {(Number(pct) * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      )}
      {classificationData.crs && (
        <div
          style={{
            fontSize: '11px',
            color: '#6b7280',
            marginTop: '10px',
            paddingTop: '8px',
            borderTop: '1px solid #e5e7eb',
          }}
        >
          <strong>CRS:</strong> {classificationData.crs}
        </div>
      )}
    </div>
  );
};

export default LULCLegendPanel;
