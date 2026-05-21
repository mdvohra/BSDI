import React, { useRef, useEffect, useState } from 'react';
import { Card } from 'react-bootstrap';
import { useNavigate } from 'react-router-dom';
import './App.css';
function FlipCard({title, description,redirectlink}) {
  const cardRef = useRef(null);
  const navigate = useNavigate();
  const [isFlipped, setIsFlipped] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            setIsFlipped(true); // Flip the card when it is in view
          }
        });
      },
      {
        threshold: 0, // Trigger when 50% of the card is visible
      }
    );

    if (cardRef.current) {
      observer.observe(cardRef.current);
    }

    return () => {
      if (cardRef.current) {
        observer.unobserve(cardRef.current);
      }
    };
  }, []);

  return (
    <div
    onClick={() => navigate(redirectlink)}
    className={`flip-card ${!isFlipped ? 'flip-card-flipped' : ''}`} ref={cardRef}>
      <div className="flip-card-inner">
        {/* Front of the card */}
        <div className="flip-card-front">
          <Card className="service-card">
            <Card.Header>
              <Card.Title as="h5">{title}</Card.Title>
              <i className="feather icon-file-text" />
            </Card.Header>
            <Card.Body>
              <Card.Text style={{ padding: '10px' }}>
                {description}
              </Card.Text>
            </Card.Body>
          </Card>
        </div>

        {/* Back of the card */}
        <div className="flip-card-back">
          <Card className="service-card">
            <Card.Body>
              <Card.Text style={{ padding: '10px' }}>
                More details about this service...
              </Card.Text>
            </Card.Body>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default FlipCard;
