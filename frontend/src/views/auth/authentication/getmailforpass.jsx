import React from 'react';
import { Card, Row, Col } from 'react-bootstrap';
import { NavLink, Link } from 'react-router-dom';
import Breadcrumb from '../../../layouts/AdminLayout/Breadcrumb';
import { useNavigate } from 'react-router-dom';
const Email = () => {
    const navigate = useNavigate();
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
                                    <h3 className="mb-4">Registered Mail ID</h3>
                                    <div className="input-group mb-3">
                                        <input type="email" className="form-control" placeholder="Email address" />
                                    </div>
                                    <button 
                                     className="btn btn-primary mb-4"
                                     onClick={() => {
                                        navigate('/resetpassword/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5');
                                    }}
                                     >Get Passowrd Reset Link</button>
                                </Card.Body>
                            </Col>
                        </Row>
                    </Card>
                </div>
            </div>
        </React.Fragment>
    );
};

export default Email;
