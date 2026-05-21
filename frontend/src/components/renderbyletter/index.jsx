import React, { useState, useEffect } from 'react';

const TypeWriter = ({ text, speed = 100 }) => {
  const [displayedText, setDisplayedText] = useState('');
  useEffect(() => {
    let index = 0;
    setDisplayedText(text[index]);
    const intervalId = setInterval(() => {
      if (index < text.length-1) {
        setDisplayedText((prev) => prev + text[index]);
        index++;
      } else {
        clearInterval(intervalId);
      }
    }, speed);

    return () => clearInterval(intervalId);
  }, [text, speed]);

  return (
    <div style={{ textAlign: 'left',
     padding: 0,
      margin: 0,
      whiteSpace: 'pre-wrap',
      }}>
      {displayedText}
    </div>
  );
};

export default TypeWriter;
