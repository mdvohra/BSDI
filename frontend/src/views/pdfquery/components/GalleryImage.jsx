import React from "react";
import styled from "styled-components";
import GalleryImage from "./GalleryImagesup";

const imageUrls = [
  "https://cdn.builder.io/api/v1/image/assets/TEMP/6bf568aeca7dd5f11206fce8cf796f58d2fa9b5596fc213b4809aed6eb9d2ae9?placeholderIfAbsent=true&apiKey=73af7fcffe284688b01dde92703db4e5",
  "https://cdn.builder.io/api/v1/image/assets/TEMP/208a5ff660ca110134500254bcb9db6a35918628ed734342ef9b58faa255570c?placeholderIfAbsent=true&apiKey=73af7fcffe284688b01dde92703db4e5",
  "https://cdn.builder.io/api/v1/image/assets/TEMP/25c2954e9eb76bd8df57538f39c965adfe6c3bb7476e11ffdd774eda4bdf04c4?placeholderIfAbsent=true&apiKey=73af7fcffe284688b01dde92703db4e5",
  "https://cdn.builder.io/api/v1/image/assets/TEMP/133ebfa9f62bdd29d1af5e3b86e2aa882ee109c96198fe8f5a4b72d4b93de7aa?placeholderIfAbsent=true&apiKey=73af7fcffe284688b01dde92703db4e5"
];

function ImageGallery() {
  return (
    <GalleryContainer>
      {imageUrls.map((url, index) => (
        <GalleryImage key={index} src={url} />
      ))}
    </GalleryContainer>
  );
}

const GalleryContainer = styled.section`
  display: flex;
  align-items: center;
  gap: 20px;
  justify-content: flex-start;
`;

export default ImageGallery;