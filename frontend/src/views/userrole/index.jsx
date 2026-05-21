import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Row, Col, Card, Form, Button, Table } from 'react-bootstrap';

function AddUserRole() {
  const [tenantID, setTenantID] = useState('');
  const [roleName, setRoleName] = useState('');
  const [userRoles, setUserRoles] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [filteredUserRoles, setFilteredUserRoles] = useState([]);

  useEffect(() => {
    const fetchTenants = async () => {
      try {
        const response = await axios.get('Tenant');
        if (response.data && response.data.$values) {
          setTenants(response.data.$values);
        } else if (Array.isArray(response.data)) {
          setTenants(response.data);
        } else {
          console.error('Unexpected response format:', response.data);
        }
      } catch (error) {
        console.error('Error fetching tenants:', error);
      }
    };

    const fetchUserRoles = async () => {
      try {
        const response = await axios.get('UserRole');
        if (response.data && Array.isArray(response.data)) {
          setUserRoles(response.data);
        } else if (response.data && response.data.$values) {
          setUserRoles(response.data.$values);
        } else {
          console.error('Unexpected response format:', response.data);
        }
      } catch (error) {
        console.error('Error fetching user roles:', error);
      }
    };

    fetchTenants();
    fetchUserRoles();
  }, []);

  useEffect(() => {
    if (tenantID) {
      setFilteredUserRoles(userRoles.filter(role => role.tenantID === parseInt(tenantID)));
    } else {
      setFilteredUserRoles([]);
    }
  }, [tenantID, userRoles]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const response = await axios.post('UserRole', { tenantID, roleName });
      console.log('User role added:', response.data);
      setUserRoles([...userRoles, response.data]); // Update the user roles list with the new role
      setTenantID(''); // Clear the input field
      setRoleName(''); // Clear the input field
    } catch (error) {
      console.error('Error adding user role:', error);
    }
  };

  const handleDelete = async (roleID) => {
    try {
      await axios.delete(`UserRole/${roleID}`);
      setUserRoles(userRoles.filter(role => role.roleID !== roleID)); // Remove the deleted role from the list
    } catch (error) {
      console.error('Error deleting user role:', error);
    }
  };

  return (
    // <div>
    //   <form onSubmit={handleSubmit}>
    //     <div>
    //       <label>Tenant Name:</label>
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
    //       <label>Role Name:</label>
    //       <input
    //         type="text"
    //         value={roleName}
    //         onChange={(e) => setRoleName(e.target.value)}
    //         required
    //       />
    //     </div>
    //     <button type="submit">Add User Role</button>
    //   </form>
    //   <h2>Existing User Roles</h2>
    //   <ul>
    //     {filteredUserRoles.map((role) => (
    //       <li key={role.roleID}>
    //         {role.roleName} (Tenant ID: {role.tenantID})
    //         <button onClick={() => handleDelete(role.roleID)}>Delete</button>
    //       </li>
    //     ))}
    //   </ul>
    // </div>
    // add user role form with react-bootstrap components and good styling
    <>
      <Row>
        <Col>
          <Card>
            <Card.Header>
              <Card.Title as="h5">Add User Role</Card.Title>
            </Card.Header>
            <Card.Body>
              <Form onSubmit={handleSubmit}>
                <Row>
                  <Col md={6}>
                    <Form.Group controlId="tenantID">
                      <Form.Label>Tenant Name</Form.Label>
                      <Form.Control
                        as="select"
                        value={tenantID}
                        onChange={(e) => setTenantID(e.target.value)}
                        required
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
                  <Col md={6}>
                    <Form.Group controlId="roleName">
                      <Form.Label>Role Name</Form.Label>
                      <Form.Control
                        type="text"
                        placeholder="Enter role name"
                        value={roleName}
                        onChange={(e) => setRoleName(e.target.value)}
                        required
                      />
                    </Form.Group>
                  </Col>
                </Row>
                {/* space between button and form */}
                <Button
                style={{
                    marginTop: '1rem'
                }}
                type="submit">Add User Role</Button>
              </Form>
            </Card.Body>
          </Card>
        </Col>
      </Row>
      <Row>
        <Col>
          <Card>
            <Card.Body>
              <Table responsive hover>
                <thead>
                  <tr>
                    <th>Role Name</th>
                    <th>Tenant ID</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUserRoles.map((role) => (
                    <tr key={role.roleID}>
                      <td>{role.roleName}</td>
                      <td>{role.tenantID}</td>
                      <td>
                        <Button
                          variant="danger"
                          onClick={() => handleDelete(role.roleID)}
                        >
                          Delete
                        </Button>
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

export default AddUserRole;