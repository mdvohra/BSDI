import React from 'react';
import { Row, Col, Card, Button } from 'react-bootstrap';
import { useNavigate } from 'react-router-dom';
import { useUiConfig } from '../contexts/UiConfigContext';
import Loader from './Loader/Loader';

const cardStyle = {
  border: '1px solid rgba(206, 17, 38, 0.2)',
  borderRadius: 12,
  height: '100%',
  boxShadow: '0 4px 20px rgba(206, 17, 38, 0.08)',
  background: '#fff',
};

const featuresMeta = [
  {
    id: 'gis',
    title: 'GIS object detection',
    description:
      'Upload orthoimagery or GeoTIFFs, draw regions of interest, and run building or object detection with interactive maps and exports.',
    path: '/app/sataliteimage',
    icon: 'feather icon-map',
    always: true,
    flag: null,
  },
  {
    id: 'sr',
    title: 'Super resolution',
    description:
      'Upscale satellite or aerial imagery with deep-learning super-resolution for clearer downstream analysis.',
    path: '/app/superResolution',
    icon: 'feather icon-maximize-2',
    flag: 'show_super_resolution',
  },
  {
    id: 'lulc',
    title: 'Land cover (LULC)',
    description:
      'Classify land use and land cover from imagery; compare runs and link results with detection workflows.',
    path: '/app/lulc',
    icon: 'feather icon-layers',
    flag: 'show_lulc',
  },
  {
    id: 'analysis',
    title: 'Analysis',
    description:
      'Inspect saved runs, shallow comparisons, LULC change analysis, and assistants over your catalog.',
    path: '/app/analysis',
    icon: 'feather icon-bar-chart-2',
    flag: 'show_analysis',
  },
  {
    id: 'pdf',
    title: 'Documents & PDF Q&A',
    description:
      'Query PDFs, spreadsheets, and structured data with LLM-assisted workflows.',
    path: '/app/pdfquery',
    icon: 'feather icon-file-text',
    always: true,
    flag: null,
  },
];

export default function DashboardFeatureGrid() {
  const navigate = useNavigate();
  const { uiConfig, loading } = useUiConfig();

  if (loading) {
    return <Loader />;
  }

  const visible = featuresMeta.filter((f) => {
    if (f.always) return true;
    if (f.flag && uiConfig[f.flag]) return true;
    return false;
  });

  return (
    <Row className="g-4 geoai-feature-grid">
      {visible.map((f) => (
        <Col key={f.id} md={6} xl={4}>
          <Card style={cardStyle} className="geoai-feature-card h-100">
            <Card.Body className="d-flex flex-column">
              <div className="d-flex align-items-start gap-3 mb-3">
                <span
                  className="rounded-circle d-inline-flex align-items-center justify-content-center"
                  style={{
                    width: 48,
                    height: 48,
                    background: 'rgba(206, 17, 38, 0.1)',
                    color: '#CE1126',
                  }}
                >
                  <i className={f.icon} style={{ fontSize: 22 }} />
                </span>
                <div>
                  <Card.Title as="h5" style={{ color: '#1a1a1a', fontWeight: 600 }}>
                    {f.title}
                  </Card.Title>
                </div>
              </div>
              <Card.Text style={{ color: '#555', flex: 1, fontSize: 14, lineHeight: 1.55 }}>
                {f.description}
              </Card.Text>
              <Button
                variant="primary"
                className="mt-3 align-self-start geoai-cta-btn"
                onClick={() => navigate(f.path)}
              >
                Open
              </Button>
            </Card.Body>
          </Card>
        </Col>
      ))}
    </Row>
  );
}
