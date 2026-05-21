import React from 'react';
import { Container } from 'react-bootstrap';
import ObjectDetectionProcessPanel from '../../components/ObjectDetectionProcessPanel';

const DashDefault = () => {
  return (
    <React.Fragment>
      <Container fluid className="geoai-dashboard px-3 py-4">
        <div
          className="geoai-dashboard-hero mb-4 p-4 rounded-3"
          style={{
            background: 'linear-gradient(135deg, #fff 0%, #FFF5F5 50%, #FDECEC 100%)',
            border: '1px solid rgba(206, 17, 38, 0.15)',
          }}
        >
          <h2 className="mb-2 geoai-wordmark geoai-wordmark--on-light">GeoAI</h2>
          <p className="mb-1 text-muted" style={{ maxWidth: 720, fontSize: '1.05rem', lineHeight: 1.6 }}>
            <strong style={{ color: '#333' }}>Object detection</strong> on satellite and aerial imagery—upload
            orthoimagery, run AI-backed detectors, and review results on the map.
          </p>
        </div>

        <h4 className="mb-3" style={{ fontWeight: 600, color: '#333' }}>
          Process
        </h4>
        <p className="text-muted mb-4" style={{ maxWidth: 900 }}>
          Follow these steps in the object detection workspace. Each stage is designed for operational mapping and
          government-ready review.
        </p>

        <ObjectDetectionProcessPanel />
      </Container>
    </React.Fragment>
  );
};

export default DashDefault;
