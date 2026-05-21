import React from 'react';
import { Row, Col, Card, Button } from 'react-bootstrap';
import { useNavigate } from 'react-router-dom';

const STEPS = [
  {
    title: 'Upload imagery',
    description:
      'Select an ortho GeoTIFF or compatible raster. Optionally load the demo ortho sample to try the workflow immediately.',
    icon: 'feather icon-upload',
  },
  {
    title: 'Choose detection model',
    description:
      'Pick the model served by your deployment (e.g. UNet buildings, Mask R-CNN objects). Optional fields appear only when enabled by your administrator.',
    icon: 'feather icon-layers',
  },
  {
    title: 'Region of interest (optional)',
    description:
      'Draw a polygon on the map to limit inference to an area. Full-scene runs when no ROI is drawn.',
    icon: 'feather icon-edit-2',
  },
  {
    title: 'Run prediction',
    description:
      'Start detection; progress streams for large GeoTIFFs. Results overlay as vectors on the map viewer.',
    icon: 'feather icon-zap',
  },
  {
    title: 'Review & export',
    description:
      'Inspect detections on the basemap, adjust display options if enabled, then export GeoJSON, Shapefile, or GeoTIFF as offered.',
    icon: 'feather icon-download',
  },
];

export default function ObjectDetectionProcessPanel() {
  const navigate = useNavigate();

  return (
    <div className="object-detection-process">
      <Row className="g-4 mb-4">
        {STEPS.map((step, i) => (
          <Col key={step.title} md={6} xl={4}>
            <Card
              className="h-100 border-0 shadow-sm"
              style={{
                borderRadius: 12,
                border: '1px solid rgba(206, 17, 38, 0.15)',
                background: '#fff',
              }}
            >
              <Card.Body>
                <div className="d-flex align-items-start gap-3">
                  <span
                    className="rounded-circle d-flex align-items-center justify-content-center flex-shrink-0 fw-bold text-white"
                    style={{
                      width: 36,
                      height: 36,
                      fontSize: 14,
                      background: '#CE1126',
                      boxShadow: '0 0 12px rgba(206, 17, 38, 0.35)',
                    }}
                  >
                    {i + 1}
                  </span>
                  <div>
                    <div className="d-flex align-items-center gap-2 mb-2">
                      <i className={step.icon} style={{ color: '#CE1126', fontSize: 18 }} />
                      <Card.Title as="h6" className="mb-0" style={{ fontWeight: 600, color: '#1a1a1a' }}>
                        {step.title}
                      </Card.Title>
                    </div>
                    <Card.Text className="text-muted small mb-0" style={{ lineHeight: 1.55 }}>
                      {step.description}
                    </Card.Text>
                  </div>
                </div>
              </Card.Body>
            </Card>
          </Col>
        ))}
      </Row>

      <div className="text-center py-3">
        <Button
          size="lg"
          className="geoai-cta-btn px-5"
          onClick={() => navigate('/app/sataliteimage')}
        >
          <i className="feather icon-map me-2" />
          Open object detection
        </Button>
        <p className="text-muted small mt-3 mb-0">
          You will move to the GIS workspace with upload, model selection, and the interactive map.
        </p>
      </div>
    </div>
  );
}
