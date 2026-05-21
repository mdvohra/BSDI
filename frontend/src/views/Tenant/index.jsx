import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Row, Col, Card, Form, Button, InputGroup, FormControl, DropdownButton, Dropdown } from 'react-bootstrap';

function AddTenant() {
    const [tenantName, setTenantName] = useState('');
    const [tenants, setTenants] = useState([]);
    useEffect(() => {
        const fetchTenants = async () => {
            try {
                const response = await axios.get('Tenant');
                if (response.data && response.data.$values) {
                    setTenants(response.data.$values);
                } else {
                    console.error('Unexpected response format:', response.data);
                }
            } catch (error) {
                console.error('Error fetching tenants:', error);
            }
        };

        fetchTenants();
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            const response = await axios.post('Tenant', { tenantName });
            console.log('Tenant added:', response.data);
            setTenants([...tenants, response.data]); // Update the tenants list with the new tenant
            setTenantName(''); // Clear the input field
        } catch (error) {
            console.error('Error adding tenant:', error);
        }
    };



    return (
        //     <div>
        //         <h1>Tenants</h1>
        //         <form onSubmit={handleSubmit}>
        //             <input
        //                 type="text"
        //                 value={tenantName}
        //                 onChange={(e) => setTenantName(e.target.value)}
        //                 placeholder="Enter tenant name"
        //             />
        //             <button type="submit">Add Tenant</button>
        //         </form>
        //         <ul>
        //     {tenants.map((tenant) => (
        //       <li key={tenant.tenantID}>{tenant.tenantName}</li>
        //     ))}
        //   </ul>
        //     </div>
        // add tenant form with react-bootstrap components and good styling
        <>
            <Row>
                <Col>
                    <Card>
                        <Card.Header>
                            <Card.Title as="h5">Add Tenant</Card.Title>
                        </Card.Header>
                        <Card.Body>
                            <Form onSubmit={handleSubmit}>
                                <Row>
                                    <Col md={6}>
                                        <Form.Group controlId="tenantName">
                                            <Form.Label>Tenant Name</Form.Label>
                                            <Form.Control
                                                type="text"
                                                placeholder="Enter tenant name"
                                                value={tenantName}
                                                onChange={(e) => setTenantName(e.target.value)}
                                            />
                                        </Form.Group>
                                    </Col>
                                </Row>
                                <Button
                                // space between button and form
                                    style={{ marginTop: '1rem' }}
                                variant="primary" type="submit">
                                    Add Tenant
                                </Button>
                            </Form>
                        </Card.Body>
                    </Card>
                </Col>
            </Row>
            <Row>
                <Col>
                    <Card>
                        <Card.Header>
                            <Card.Title as="h5">Tenants</Card.Title>
                        </Card.Header>
                        <Card.Body>
                            <ul>
                                {tenants.map((tenant) => (
                                    <li key={tenant.tenantID}>{tenant.tenantName}</li>
                                ))}
                            </ul>
                        </Card.Body>
                    </Card>
                </Col>
            </Row>
        </>
    );

}


export default AddTenant;