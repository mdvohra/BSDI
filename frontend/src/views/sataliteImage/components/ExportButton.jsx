import React, { useState, useRef, useEffect } from 'react';

const ExportButton = ({ onExport, showGeoTiffOnly = false }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleExport = (format) => {
    setIsOpen(false);
    onExport(format);
  };

  return (
    <div ref={dropdownRef} style={{ position: 'relative' }}>
      <button className="sat-export-btn" onClick={() => setIsOpen(!isOpen)}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        Export
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ opacity: 0.5 }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <div className="sat-export-dropdown">
          {showGeoTiffOnly ? (
            <button className="sat-export-option" onClick={() => handleExport('geotiff')}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--geoai-od-accent-text-strong)" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              Class GeoTIFF (.tif)
            </button>
          ) : (
            <>
              <button className="sat-export-option" onClick={() => handleExport('shapefile')}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                Shapefile (.shp)
              </button>
              <button className="sat-export-option" onClick={() => handleExport('geojson')}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--geoai-od-accent)" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
                GeoJSON (.geojson)
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default ExportButton;
