import React, { useState, useEffect } from 'react';
import { Card } from 'react-bootstrap';
import { useInView } from 'react-intersection-observer';
import './CardAnimations.css'; // Add your custom CSS here

const AnimatedCard = ({ title, description }) => {
  const [inView, setInView] = useState(false);
  const { ref, inView: isCardInView } = useInView({
    triggerOnce: true, // Trigger the animation once when it comes into view
    threshold: 0.9, // Percentage of card visible before triggering animation
  });

  useEffect(() => {
    if (isCardInView) {
      setInView(true);
    }
  }, [isCardInView]);

  return (
    <Card
      className={`service-card ${inView ? 'animate-card' : 'hidden-card'}`}
      ref={ref}
    >
      <Card.Header>
        <Card.Title as="h5">{title}</Card.Title>
        <i className="feather icon-file-text" />
      </Card.Header>
      <Card.Body>
        <Card.Text style={{ padding: '10px' }}>{description}</Card.Text>
      </Card.Body>
    </Card>
  );
};

export default AnimatedCard;
