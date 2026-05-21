// BrainAnimation.js
import React from "react";
import styled, { keyframes } from "styled-components";

const pulse = keyframes`
  0% {
    transform: scale(1);
    opacity: 0.8;
  }
  50% {
    transform: scale(1.2);
    opacity: 1;
  }
  100% {
    transform: scale(1);
    opacity: 0.8;
  }
`;

const BrainWrapper = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background-color: #f0f0f0;
`;

const Brain = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-gap: 15px;
  padding: 20px;
`;

const Neuron = styled.div`
  width: 30px;
  height: 30px;
  background-color: #4caf50;
  border-radius: 50%;
  animation: ${pulse} 1.5s infinite;
  animation-delay: ${(props) => props.delay}s;
  box-shadow: 0px 0px 10px rgba(76, 175, 80, 0.8);
`;

const Connection = styled.div`
  grid-column: span 4;
  height: 5px;
  background-color: #4caf50;
  animation: ${pulse} 2s infinite;
  animation-delay: ${(props) => props.delay}s;
`;

const BrainAnimation = () => {
  return (
    <BrainWrapper>
      <Brain>
        <Neuron delay={0.2} />
        <Neuron delay={0.4} />
        <Neuron delay={0.6} />
        <Neuron delay={0.8} />
        <Connection delay={0.3} />
        <Neuron delay={1.0} />
        <Neuron delay={1.2} />
        <Neuron delay={1.4} />
        <Neuron delay={1.6} />
      </Brain>
    </BrainWrapper>
  );
};

export default BrainAnimation;
