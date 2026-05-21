// src/components/ExportButton.js
import React, { useState, useRef, useEffect } from 'react';

const ExportButton = ({ onExport }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown if user clicks outside of it
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
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        // className="bg-green-500 text-white px-4 py-2 rounded-md hover:bg-green-600 focus:outline-none"
        style={{
          backgroundColor: "#10B981",
          color: "#fff",
          padding: "0.5rem 1rem",
          borderRadius: "0.375rem",
          cursor: "pointer",
          border: "none",
          outline: "none",
          marginTop: "0.5rem",
        }}
      >
        Export
      </button>
      {isOpen && (
        <div className="absolute right-0 mt-2 w-48 bg-white shadow-lg rounded-md">
          <button
            onClick={() => handleExport('shapefile')}
            className="block w-full px-4 py-2 text-left hover:bg-gray-100 focus:outline-none"
          >
            Export as Shapefile
          </button>
          <button
            onClick={() => handleExport('geojson')}
            className="block w-full px-4 py-2 text-left hover:bg-gray-100 focus:outline-none"
          >
            Export as GeoJSON
          </button>
        </div>
      )}
    </div>
  );
};

export default ExportButton;
