import React, { useState, useRef, useEffect } from 'react';

/** PNG / non-GeoTIFF before–after swipe (no map). For GeoTIFFs use LULCTiffCompareMaps instead. */
const SwipeComparison = ({
  beforeImage,
  afterImage,
  beforeLabel = 'Original',
  afterLabel = 'Classified',
  sliderLineColor = '#10b981',
}) => {
  const [sliderPosition, setSliderPosition] = useState(50);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef(null);

  if (!beforeImage || !afterImage) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '400px',
          background: '#f3f4f6',
          borderRadius: '8px',
          color: '#6b7280',
          fontSize: '16px',
        }}
      >
        No images available for comparison
      </div>
    );
  }

  const handleMove = (clientX) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const percentage = (x / rect.width) * 100;
    setSliderPosition(Math.min(Math.max(percentage, 0), 100));
  };

  useEffect(() => {
    const handleGlobalMouseUp = () => setIsDragging(false);
    const handleGlobalMouseMove = (e) => {
      if (isDragging) handleMove(e.clientX);
    };

    if (isDragging) {
      document.addEventListener('mouseup', handleGlobalMouseUp);
      document.addEventListener('mousemove', handleGlobalMouseMove);
      document.addEventListener('touchend', handleGlobalMouseUp);
      return () => {
        document.removeEventListener('mouseup', handleGlobalMouseUp);
        document.removeEventListener('mousemove', handleGlobalMouseMove);
        document.removeEventListener('touchend', handleGlobalMouseUp);
      };
    }
  }, [isDragging]);

  return (
    <div
      ref={containerRef}
      onMouseMove={(e) => isDragging && handleMove(e.clientX)}
      onTouchMove={(e) => isDragging && e.touches[0] && handleMove(e.touches[0].clientX)}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        cursor: isDragging ? 'grabbing' : 'grab',
        userSelect: 'none',
        backgroundColor: '#1a1a1a',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
        }}
      >
        <img
          src={beforeImage}
          alt="Before"
          style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', pointerEvents: 'none' }}
          crossOrigin="anonymous"
          draggable={false}
        />
      </div>

      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          clipPath: `polygon(0 0, ${sliderPosition}% 0, ${sliderPosition}% 100%, 0 100%)`,
        }}
      >
        <img
          src={afterImage}
          alt="After"
          style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', pointerEvents: 'none' }}
          crossOrigin="anonymous"
          draggable={false}
        />
      </div>

      <div
        style={{
          position: 'absolute',
          top: 0,
          left: `${sliderPosition}%`,
          width: '4px',
          height: '100%',
          backgroundColor: sliderLineColor,
          transform: 'translateX(-50%)',
          boxShadow: '0 0 10px rgba(0,0,0,0.5)',
          zIndex: 10,
          pointerEvents: 'none',
        }}
      />

      <div
        onMouseDown={() => setIsDragging(true)}
        onTouchStart={() => setIsDragging(true)}
        style={{
          position: 'absolute',
          top: '50%',
          left: `${sliderPosition}%`,
          transform: 'translate(-50%, -50%)',
          width: '50px',
          height: '50px',
          backgroundColor: sliderLineColor,
          borderRadius: '50%',
          border: '3px solid white',
          boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
          cursor: isDragging ? 'grabbing' : 'grab',
          zIndex: 20,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '20px',
          color: 'white',
          fontWeight: 'bold',
          userSelect: 'none',
        }}
      >
        <span style={{ pointerEvents: 'none' }}>&#x27F7;</span>
      </div>

      <div
        style={{
          position: 'absolute',
          top: '15px',
          left: '15px',
          background: 'rgba(0,0,0,0.85)',
          color: 'white',
          padding: '8px 14px',
          borderRadius: '8px',
          fontSize: '13px',
          fontWeight: '600',
          zIndex: 15,
          pointerEvents: 'none',
        }}
      >
        {beforeLabel}
      </div>
      <div
        style={{
          position: 'absolute',
          top: '15px',
          right: '15px',
          background: sliderLineColor,
          color: 'white',
          padding: '8px 14px',
          borderRadius: '8px',
          fontSize: '13px',
          fontWeight: '600',
          zIndex: 15,
          pointerEvents: 'none',
        }}
      >
        {afterLabel}
      </div>
    </div>
  );
};

export default SwipeComparison;
