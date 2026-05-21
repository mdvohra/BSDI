import React from "react";
import TypeWriter from "../../../components/renderbyletter";
import { ThreeDots } from "react-loader-spinner";
const ChatBubble = ({ messages }) => {
  // render text with **bold** and _italic_ text
  const renderTextBold = (text) => {
    return text?.split("**").map((part, index) => {
      if (index % 2 === 0) {
        return part.split("_").map((part2, index2) => {
          if (index2 % 2 === 0) {
            return part2;
          } else {
            return <i key={index2}>{part2}</i>;
          }
        });
      } else {
        return <b key={index}>{part}</b>;
      }
    });
  };

  return (
    <div
      style={{
        overflowY: "scroll",
        minHeight: "66vh",
        maxHeight: "66vh",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {messages.map((message, index) => (
        <div key={index} style={styles.messageContainer}>
          <div style={styles.questionBubble}>
            {
              message.question ? (
                message.isNotHistory ? (

                  <TypeWriter text={message?.question} speed={30} />
                ) : (
                  message?.question
                )
              ) : (
                null
              )
            }
          </div>
          <div style={styles.answerBubble}>
            {message?.isLoading ? (
              <ThreeDots

                style={{ display: "flex", alignSelf: "center" }}
                color="#000000" height={20} width={20} />
            ) : (
              message?.answer ? (
                message.isNotHistory ? (

                  <TypeWriter text={message?.answer} speed={30} />
                ) : (
                  message?.answer
                )
              ) : (
                null
              )
            )}
          </div>
        </div>
      ))}
    </div>
  );
};


const styles = {
  messageContainer: {
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    marginBottom: '10px',
  },
  questionBubble: {
    backgroundColor: '#f1f0f0',
    padding: '10px 15px',
    borderRadius: '10px',
    maxWidth: '85%',
    alignSelf: 'flex-start',
    marginBottom: '10px',
  },
  answerBubble: {
    backgroundColor: '#f1f0f0',
    padding: '10px 15px',
    borderRadius: '10px',
    minWidth: '85%',
    maxWidth: '85%',
    alignSelf: 'flex-end',
  },
};


export default ChatBubble;