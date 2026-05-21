import React, { useState, useEffect } from 'react';
import { Container, Row, Col } from 'react-bootstrap';

function TextVideoDisplay({ videoList, textList }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setIsAnimating(true);
      setTimeout(() => {
        setCurrentIndex((prevIndex) => (prevIndex + 1) % textList.length);
        setIsAnimating(false);
      }, 500); // Adjust animation duration
    }, 5500); // Change every 4 seconds

    return () => clearInterval(interval);
  }, []);

  return (
    <Container className="my-5">
      <Row>
        {/* Column to render text */}
        <Col lg={6} >
          <div
            style={{
              height: '100%',
              justifyContent: 'center',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <div
              style={{
                overflow: 'hidden',
              }}>
              <div className='gradient-heading' style={{
                transform: `translateY(${isAnimating ? '-100%' : '0'})`,
                transition: 'transform 0.5s ease',
              }}>
                {textList[currentIndex]}
              </div>
            </div>
          </div>
        </Col>

        <Col lg={6}>
          <div
            style={{
              overflow: 'hidden'
            }}
          >
            <video
              key={currentIndex}
              width="80%"
              autoPlay
              muted
              loop
              style={{
                borderRadius: '15px',
                transform: `translateY(${isAnimating ? '-100%' : '0'})`,
                transition: 'transform 0.5s ease'
              }}
            >
              <source
                src={videoList[currentIndex]}
                type="video/mp4"
              />
              Your browser does not support the video tag.
            </video>
          </div>
        </Col>

      </Row>
    </Container>
  );
}

export default TextVideoDisplay;
