import React, { useState, useEffect } from 'react';
import { Row, Col, Container } from 'react-bootstrap';
import './textimage.css';

const TextImage = () => {
    const images = [
        'https://unifynow.ai/images/digitalworkplace-modelselection.jpg',
        'https://unifynow.ai/images/digitalworkplace-configure-assests.jpg',
        'https://unifynow.ai/images/digitalworkplace-digital-twin.jpg'
    ];
    const description = "Digital workplace solutions are transforming the way we work. With AI and ML, we can now predict future outcomes and optimize business processes. Our digital twin technology offers a unique perspective on data visualization and analytics. Computer vision is enhancing the way we interact with data and images.";

    const [currentIndex, setCurrentIndex] = useState(0);
    const [isAnimating, setIsAnimating] = useState(false);

    useEffect(() => {
        const intervalId = setInterval(() => {
            setIsAnimating(true); // Start animation
            setTimeout(() => {
                setCurrentIndex((prevIndex) => (prevIndex + 1) % images.length);
                setIsAnimating(false); // End animation
            }, 200); // Match this duration with CSS animation duration
        }, 4000); // Change image every 3 seconds

        return () => clearInterval(intervalId); // Cleanup interval on component unmount
    }, [images.length]);

    return (
        <Container className="my-5">
            <Row>
                <Col md={6}

                    style={{
                        overflow: 'hidden', // Hide image overflow
                    }}
                    className="text-center">
                    <div className={`image-container ${isAnimating ? 'slide-out' : 'slide-in'}`}>
                        <img
                            src={images[currentIndex]}
                            alt={`Image ${currentIndex + 1}`}
                            style={{ width: '80%', height: 'auto', borderRadius: '10px' }} // Adjust styles as needed
                        />
                    </div>
                </Col>
                <Col md={6} className="d-flex align-items-center">
                    <div>
                        <div
                            style={{
                                display: 'flex',
                                justifyContent: 'center',
                            }}
                        >
                            <div className='gradient-heading' >Description</div>
                        </div>
                        <p>{description}</p>
                    </div>
                </Col>
            </Row>
        </Container>
    );
};

export default TextImage;
