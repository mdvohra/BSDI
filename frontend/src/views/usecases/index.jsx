import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Row, Col, Card, Form, Button, Table } from 'react-bootstrap';

function AddUseCase() {
  const [useCaseName, setUseCaseName] = useState('');
  const [adminID, setAdminID] = useState(1);
  const [useCases, setUseCases] = useState([]);

  useEffect(() => {
    fetchUseCases();
  }, []);

  const fetchUseCases = async () => {
    try {
      const response = await axios.get('UseCase');
      setUseCases(response.data.$values); // Access the array of use cases
    } catch (error) {
      console.error('Error fetching use cases:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const newUseCase = {
        useCaseName,
        adminID: parseInt(adminID),
        createdAt: new Date().toISOString()
      };
      await axios.post('UseCase', newUseCase);
      alert('Use case added successfully');
      setUseCaseName('');
      setAdminID('');
      fetchUseCases(); // Refresh the list of use cases
    } catch (error) {
      console.error('Error adding use case:', error);
    }
  };

  const handleDeleteUseCase = async (useCaseID) => {
    try {
      await axios.delete(`UseCase/${useCaseID}`);
      fetchUseCases(); // Refresh the list of use cases
    } catch (error) {
      console.error('Error deleting use case:', error);
    }
  };

  return (
    // <div>
    //   <form onSubmit={handleSubmit}>
    //     <div>
    //       <label>Use Case Name:</label>
    //       <input
    //         type="text"
    //         value={useCaseName}
    //         onChange={(e) => setUseCaseName(e.target.value)}
    //         required
    //       />
    //     </div>
    //     <div>
    //       <label>Admin ID:</label>
    //       <input
    //         type="number"
    //         value={adminID}
    //         onChange={(e) => setAdminID(e.target.value)}
    //         required
    //       />
    //     </div>
    //     <button type="submit">Add Use Case</button>
    //   </form>
    //   <h2>Existing Use Cases</h2>
    //   <ul>
    //     {useCases.map((useCase) => (
    //       <li key={useCase.useCaseID}>
    //         <h3>{useCase.useCaseName}</h3>
    //         <p>Created At: {new Date(useCase.createdAt).toLocaleString()}</p>
    //         <button onClick={() => handleDeleteUseCase(useCase.useCaseID)}>Delete</button>
    //       </li>
    //     ))}
    //   </ul>
    // </div>
    // add use case form with react-bootstrap components and good styling
    <>
      <Row>
        <Col>
          <Card>
            <Card.Header>
              <Card.Title as="h5">Add Use Case</Card.Title>
            </Card.Header>
            <Card.Body>
              <Form onSubmit={handleSubmit}>
                <Row>
                  <Col md={8}>
                    <Form.Group controlId="useCaseName">
                      <Form.Label>Use Case Name</Form.Label>
                      <Form.Control
                        type="text"
                        placeholder="Enter use case name"
                        value={useCaseName}
                        onChange={(e) => setUseCaseName(e.target.value)}
                      />
                    </Form.Group>
                  </Col>
                  {/* <Col md={6}>
                    <Form.Group controlId="adminID">
                      <Form.Label>Admin ID</Form.Label>
                      <Form.Control
                        type="number"
                        placeholder="Enter admin ID"
                        value={adminID}
                        onChange={(e) => setAdminID(e.target.value)}
                      />
                    </Form.Group>
                  </Col> */}
                </Row>
                {/* space between button and form */}
                <Button
                style={{
                    marginTop: '1rem'
                }}
                type="submit">Add Use Case</Button>
              </Form>
            </Card.Body>
          </Card>
        </Col>
      </Row>
      <Row>
        <Col>
          <Card>
            <Card.Body>
              <h2>Existing Use Cases</h2>
              <Table striped bordered hover>
                <thead>
                  <tr>
                    <th>Use Case Name</th>
                    <th>Created At</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {useCases.map((useCase) => (
                    <tr key={useCase.useCaseID}>
                      <td>{useCase.useCaseName}</td>
                      <td>{new Date(useCase.createdAt).toLocaleString()}</td>
                      <td>
                        <Button variant="danger" onClick={() => handleDeleteUseCase(useCase.useCaseID)}>Delete</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </>
  );
}

export default AddUseCase;