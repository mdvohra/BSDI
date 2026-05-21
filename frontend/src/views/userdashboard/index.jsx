import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Table, Container } from 'react-bootstrap';
import ObjectDetectionProcessPanel from '../../components/ObjectDetectionProcessPanel';

function UserDashboard() {
  const [useCases, setUseCases] = useState([]);

  useEffect(() => {
    const fetchUseCases = async () => {
      try {
        const response = await axios.get('UseCase');
        setUseCases(response.data.$values);
      } catch (error) {
        console.error('Error fetching use cases:', error);
      }
    };

    fetchUseCases();
  }, []);

  return (
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
          <strong style={{ color: '#333' }}>Object detection</strong> workflow—same steps as the admin view. Your
          assigned use cases appear below.
        </p>
      </div>

      <h4 className="mb-3" style={{ fontWeight: 600, color: '#333' }}>
        Process
      </h4>
      <p className="text-muted mb-4" style={{ maxWidth: 900 }}>
        How to run detection from upload through export. Use the button at the bottom to open the live workspace.
      </p>

      <ObjectDetectionProcessPanel />

      <div className="mt-5">
        <h4 className="mb-3" style={{ fontWeight: 600, color: '#333' }}>
          Use cases
        </h4>
        <Table striped bordered hover responsive className="bg-white">
          <thead>
            <tr>
              <th>Use Case Name</th>
              <th>Created At</th>
            </tr>
          </thead>
          <tbody>
            {useCases.map((useCase) => (
              <tr key={useCase.useCaseID}>
                <td>{useCase.useCaseName}</td>
                <td>{new Date(useCase.createdAt).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </Container>
  );
}

export default UserDashboard;
