import React,{useContext,useEffect,useState} from "react";
import styled from "styled-components";
import FileUploadCard from "./FileUploadCard";
import LegalDemandButton from "./LegalDemandButton";
import { ConfigContext } from '../../../../../contexts/ConfigContext';
const FileUploadSection = () => {
  // get user history from redux
  const configContext = useContext(ConfigContext);
  const { userChats } = configContext.state;
  const [chats, setchats] = useState([]);
  useEffect(() => {
    // get user history from redux
    setchats(userChats);
  }, [userChats]);


  return (
    <StyledSection>
      <FileUploadCard />
      {
        chats.map((chat,index) => (
          <LegalDemandButton key={index} chat={chat} />
        ))
      }
    </StyledSection>
  );
};

const StyledSection = styled.section`
  border-radius: 0;
  display: flex;
  max-width: 244px;
  flex-direction: column;
  font: 14px/1 Omnes, sans-serif;
`;

export default FileUploadSection;