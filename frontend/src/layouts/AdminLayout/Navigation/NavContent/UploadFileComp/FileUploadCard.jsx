import React from "react";
import styled from "styled-components";

const FileUploadCard = () => {
  return (
    <StyledCard>
      <UploadInfo>
        <UploadIcon src="https://cdn.builder.io/api/v1/image/assets/TEMP/b1bce800da5e81dcff8cc53ca459fce7addff3b520cc6b614af49fa899bd17f0?placeholderIfAbsent=true&apiKey=73af7fcffe284688b01dde92703db4e5" alt="" />
        <UploadText>New File</UploadText>
      </UploadInfo>
      <DropText>Drop File here</DropText>
    </StyledCard>
  );
};

const StyledCard = styled.div`
  border-radius: 10px;
  background-color: #656e7d;
  display: flex;
  width: 100%;
  flex-direction: column;
  align-items: center;
  padding: 12px 49px;
  border: 1px dashed #fff;
`;

const UploadInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  color: #fff;
  font-weight: 500;
  justify-content: center;
  padding: 10px;
`;

const UploadIcon = styled.img`
  aspect-ratio: 1;
  object-fit: contain;
  object-position: center;
  width: 20px;
  align-self: stretch;
  margin: auto 0;
`;

const UploadText = styled.span`
  align-self: stretch;
  margin: auto 0;
`;

const DropText = styled.p`
  color: rgba(255, 255, 255, 0.65);
  font-weight: 400;
  margin: 0;
`;

export default FileUploadCard;