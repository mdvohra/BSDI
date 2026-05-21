import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Card, Modal, Button } from 'react-bootstrap';
import Breadcrumb from '../../../layouts/AdminLayout/Breadcrumb';
import AuthLogin from './jwtlogin';
import { GoogleOAuthProvider } from '@react-oauth/google';
import SignupPageGoogle from './signupwithgoogle';
import SignupPageMicrosoft from './signupwithmicrosoft'
import { MsalProvider } from '@azure/msal-react';
import { PublicClientApplication } from '@azure/msal-browser';
import axios from 'axios';
import { getApiBaseUrl } from '../../../config/apiBase';
const UserLogin = () => {
  const [email, setEmail] = useState('user@example.com');
  const [password, setPassword] = useState('string');
  const [ispopup, setPopup] = useState(false);


  const onSuccessCallBack = (userInfo) => {
    console.log('User Info:', userInfo);
    setPopup(true);
  };

  const msalConfig = {
    auth: {
      clientId: "1250992d-6209-4071-8265-7e5fd4930e96", // Your client ID
      tenantId: "e68ed096-47c9-4775-9b02-eace0d83e235",
      authority: "https://login.microsoftonline.com/e68ed096-47c9-4775-9b02-eace0d83e235",
      redirectUri: "http://localhost:3000/signup",
    },
  };
  const msalInstance = new PublicClientApplication(msalConfig);


  const handleAdminSubmit = async () => {
    // console.log('Form submitted'); // Debugging statement
    // console.log('Email:', email); // Debug statement
    // console.log('Password:', password); // Debugging statement
    try {
      const response = await axios.post(`${getApiBaseUrl()}/Auth/login`, { email, password });
      console.log('API response:', response.data); // Debugging statement
      if (response.data && response.data.token) {
        localStorage.setItem('token', response.data.token);
        localStorage.setItem('role', 'admin');
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

  const handleUserSubmit = async () => {
    // console.log('Form submitted'); // Debugging statement
    // console.log('Email:', email); // Debug statement
    // console.log('Password:', password); // Debugging statement
    try {
      const response = await axios.post(`${getApiBaseUrl()}/Auth/login`, { email, password });
      console.log('API response:', response.data); // Debugging statement
      if (response.data && response.data.token) {
        localStorage.setItem('token', response.data.token);
        localStorage.setItem('role', 'user');
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
    <React.Fragment>
      <Breadcrumb />
      <div className="auth-wrapper">
        <div className="auth-content">
          <div className="auth-bg">
            <span className="r" />
            <span className="r s" />
            <span className="r s" />
            <span className="r" />
          </div>
          <Card className="borderless text-center">
            <Card.Body>
              {/* <div className="mb-4">
                <i className="feather icon-unlock auth-icon" />
              </div> */}
              <div className="mb-4">
                <span className="geoai-wordmark geoai-wordmark--on-light geoai-wordmark--lg">GeoAI</span>
              </div>
              <AuthLogin />
              <div
                style={{
                  marginBottom: '10px',
                }}
              >
                <div
                  style={{
                    marginTop: '10px',
                    display: 'flex',
                    flexDirection: 'row',
                    justifyContent: 'center',
                  }}
                >
                  <GoogleOAuthProvider clientId="164562022002-v3jvsmt5tpaomhrt04qs0aanasu17faj.apps.googleusercontent.com">
                    <SignupPageGoogle onSuccessCallBack={onSuccessCallBack} />
                  </GoogleOAuthProvider>
                  <MsalProvider instance={msalInstance}>
                    <SignupPageMicrosoft onSuccessCallBack={onSuccessCallBack} />
                  </MsalProvider>
                </div>
              </div>
              <p className="mb-2 text-muted">
                Forgot password?{' '}
                <NavLink to='/passwordreset/mail' className="f-w-400">
                  Reset
                </NavLink>
              </p>
              <p className="mb-0 text-muted">
                Don’t have an account?{' '}
                <NavLink to="/signup" className="f-w-400">
                  Signup
                </NavLink>
              </p>
              {/* a div container wiht google facebook and microsoft logo  */}
            </Card.Body>
          </Card>
        </div>
      </div>

      {/* Popup Modal for Role Selection */}
      <Modal show={ispopup} onHide={() => setPopup(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Select Role</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <div className="d-flex justify-content-around">
            <Button variant="primary" onClick={() => { setPopup(false); handleUserSubmit(); }}>
              User
            </Button>
            <Button variant="secondary" onClick={() => { setPopup(false); handleAdminSubmit(); }}>
              Admin
            </Button>
          </div>
        </Modal.Body>
      </Modal>
    </React.Fragment>
  );
};

export default UserLogin;
