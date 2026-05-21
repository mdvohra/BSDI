import React, { useState, useEffect } from 'react';
import { useInView } from 'react-intersection-observer';
import './CardAnimations.css';
const AnimatedDiv = ({ children }) => {
  const [inView, setInView] = useState(false);
  const { ref, inView: isInView } = useInView({
    triggerOnce: true, // Trigger animation only once
    threshold: 0.9, // Start animation when 10% of the div is visible
  });

  useEffect(() => {
    if (isInView) {
      setInView(true);
    }
  }, [isInView]);

  return (
    <div ref={ref} className={`animated-div ${inView ? 'animate' : 'hidden'}`}>
      {children}
    </div>
  );
};

export default AnimatedDiv;
