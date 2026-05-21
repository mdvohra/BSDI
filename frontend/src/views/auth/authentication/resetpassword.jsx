import React from 'react';
import { Card, Row, Col } from 'react-bootstrap';
import { NavLink, Link } from 'react-router-dom';
import Breadcrumb from '../../../layouts/AdminLayout/Breadcrumb';

const Resetpassword = () => {
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
                                    <h3 className="mb-4">Reset Password</h3>
                                    <div className="input-group mb-3">
                                        <input type="password" className="form-control" placeholder="Enter New Password" />
                                    </div>
                                    <div className="input-group mb-3">
                                        <input type="password" className="form-control" placeholder="Confirm Password" />
                                    </div>
                                    
                                    <button className="btn btn-primary mb-4">Reset Password</button>
                                    {/* <p className="mb-2">
                                        Already have an account?{' '}
                                        <NavLink to={'/auth/signin-1'} className="f-w-400">
                                            Login
                                        </NavLink>
                                    </p> */}
                                </Card.Body>
                            </Col>
                        </Row>
                    </Card>
                </div>
            </div>
        </React.Fragment>
    );
};

export default Resetpassword;
