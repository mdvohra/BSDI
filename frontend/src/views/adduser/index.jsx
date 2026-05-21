import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Row, Col, Card, Form, Button } from 'react-bootstrap';
function AddUser() {
    const [userName, setUserName] = useState('');
    const [password, setPassword] = useState('');
    const [email, setEmail] = useState('');
    const [tenantID, setTenantID] = useState('');
    const [roleID, setRoleID] = useState('');
    const [tenants, setTenants] = useState([]);
    const [roles, setRoles] = useState([]);

    useEffect(() => {
        const fetchTenants = async () => {
            try {
                const response = await axios.get('Tenant');
                setTenants(response.data.$values || response.data);
            } catch (error) {
                console.error('Error fetching tenants:', error);
            }
        };

        const fetchRoles = async () => {
            try {
                const response = await axios.get('UserRole');
                setRoles(response.data.$values || response.data);
            } catch (error) {
                console.error('Error fetching roles:', error);
            }
        };

        fetchTenants();
        fetchRoles();
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        const newUser = {
            userName,
            password,
            email,
            tenantID: parseInt(tenantID),
            roleID: parseInt(roleID),
            createdAt: new Date().toISOString(),
            isMicrosoftLogin: false,
            isGoogleLogin: false,
            microsoftId: '',
            googleId: ''
        };

        try {
            const response = await axios.post('User', newUser);
            console.log('User added:', response.data);
            alert('User added successfully');
            // Clear the form
            setUserName('');
            setPassword('');
            setEmail('');
            setTenantID('');
            setRoleID('');
        } catch (error) {
            console.error('Error adding user:', error);
        }
    };

    return (
        // <div>
        //   <form onSubmit={handleSubmit}>
        //     <div>
        //       <label>User Name:</label>
        //       <input
        //         type="text"
        //         value={userName}
        //         onChange={(e) => setUserName(e.target.value)}
        //         required
        //       />
        //     </div>
        //     <div>
        //       <label>Password:</label>
        //       <input
        //         type="password"
        //         value={password}
        //         onChange={(e) => setPassword(e.target.value)}
        //         required
        //       />
        //     </div>
        //     <div>
        //       <label>Email:</label>
        //       <input
        //         type="email"
        //         value={email}
        //         onChange={(e) => setEmail(e.target.value)}
        //         required
        //       />
        //     </div>
        //     <div>
        //       <label>Tenant:</label>
        //       <select
        //         value={tenantID}
        //         onChange={(e) => setTenantID(e.target.value)}
        //         required
        //       >
        //         <option value="">Select Tenant</option>
        //         {tenants.map((tenant) => (
        //           <option key={tenant.tenantID} value={tenant.tenantID}>
        //             {tenant.tenantName}
        //           </option>
        //         ))}
        //       </select>
        //     </div>
        //     <div>
        //       <label>User Role:</label>
        //       <select
        //         value={roleID}
        //         onChange={(e) => setRoleID(e.target.value)}
        //         required
        //       >
        //         <option value="">Select Role</option>
        //         {roles.map((role) => (
        //           <option key={role.roleID} value={role.roleID}>
        //             {role.roleName}
        //           </option>
        //         ))}
        //       </select>
        //     </div>
        //     <button type="submit">Add User</button>
        //   </form>
        // </div>
        // add user form with react-bootstrap components and good styling
        <>
            <Row>
                <Col>
                    <Card>
                        <Card.Header>
                            <Card.Title as="h5">Add User</Card.Title>
                        </Card.Header>
                        <Card.Body>
                            <Form onSubmit={handleSubmit}>
                                <Row>
                                    <Col md={6}>
                                        <Form.Group controlId="userName">
                                            <Form.Label>User Name</Form.Label>
                                            <Form.Control
                                                type="text"
                                                placeholder="Enter user name"
                                                value={userName}
                                                onChange={(e) => setUserName(e.target.value)}
                                            />
                                        </Form.Group>
                                    </Col>
                                    <Col md={6}>
                                        <Form.Group controlId="password">
                                            <Form.Label>Password</Form.Label>
                                            <Form.Control
                                                type="password"
                                                placeholder="Enter password"
                                                value={password}
                                                onChange={(e) => setPassword(e.target.value)}
                                            />
                                        </Form.Group>
                                    </Col>
                                </Row>
                                <Row>
                                    <Col md={6}>
                                        <Form.Group controlId="email">
                                            <Form.Label>Email</Form.Label>
                                            <Form.Control
                                                type="email"
                                                placeholder="Enter email"
                                                value={email}
                                                onChange={(e) => setEmail(e.target.value)}
                                            />
                                        </Form.Group>
                                    </Col>
                                    <Col md={6}>
                                        <Form.Group controlId="tenantID">
                                            <Form.Label>Tenant</Form.Label>
                                            <Form.Control
                                                as="select"
                                                value={tenantID}
                                                onChange={(e) => setTenantID(e.target.value)}
                                            >
                                                <option value="">Select Tenant</option>
                                                {tenants.map((tenant) => (
                                                    <option key={tenant.tenantID} value={tenant.tenantID}>
                                                        {tenant.tenantName}
                                                    </option>
                                                ))}
                                            </Form.Control>
                                        </Form.Group>
                                    </Col>
                                </Row>
                                <Row>
                                    <Col md={6}>
                                        <Form.Group controlId="roleID">
                                            <Form.Label>User Role</Form.Label>
                                            <Form.Control
                                                as="select"
                                                value={roleID}
                                                onChange={(e) => setRoleID(e.target.value)}
                                            >
                                                <option value="">Select Role</option>
                                                {roles.map((role) => (
                                                    <option key={role.roleID} value={role.roleID}>
                                                        {role.roleName}
                                                    </option>
                                                ))}
                                            </Form.Control>
                                        </Form.Group>
                                    </Col>
                                </Row>
                                <Button
                                    style={{
                                        marginTop: '1rem'
                                    }}
                                    type="submit">Add User</Button>
                            </Form>
                        </Card.Body>
                    </Card>
                </Col>
            </Row>
        </>
    );
}

export default AddUser;