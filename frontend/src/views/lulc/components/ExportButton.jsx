import React from 'react';
import Dropdown from 'react-bootstrap/Dropdown';

const ExportButton = ({ onExport, geotiffAvailable, disabled }) => {
  return (
    <Dropdown className="w-100 lulc-export-dropdown">
      <Dropdown.Toggle
        variant="success"
        id="lulc-export-toggle"
        disabled={disabled}
        className="w-100 py-2 fw-semibold rounded-3 border-0 shadow-sm"
      >
        Export results
      </Dropdown.Toggle>
      <Dropdown.Menu className="w-100 shadow-sm border mt-1 rounded-3 py-1">
        <Dropdown.Item
          className="py-2 px-3"
          onClick={() => onExport('png')}
        >
          PNG image
        </Dropdown.Item>
        {geotiffAvailable && (
          <Dropdown.Item
            className="py-2 px-3"
            onClick={() => onExport('geotiff')}
          >
            GeoTIFF (georeferenced)
          </Dropdown.Item>
        )}
      </Dropdown.Menu>
    </Dropdown>
  );
};

export default ExportButton;
