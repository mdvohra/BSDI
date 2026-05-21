import React, { useState, useEffect } from 'react';
import { Navbar, Nav, Container, Button, Row, Col, Card, NavDropdown } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useNavigate } from 'react-router-dom';
import './App.css';  // New CSS file for custom animations and styles
import TextVideoDisplay from './textvideo';
import TypeWriter from '../../components/renderbyletter';
import FlipCard from './cardflip';
import TextImage from './textimage';
// import AnimatedCard from './animatedcard';
import AnimatedDiv from './divanimation';
// import BrainAnimation from './brainani';
// import Viewpager from './viewpager.jsx';
// import Fliponclick from './fliponclick';
import CardStack from './cardstack';
function App() {
  const navigate = useNavigate();
  const goToDashboard = () => {
    const role = localStorage.getItem('role');
    if (role === 'admin') {
      navigate('/app/admin/dashboard/')
    }
    else if (role === 'user') {
      navigate('/app/userdashboard')
    }
    else {
      navigate('/login')
    }
  }

  const [currentIndex, setCurrentIndex] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);


  const textList = [
    "AI is revolutionizing industries",
    "Predictive analytics offer future insights",
    "Deep learning is shaping modern applications",
    "Computer Vision enhances data visualization"
  ];

  const videoList = [
    "https://unifynow.ai/images/digital_twin.mp4",
    "https://unifynow.ai/images/image_annoation_seq.mp4",
    "https://unifynow.ai/images/video_anlaytics%201.mp4",
    "https://unifynow.ai/images/Neural%20networks.mp4"
  ];


  return (
    <>
      <div className="App">
        {/* Fixed Navbar Component */}
        <Navbar
          className="navbar-custom navbar-brandf"
          expand="lg"
        >
          <Container>
            <Navbar.Brand href="#home">
              <div>
                <Link to="#" className="b-brand" style={{ textDecoration: 'none' }}>
                  <span className="geoai-wordmark">GeoAI</span>
                </Link>
              </div>
            </Navbar.Brand>
            <Navbar.Toggle aria-controls="basic-navbar-nav" />
            <Navbar.Collapse id="basic-navbar-nav">
              <Nav className="ms-auto navbar-links">
                <Nav.Link onClick={goToDashboard} className="nav-item-custom">Home</Nav.Link>

                {/* <NavDropdown
                  title={<span className="nav-item-custom">Solutions</span>} id="features-dropdown">
                  <NavDropdown.Item onClick={() => navigate('/app/pdfquery')}>Language Based Models</NavDropdown.Item>
                  <NavDropdown.Item href="#action/1">Computer Vision</NavDropdown.Item>
                  <NavDropdown.Item href="#action/2">GeoSpatial Analysis</NavDropdown.Item>
                </NavDropdown> */}
                <Nav.Link href="/app/pdfquery" className="nav-item-custom">Solutions</Nav.Link>

                <Nav.Link href="https://www.braein.com/connect-us.html" className="nav-item-custom">Contact Us</Nav.Link>
                <Nav.Link
                  className="get-started-btn"
                  href='/login'
                >
                  Get Started
                </Nav.Link>
              </Nav>
            </Navbar.Collapse>
          </Container>
        </Navbar>
        <AnimatedDiv>
          <div style={{ marginTop: '120px' }}>
            {/* Header Section */}
            {/* <BrainAnimation /> */}
            {/* <Viewpager /> */}
            <div
              className="text-center p-5t" style={{ marginBottom: '20px' }}> {/* Adjusted margin-bottom */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                }}
              >
                <div className='gradient-heading'>
                  Welcome to GeoAI
                </div>
              </div>
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
                    minHeight: '100px'
                  }}
                >
                  <TypeWriter text="GeoAI brings geospatial intelligence and AI-powered mapping to government and enterprise teams—object detection, land insight, and document workflows in one platform." speed={30} />
                </p>
              </div>
            </div>
          </div>
        </AnimatedDiv>
        <AnimatedDiv>
          <div
            className="my-5">
            <TextVideoDisplay textList={textList} videoList={videoList} />
          </div>
        </AnimatedDiv>
        <AnimatedDiv>
          <div className="text-center my-5">
            <TextImage />
          </div>
        </AnimatedDiv>
        {/* Cards Section */}
        <Container className="my-5">
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
            }}
          >
            <div className='gradient-heading'>Our Solutions</div>
          </div>
          <Row
            style={{
              // paddingBottom: '260px'
              marginBottom: '300px'
            }}
          >
            <Col>
              {/* <Card onClick={() => navigate('/app/pdfquery')} className="service-card">
                <Card.Header>
                  <Card.Title as="h5">LLM for Data Files like PDF, Excel, CSV</Card.Title>
                  <i className="feather icon-file-text" />
                </Card.Header>
                <Card.Body>
                  <Card.Text
                  style={{
                    padding: '10px'
                  }}
                  >
                    Large Language Models (LLMs) are neural networks that can be trained on large text data sets. They are used in applications like chatbots, language translation, and text summarization for handling documents like PDFs, Excel, and CSV files.
                  </Card.Text>
                </Card.Body>
              </Card> */}
              <FlipCard redirectlink='/app/pdfquery' title='LLM for Data Files like PDF, Excel, CSV' description='Large Language Models (LLMs) are neural networks that can be trained on large text data sets. They are used in applications like chatbots, language translation, and text summarization for handling documents like PDFs, Excel, and CSV files.' />
            </Col>
            <Col>
              {/* <Card className="service-card">
                <Card.Header>
                  <Card.Title as="h5">Computer Vision Services</Card.Title>
                  <i className="feather icon-eye" />
                </Card.Header>
                <Card.Body>
                  <Card.Text
                  style={{
                    padding: '10px'
                  }}
                  >
                    Computer vision is an interdisciplinary field that deals with how computers can gain high-level understanding from digital images or videos. It seeks to understand and automate tasks that the human visual system can do.
                  </Card.Text>
                </Card.Body>
              </Card> */}
              <FlipCard redirectlink='/app/pdfquery' title='Computer Vision Services' description='Computer vision is an interdisciplinary field that deals with how computers can gain high-level understanding from digital images or videos. It seeks to understand and automate tasks that the human visual system can do.' />
            </Col>

            <Col>
              {/* <Card className="service-card">
                <Card.Header>
                  <Card.Title as="h5">GIS Analysis</Card.Title>
                  <i className="feather icon-map" />
                </Card.Header>
                <Card.Body>
                  <Card.Text
                  style={{
                    padding: '10px'
                  }}
                  >
                    A Geographic Information System (GIS) is a framework that provides the ability to capture and analyze spatial and geographic data. It allows users to create interactive queries, store and edit spatial and non-spatial data, and analyze geographic information.
                  </Card.Text>
                </Card.Body>
              </Card> */}
              <FlipCard redirectlink='/app/sataliteimage' title='GIS Analysis' description='A Geographic Information System (GIS) is a framework that provides the ability to capture and analyze spatial and geographic data. It allows users to create interactive queries, store and edit spatial and non-spatial data, and analyze geographic information.' />
            </Col>
          </Row>
          <Row>
            <Col lg={12}>
              <AnimatedDiv>
                <Card className="service-card"
                  style={{
                    borderRadius: '10px'
                  }}
                >
                  <Card.Body>
                    <img src="https://www.braein.com/images/home/how_it_works/pic.png" style={{ width: '100%', height: '100%' }} />
                  </Card.Body>
                </Card>
              </AnimatedDiv>
            </Col>
          </Row>
          <Row>

            <Col lg={6} >
              <AnimatedDiv>
                <Card className="service-card" style={{ borderRadius: '10px' }}>
                  <Card.Body>
                    <div
                      style={{
                        fontSize: '20px',
                        color: '#6c757d',
                        marginBottom: '20px',
                        width: '100%',
                      }}
                    >
                      GeoAI combines artificial intelligence, analytics, and location intelligence for national-scale geospatial programs.
                    </div>
                    <Row>
                      <Col lg={6}>
                        <div className="numbered-section">
                          <span className="number-circle">1</span>
                          <div>
                            <span className="section-title">Model Selection</span>
                            <p className="section-description">We select the best model for your data</p>
                          </div>
                        </div>
                      </Col>
                      <Col lg={6}>
                        <div className="numbered-section">
                          <span className="number-circle">2</span>
                          <div>
                            <span className="section-title">Data Preprocessing</span>
                            <p className="section-description">We clean and preprocess your data</p>
                          </div>
                        </div>
                      </Col>
                    </Row>
                    <Row>
                      <Col lg={6}>
                        <div className="numbered-section">
                          <span className="number-circle">3</span>
                          <div>
                            <span className="section-title">Model Training</span>
                            <p className="section-description">We train the model on your data</p>
                          </div>
                        </div>
                      </Col>
                      <Col lg={6}>
                        <div className="numbered-section">
                          <span className="number-circle">4</span>
                          <div>
                            <span className="section-title">Model Evaluation</span>
                            <p className="section-description">We evaluate the model performance</p>
                          </div>
                        </div>
                      </Col>
                    </Row>
                  </Card.Body>
                </Card>
              </AnimatedDiv>
            </Col>
            <Col lg={6}>
              <AnimatedDiv>
                {/* <Card className="service-card"
                  style={{
                    borderRadius: '10px'
                  }}
                > */}
                {/* <Card.Body> */}
                {/* render a viedo */}
                <video loop autoPlay muted style={{ width: '90%', height: 'auto', borderRadius: '10px' }}>
                  <source src="src/views/landingpage/8327799-uhd_3840_2160_25fps.mp4" type="video/mp4" />
                </video>

                {/* </Card.Body> */}
                {/* </Card> */}
              </AnimatedDiv>
            </Col>
          </Row>
        </Container>
      </div >
      {/* Footer Section */}
      < footer className="bg-light text-center text-lg-start mt-5 gradient-footer" >
        <Container className="p-4">
          <Row>
            <Col lg={3} className="mb-4 mb-lg-0">
              <div>
                <span className="geoai-wordmark geoai-wordmark--on-light">GeoAI</span>
              </div>
              {/* <h5 className="text-uppercase">Braein AI</h5> */}
            </Col>
            <Col lg={3} className="mb-4 mb-lg-0">
              <h5 style={{
                fontWeight: 'bold'
              }}
              className='footer-items-heading'
              >Business</h5>
              <Nav className="flex-column">
                <Nav.Link className='footer-items ' href="/app/pdfquery">LLM for Data Files</Nav.Link>
                <Nav.Link className='footer-items ' href="#action/1">Computer Vision Services</Nav.Link>
                <Nav.Link className='footer-items ' href="#action/2">GIS Analysis</Nav.Link>
                <Nav.Link className='footer-items ' href="https://www.braein.com/connect-us.html">Contact Us</Nav.Link>
              </Nav>
            </Col>
            <Col lg={3} className="mb-4 mb-lg-0">
              <h5 style={{
                fontWeight: 'bold'
              }}className='footer-items-heading'>Agencies</h5>
              <Nav className="flex-column">
                <Nav.Link className='footer-items ' href="/app/pdfquery">LLM for Data Files</Nav.Link>
                <Nav.Link className='footer-items ' href="#action/1">Computer Vision Services</Nav.Link>
                <Nav.Link className='footer-items ' href="#action/2">GIS Analysis</Nav.Link>
                <Nav.Link className='footer-items ' href="https://www.braein.com/connect-us.html">Contact Us</Nav.Link>
              </Nav>
            </Col>
            <Col lg={3} className="mb-4 mb-lg-0">
              <h5 style={{
                fontWeight: 'bold'
              }}className='footer-items-heading'>Get in Touch</h5>
              <Nav className="flex-column">
                <Nav.Link className='footer-items ' href="/app/pdfquery">LLM for Data Files</Nav.Link>
                <Nav.Link className='footer-items ' href="#action/1">Computer Vision Services</Nav.Link>
                <Nav.Link className='footer-items ' href="#action/2">GIS Analysis</Nav.Link>
                <Nav.Link className='footer-items ' href="https://www.braein.com/connect-us.html">Contact Us</Nav.Link>
              </Nav>
            </Col>
          </Row>
          <div
            style={{
              display: 'flex',
              justifyContent: "space-between",
              marginTop: '20px'
            }}
          >
            <div className="text-center p-3 footer-text ">
              © {new Date().getFullYear()} GeoAI. All Rights Reserved.
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: "space-between",
              }}
            >
              <div className="text-center p-3 footer-text "  >Terms</div>
              <div className="text-center p-3 footer-text "  >Privacy Policy</div>
              <div className="text-center p-3 footer-text "  >Accessibility</div>
              <div className="text-center p-3 footer-text "  >Fraud Protection</div>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: "space-between",
              }} >
              <div className="text-center p-3 footer-text " >

                <i class="fi fi-brands-facebook"></i>
              </div>
              <div className="text-center p-3 footer-text ">

                <i class="fi fi-brands-twitter-alt-circle"></i>
              </div>
              <div className="text-center p-3 footer-text ">

                <i class="fi fi-brands-linkedin"></i>
              </div>
              <div className="text-center p-3 footer-text ">

                <i class="fi fi-brands-instagram"></i>
              </div>
              <div className="text-center p-3 footer-text ">

                <i class="fi fi-brands-youtube"></i>
              </div>
            </div>
          </div>
        </Container>
      </footer >
    </>
  );
}

export default App;
