import React,{useState} from 'react';
import { Row, Col, Alert, Button } from 'react-bootstrap';
import * as Yup from 'yup';
import { Formik } from 'formik';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { getApiBaseUrl } from '../../../config/apiBase';
const JWTLogin = () => {
    const [email, setEmail] = useState('user@example.com');
    const [password, setPassword] = useState('string');
    const navigate = useNavigate();
    const handleAdminSubmit = async (e) => {
      e.preventDefault();
      // console.log('Form submitted'); // Debugging statement
      // console.log('Email:', email); // Debug statement
      // console.log('Password:', password); // Debugging statement
      try {
        const response = await axios.post(`${getApiBaseUrl()}/Auth/login`, { email, password });
        console.log('API response:', response.data); // Debugging statement
        if (response.data && response.data.token) {
          localStorage.setItem('token', response.data.token);
          localStorage.setItem('role', 'admin');
          localStorage.setItem('loginMethod','normal');
          // navigate('/app/admin/dashboard/');
          // navigate(0)
          window.location.href = '/app/admin/dashboard/';
        } else {
          console.error('Invalid login response', response.data);
        }
      } catch (error) {
        console.error('Login failed', error);
      }
    };
    const handleUserSubmit = async (e) => {
      e.preventDefault();
      // console.log('Form submitted'); // Debugging statement
      // console.log('Email:', email); // Debug statement
      // console.log('Password:', password); // Debugging statement
      try {
        const response = await axios.post(`${getApiBaseUrl()}/Auth/login`, { email, password });
        console.log('API response:', response.data); // Debugging statement
        if (response.data && response.data.token) {
          localStorage.setItem('token', response.data.token);
          localStorage.setItem('role', 'user');
          localStorage.setItem('loginMethod','normal');
          // navigate('/app/userdashboard/');
          // navigate(0)
          window.location.href = '/app/userdashboard/';
        } else {
          console.error('Invalid login response', response.data);
        }
      } catch (error) {
        console.error('Login failed', error);
      }
    };
  
  return (
    <Formik
      initialValues={{
        email: 'user@example.com',
        password: 'string',
        submit: null
      }}
      validationSchema={Yup.object().shape({
        email: Yup.string().email('Must be a valid email').max(255).required('Email is required'),
        password: Yup.string().max(255).required('Password is required')
      })}
    >
      {({ errors, handleBlur, handleChange, isSubmitting, touched, values }) => (
        <form noValidate>
          <div className="form-group mb-3">
            <input
              className="form-control"
              label="Email Address / Username"
              name="email"
              onBlur={handleBlur}
              onChange={handleChange}
              type="email"
              value={values.email}
            />
            {touched.email && errors.email && <small className="text-danger form-text">{errors.email}</small>}
          </div>
          <div className="form-group mb-4">
            <input
              className="form-control"
              label="Password"
              name="password"
              onBlur={handleBlur}
              onChange={handleChange}
              type="password"
              value={values.password}
            />
            {touched.password && errors.password && <small className="text-danger form-text">{errors.password}</small>}
          </div>

          <div className="custom-control custom-checkbox  text-start mb-4 mt-2">
            <input type="checkbox" className="custom-control-input mx-2" id="customCheck1" />
            <label className="custom-control-label" htmlFor="customCheck1">
              Save credentials.
            </label>
          </div>

          {errors.submit && (
            <Col sm={12}>
              <Alert>{errors.submit}</Alert>
            </Col>
          )}

          <Row>
            <Col>
              <Button className="btn-block mb-4" color="primary" onClick={(e)=>handleUserSubmit(e)} size="sm" type="submit" variant="primary">
                Login as User
              </Button>
            </Col>
            <Col>
              <Button className="btn-block mb-4" color="primary" onClick={(e)=>handleAdminSubmit(e)} size="sm" type="submit" variant="primary">
                Login as Admin
              </Button>
            </Col>
          </Row>
        </form>
      )}
    </Formik>
  );
};

export default JWTLogin;
