import React from "react";
import styled from "styled-components";

function GalleryImage({ src }) {
  return <StyledImage loading="lazy" src={src} alt="" />;
}

const StyledImage = styled.img`
  aspect-ratio: 1;
  object-fit: contain;
  object-position: center;
  width: 24px;
  align-self: stretch;
  margin: auto 0;
`;

export default GalleryImage;