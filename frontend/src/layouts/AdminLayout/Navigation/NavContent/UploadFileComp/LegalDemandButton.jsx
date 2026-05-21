import React, { useContext, useState, useRef } from "react";
import styled from "styled-components";
import axios from "axios";
// import { ConfigContext } from "./contexts/ConfigContext";
//import { ConfigContext } from "../../../../contexts/ConfigContext";
// import useOutsideClick from "hooks/useOutsideClick";
//import useOutsideClick from "../../../../hooks/useOutsideClick";
import { ConfigContext } from "../../../../../contexts/ConfigContext";
import useOutsideClick from "../../../../../hooks/useOutsideClick";


const LegalDemandButton = ({ chat }) => {
  const configContext = useContext(ConfigContext);
  const { dispatch } = configContext;

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [newChatTitle, setNewChatTitle] = useState(chat.chatTitle);
  const ref = useRef();

  useOutsideClick(ref, () => {
    if (isDropdownOpen) {
      setIsDropdownOpen(false);
    }
  });

  const getChatHistory = async (chatId) => {
    const response = await axios.get(`Chata/GetChatHistory/${chatId}`);
    dispatch({
      type: 'SELECTED_CHAT_HISTORY',
      historySelectedFile: response.data.file,
      historyfilemessages: response.data.chatHistory.$values,
      historyfileassistantId: response.data.fileassistantId,
      historymainassistantId: response.data.mainassistantId,
      historyassistantId: response.data.assistantId,
      historyfileid: chat.fileID,
      historyFilename: response.data.fileName,
    });
  };

  const handleDelete = async (chatId) => {
    await axios.delete(`Chata/DeleteChat/${chatId}`);
    // Refresh the page
    window.location.reload();
  };

  const handleRename = async (chatId) => {
    try {
      await axios.put(`Chata/RenameChat/${chatId}?chatTitle=${newChatTitle}`).then((response) => {
        console.log(response);
        window.location.reload();
      });
      // Exit rename mode after successful rename
      setIsRenaming(false);
      // Refresh the page
    } catch (error) {
      console.error("Error renaming chat:", error);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleRename(chat.chatID);
    }
  };

  const dropDownCard = (
    <StyledDropDownCard>
      <DropDownButton onClick={() => setIsRenaming(true)}>Rename</DropDownButton>
      <DropDownButton onClick={() => handleDelete(chat.chatID)}>Delete</DropDownButton>
      <DropDownButton>Share</DropDownButton>
    </StyledDropDownCard>
  );

  return (
    <StyledButton ref={ref}>
      {isRenaming ? (
        <RenameInput
          value={newChatTitle}
          onChange={(e) => setNewChatTitle(e.target.value)}
          onKeyPress={handleKeyPress}
          autoFocus
        />
      ) : (
        <>
          <ButtonText onClick={() => getChatHistory(chat.chatID)}>
            {chat.chatTitle}
          </ButtonText>
          <IconContainer>
            <i onClick={() => setIsDropdownOpen(!isDropdownOpen)} className="fi fi-rr-menu-dots"></i>
          </IconContainer>
          {isDropdownOpen && dropDownCard}
        </>
      )}
    </StyledButton>
  );
};

const StyledButton = styled.button`
  border-radius: 10px;
  background-color: #59698f;
  display: flex;
  align-items: center;
  margin-top: 10px;
  gap: 10px;
  color: #fff;
  font-weight: 300;
  padding: 10px 15px;
  border: none;
  cursor: pointer;
  justify-content: space-between;
  transition: transform 0.2s, background-color 0.2s;

  &:hover {
    background-color: #6b789f;
  }
`;

const ButtonText = styled.span`
  flex-grow: 1;
  margin: auto 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const IconContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;

  ${StyledButton}:hover & {
    opacity: 1;
  }
`;

const StyledDropDownCard = styled.div`
  position: absolute;
  top: 95%;
  left: 60%;
  background-color: #59698f;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 5px;
  z-index: 1;
`;

const DropDownButton = styled.button`
  background-color: #59698f;
  color: #fff;
  border: none;
  border-radius: 10px;
  padding: 10px;
  cursor: pointer;
  transition: background-color 0.2s;
  z-index: 1;

  &:hover {
    background-color: #6b789f;
  }
`;

const RenameInput = styled.input`
  flex-grow: 1;
  padding: 8px;
  border-radius: 5px;
  border: 1px solid #ccc;
`;

export default LegalDemandButton;
