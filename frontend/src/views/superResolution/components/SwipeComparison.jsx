import React, { useState, useRef, useEffect } from 'react';

const SwipeComparison = ({ 
  beforeImage, 
  afterImage, 
  beforeLabel = "Original",
  afterLabel = "Processed",
  sliderLineColor = "#10b981",
}) => {
  const [sliderPosition, setSliderPosition] = useState(50);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoaded, setIsLoaded] = useState({ before: false, after: false });
  const containerRef = useRef(null);

  console.log("🖼️ SwipeComparison:", { beforeImage, afterImage });

  if (!beforeImage || !afterImage) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '400px',
        background: '#f3f4f6',
        borderRadius: '8px',
        color: '#6b7280',
        fontSize: '16px'
      }}>
        No images available for comparison
      </div>
    );
  }

  const handleMove = (clientX) => {
    if (!containerRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const percentage = (x / rect.width) * 100;
    
    // Clamp between 0 and 100
    const clampedPercentage = Math.min(Math.max(percentage, 0), 100);
    setSliderPosition(clampedPercentage);
  };

  const handleMouseDown = () => {
    setIsDragging(true);
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleMouseMove = (e) => {
    if (!isDragging) return;
    handleMove(e.clientX);
  };

  const handleTouchMove = (e) => {
    if (!isDragging || !e.touches[0]) return;
    handleMove(e.touches[0].clientX);
  };

  useEffect(() => {
    const handleGlobalMouseUp = () => {
      setIsDragging(false);
    };

    const handleGlobalMouseMove = (e) => {
      if (isDragging) {
        handleMove(e.clientX);
      }
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

  const handleImageLoad = (type) => {
    console.log(`✅ ${type} image loaded`);
    setIsLoaded(prev => ({ ...prev, [type]: true }));
  };

  const handleImageError = (type, error) => {
    console.error(`❌ ${type} image failed to load:`, error);
  };

  return (
    <div 
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onTouchMove={handleTouchMove}
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
        justifyContent: 'center'
      }}
    >
      {/* Loading indicator */}
      {(!isLoaded.before || !isLoaded.after) && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          color: 'white',
          fontSize: '16px',
          zIndex: 100
        }}>
          Loading images...
        </div>
      )}

      {/* Before Image Container (Left/Bottom layer) */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden'
      }}>
        <img 
          src={beforeImage}
          alt="Before" 
          onLoad={() => handleImageLoad('before')}
          onError={(e) => handleImageError('before', e)}
          style={{
            maxWidth: '100%',
            maxHeight: '100%',
            width: 'auto',
            height: 'auto',
            objectFit: 'contain',
            pointerEvents: 'none',
            userSelect: 'none'
          }}
          crossOrigin="anonymous"
        />
      </div>

      {/* After Image Container (Right/Top layer with clip) */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        clipPath: `polygon(0 0, ${sliderPosition}% 0, ${sliderPosition}% 100%, 0 100%)`
      }}>
        <img 
          src={afterImage}
          alt="After" 
          onLoad={() => handleImageLoad('after')}
          onError={(e) => handleImageError('after', e)}
          style={{
            maxWidth: '100%',
            maxHeight: '100%',
            width: 'auto',
            height: 'auto',
            objectFit: 'contain',
            pointerEvents: 'none',
            userSelect: 'none'
          }}
          crossOrigin="anonymous"
        />
      </div>

      {/* Slider Line */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: `${sliderPosition}%`,
        width: '4px',
        height: '100%',
        backgroundColor: sliderLineColor,
        transform: 'translateX(-50%)',
        boxShadow: '0 0 10px rgba(0,0,0,0.5)',
        zIndex: 10,
        pointerEvents: 'none'
      }}>
        {/* Top arrow */}
        <div style={{
          position: 'absolute',
          top: '0',
          left: '50%',
          transform: 'translateX(-50%)',
          width: 0,
          height: 0,
          borderLeft: '8px solid transparent',
          borderRight: '8px solid transparent',
          borderTop: `12px solid ${sliderLineColor}`
        }} />
        
        {/* Bottom arrow */}
        <div style={{
          position: 'absolute',
          bottom: '0',
          left: '50%',
          transform: 'translateX(-50%)',
          width: 0,
          height: 0,
          borderLeft: '8px solid transparent',
          borderRight: '8px solid transparent',
          borderBottom: `12px solid ${sliderLineColor}`
        }} />
      </div>

      {/* Slider Handle */}
      <div 
        onMouseDown={handleMouseDown}
        onTouchStart={handleMouseDown}
        style={{
          position: 'absolute',
          top: '50%',
          left: `${sliderPosition}%`,
          transform: 'translate(-50%, -50%)',
          width: '60px',
          height: '60px',
          backgroundColor: sliderLineColor,
          borderRadius: '50%',
          border: '4px solid white',
          boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
          cursor: isDragging ? 'grabbing' : 'grab',
          zIndex: 20,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '24px',
          color: 'white',
          fontWeight: 'bold',
          transition: isDragging ? 'none' : 'transform 0.2s ease',
          userSelect: 'none'
        }}
        onMouseEnter={(e) => {
          if (!isDragging) {
            e.currentTarget.style.transform = 'translate(-50%, -50%) scale(1.1)';
          }
        }}
        onMouseLeave={(e) => {
          if (!isDragging) {
            e.currentTarget.style.transform = 'translate(-50%, -50%) scale(1)';
          }
        }}
      >
        <span style={{ pointerEvents: 'none' }}>⟷</span>
      </div>

      {/* Labels */}
      <div style={{
        position: 'absolute',
        top: '15px',
        left: '15px',
        background: 'rgba(0, 0, 0, 0.85)',
        color: 'white',
        padding: '10px 16px',
        borderRadius: '8px',
        fontSize: '14px',
        fontWeight: '600',
        zIndex: 15,
        pointerEvents: 'none',
        boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
        backdropFilter: 'blur(4px)'
      }}>
        {beforeLabel}
      </div>
      <div style={{
        position: 'absolute',
        top: '15px',
        right: '15px',
        background: `${sliderLineColor}`,
        color: 'white',
        padding: '10px 16px',
        borderRadius: '8px',
        fontSize: '14px',
        fontWeight: '600',
        zIndex: 15,
        pointerEvents: 'none',
        boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
      }}>
        {afterLabel}
      </div>

      {/* Instructions */}
      <div style={{
        position: 'absolute',
        bottom: '15px',
        left: '50%',
        transform: 'translateX(-50%)',
        background: 'rgba(0, 0, 0, 0.85)',
        color: 'white',
        padding: '10px 20px',
        borderRadius: '8px',
        fontSize: '13px',
        zIndex: 15,
        pointerEvents: 'none',
        boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        backdropFilter: 'blur(4px)'
      }}>
        <span style={{ fontSize: '16px' }}>⟷</span>
        <span>Drag slider to compare</span>
      </div>
    </div>
  );
};

export default SwipeComparison;
