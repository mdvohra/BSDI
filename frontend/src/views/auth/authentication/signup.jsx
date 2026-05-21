import React from 'react';
import { Card, Row, Col } from 'react-bootstrap';
import { NavLink, Link } from 'react-router-dom';
import { GoogleOAuthProvider } from '@react-oauth/google';
import SignupPageGoogle from './signupwithgoogle';
import { MsalProvider} from '@azure/msal-react';
import SignupPageMicrosoft from './signupwithmicrosoft';
import { PublicClientApplication } from '@azure/msal-browser';
const SignUp1 = () => {
    const msalConfig = {
        auth: {
            clientId: "1250992d-6209-4071-8265-7e5fd4930e96", // Your client ID
            tenantId: "e68ed096-47c9-4775-9b02-eace0d83e235",
            authority: "https://login.microsoftonline.com/e68ed096-47c9-4775-9b02-eace0d83e235",
            redirectUri: "http://localhost:3000/signup",
        },
    };

    const onSuccessCallBack = (userInfo) => {
        console.log('User Info:', userInfo);
    };

    const msalInstance = new PublicClientApplication(msalConfig);
    return (
        <React.Fragment>
            {/* <Breadcrumb /> */}
            <div className="auth-wrapper">
                <div className="auth-content">
                    <div className="auth-bg">
                        <span className="r" />
                        <span className="r s" />
                        <span className="r s" />
                        <span className="r" />
                    </div>
                    <Card className="borderless">
                        <Row className="align-items-center">
                            <Col>
                                <Card.Body className="text-center">
                                    {/* <div className="mb-4">
                                        <i className="feather icon-user-plus auth-icon" />
                                    </div> */}
                                    <div className="mb-4">
                                        <span className="geoai-wordmark geoai-wordmark--on-light geoai-wordmark--lg">GeoAI</span>
                                    </div>
                                    <h3 className="mb-4">Sign up</h3>
                                    <div className="input-group mb-3">
                                        <input type="text" className="form-control" placeholder="Username" />
                                    </div>
                                    <div className="input-group mb-3">
                                        <input type="email" className="form-control" placeholder="Email address" />
                                    </div>
                                    <div className="input-group mb-4">
                                        <input type="password" className="form-control" placeholder="Password" />
                                    </div>
                                    <div className="input-group mb-4">
                                        <input type="password" className="form-control" placeholder="Confirm Password" />
                                    </div>
                                    {/* <div className="form-check  text-start mb-4 mt-2">
                    <input type="checkbox" className="form-check-input" id="customCheck1" defaultChecked={false} />
                    <label className="form-check-label" htmlFor="customCheck1">
                      Send me the <Link to="#"> Newsletter</Link> weekly.
                    </label>
                  </div> */}
                                    <button className="btn btn-primary mb-2">Sign up</button>
                                    {/* or signup using google or microsoft */}
                                    <p>
                                        Or Sign up using
                                    </p>
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
                                            <SignupPageMicrosoft />
                                        </MsalProvider>
                                    </div>
                                    <p className="mb-4">
                                        Already have an account?{' '}
                                        <NavLink to={'/login'} className="f-w-400">
                                            Login
                                        </NavLink>
                                    </p>
                                </Card.Body>
                            </Col>
                        </Row>
                    </Card>
                </div>
            </div>
        </React.Fragment>
    );
};

export default SignUp1;
