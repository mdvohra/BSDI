import React, { useState } from 'react';
import { Navbar, Nav, Container, Button, Row, Col, Card, NavDropdown } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useNavigate } from 'react-router-dom';
function App() {
  const [isHovered, setIsHovered] = useState(false);
  const navigate = useNavigate();
  const role = localStorage.getItem('role');
  const goToDashboard = () => {
    if (role === 'admin') {
      navigate('/app/admin/dashboard/')
    }
    else {
      navigate('/app/userdashboard')
    }
  }
  return (
    <div className="App">
      {/* Fixed Navbar Component */}
      <Navbar
        style={{
          backgroundColor: '#ffffff',
          borderBottom: '1px solid rgba(206, 17, 38, 0.12)',
          height: '70px',
          position: 'fixed',  // Make the navbar fixed
          top: 0,             // Stick to the top
          width: '100%',      // Full width
          zIndex: 1000,       // Ensure it stays on top of other content
        }}
        expand="lg"
      >
        <Container>
          <Navbar.Brand href="#home">
            <div className="navbar-brand header-logo">
              <Link to="#" className="b-brand" style={{ textDecoration: 'none' }}>
                <span className="geoai-wordmark geoai-wordmark--on-light">GeoAI</span>
              </Link>
            </div>
          </Navbar.Brand>
          <Navbar.Toggle aria-controls="basic-navbar-nav" />
          <Navbar.Collapse id="basic-navbar-nav">
            {/* Move Nav to the right using ms-auto */}
            <Nav className="ms-auto" style={{ fontSize: '15px' }}>
              <Nav.Link
                style={{
                  color: '#333333',
                  fontSize: '15px',
                  fontWeight: 'bold',
                }}
                onClick={goToDashboard}>Dashboard</Nav.Link>

              {/* Dropdown for Features */}
              <NavDropdown
                title={
                  <span
                    style={{
                      color: '#333333',
                      fontSize: '15px',
                      fontWeight: 'bold',
                    }}
                  >Solutions</span>
                } id="features-dropdown">
                <NavDropdown.Item onClick={() => navigate('/app/pdfquery')}>Language Based Models</NavDropdown.Item>
                <NavDropdown.Item href="#action/1">Computer Vision</NavDropdown.Item>
                <NavDropdown.Item href="#action/2">GeoSpatial Analysis</NavDropdown.Item>
              </NavDropdown>

              <Nav.Link
                style={{
                  color: '#333333',
                  fontSize: '15px',
                  fontWeight: 'bold',
                }}
                href="https://www.braein.com/connect-us.html">Contact Us</Nav.Link>
              <Nav.Link
                // change the color of the button when hovered
                onMouseEnter={() => setIsHovered(true)}
                onMouseLeave={() => setIsHovered(false)}
                style={{
                  fontSize: '15px',
                  fontWeight: 'bold',
                  backgroundColor: isHovered ? '#a50e1f' : '#CE1126',
                  color: '#ffffff',
                  borderRadius: '5px',
                }}

                href='/login'
              >Get Started</Nav.Link>
            </Nav>
          </Navbar.Collapse>
        </Container>
      </Navbar>

      {/* Add padding or margin to prevent content being hidden behind the fixed navbar */}
      <div style={{ marginTop: '120px' }}>
        {/* Header Section */}
        <div
          className="text-center p-5t" style={{ marginBottom: '20px' }}> {/* Adjusted margin-bottom */}
          <h1>Welcome to GeoAI</h1>
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
            }}
          >
            <p
              style={{
                fontSize: '20px',
                color: '#6c757d',
                marginBottom: '20px',
                width: '60%',
              }}
            >
              GeoAI brings geospatial intelligence and AI-powered mapping to government and enterprise teams.
            </p>
          </div>
          {/* <Button variant="primary" onClick={() => navigate('/login')}>Get Started</Button> */}
        </div>

        {/* Cards Section */}
        <Container className="my-5">
          {/* <Row>
            <video autoPlay loop='1' muted
              style={{
                position: 'relative',
                right: 0,
                bottom: 0,
                minWidth: "100%",
                minHeight: "100%",
            }}
            >
            <source src="https://www.braein.com/images/home/banner/video.mp4" type="video/mp4" />
            Your browser does not support the video tag.
          </video>
          <Col>
            <img src='https://www.braein.com/images/home/banner/pic1_2.png' style={{ width: '100%', height: 'auto' }} />
          </Col>
          <Col>
            <img src='https://www.braein.com/images/home/banner/pic2.png' style={{ width: '100%', height: 'auto' }} />
          </Col>

          <Col>
            <img src='https://www.braein.com/images/home/banner/pic3.png' style={{ width: '100%', height: 'auto' }} />
          </Col>
        </Row> */}
          <h2 style={{ marginTop: '0px' }} className="text-center mb-4">Our Services</h2>
          <Row>
            <Col>
              <Card
                onClick={() => navigate('/app/pdfquery')}
                style={{ cursor: 'pointer' }}>
                <Card.Header>
                  <Card.Title as="h5">LLM for Data Files like PDF, Excel, CSV</Card.Title>
                  <i className="feather icon-file-text" />
                </Card.Header>
                <Card.Body>
                  <Card.Text>
                    Large Language Models (LLMs) are neural networks that can be trained on large text data sets. They are used in applications like chatbots, language translation, and text summarization for handling documents like PDFs, Excel, and CSV files.
                  </Card.Text>
                </Card.Body>
              </Card>
            </Col>
            <Col>
              <Card style={{ cursor: 'pointer' }}>
                <Card.Header>
                  <Card.Title as="h5">Computer Vision Services</Card.Title>
                  <i className="feather icon-eye" />
                </Card.Header>
                <Card.Body>
                  <Card.Text>
                    Computer vision is an interdisciplinary field that deals with how computers can gain high-level understanding from digital images or videos. It seeks to understand and automate tasks that the human visual system can do.
                  </Card.Text>
                </Card.Body>
              </Card>
            </Col>

            <Col>
              <Card style={{ cursor: 'pointer' }}>
                <Card.Header>
                  <Card.Title as="h5">GIS Analysis</Card.Title>
                  <i className="feather icon-map" />
                </Card.Header>
                <Card.Body>
                  <Card.Text>
                    A Geographic Information System (GIS) is a framework that provides the ability to capture and analyze spatial and geographic data. It allows users to create interactive queries, store and edit spatial and non-spatial data, and analyze geographic information.
                  </Card.Text>
                </Card.Body>
              </Card>
            </Col>

          </Row>
          {/* <Row>
          <Col>
            <Card style={{ cursor: 'pointer' }}>
              <Card.Header>
                <Card.Title as="h5">Speech Recognition</Card.Title>
                <i className="feather icon-mic" />
              </Card.Header>
              <Card.Body>
                <Card.Text>
                  Speech recognition is an interdisciplinary subfield of computer science and computational linguistics that develops methodologies and technologies that enable the recognition and translation of spoken language into text by computers.
                </Card.Text>
              </Card.Body>
            </Card>
          </Col>

          <Col>
            <Card style={{ cursor: 'pointer' }}>
              <Card.Header>
                <Card.Title as="h5">Predictive Analytics</Card.Title>
                <i className="feather icon-trending-up" />
              </Card.Header>
              <Card.Body>
                <Card.Text>
                  Predictive analytics is the use of data, statistical algorithms, and machine learning techniques to identify the likelihood of future outcomes based on historical data. The goal is to go beyond knowing what has happened to providing a best assessment of what will happen in the future.
                </Card.Text>
              </Card.Body>
            </Card>
          </Col>

          <Col>
            <Card style={{ cursor: 'pointer' }}>
              <Card.Header>
                <Card.Title as="h5">Live Monitoring Intelligence Dashboards</Card.Title>
                <i className="feather icon-monitor" />
              </Card.Header>
              <Card.Body>
                <Card.Text>
                  Live monitoring intelligence dashboards are used to visualize data in real-time. They are used to track key performance indicators (KPIs), metrics, and other key data points in real-time. They are often used in business intelligence and other data analytics applications.
                </Card.Text>
              </Card.Body>
            </Card>
          </Col>
        </Row> */}
          {/* <Row>
          <Col>
            <Card style={{ cursor: 'pointer' }}>
              <Card.Header>
                <Card.Title as="h5">How It Works</Card.Title>
                <i className="feather icon-layers" />
              </Card.Header>
              <Card.Body>
                <Card.Text>
                  GeoAI brings geospatial intelligence and AI-powered mapping to government and enterprise teams.
                </Card.Text>
                <img src='https://www.braein.com/images/home/how_it_works/pic.png' style={{ width: '100%', height: 'auto' }} />
              </Card.Body>
            </Card>
          </Col>

        </Row> */}
        </Container>
      </div>
    </div >
  );
}

export default App;
