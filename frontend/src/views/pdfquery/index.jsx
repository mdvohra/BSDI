import React, { useState, useRef, useEffect, useContext } from 'react';
import { Container, Form, Button, InputGroup, FormControl, Collapse, Col, Row } from 'react-bootstrap';
import { XCircle } from 'react-bootstrap-icons'; // Import the Bootstrap Icon for the close button
import './fileupload.css';
import ImageGallery from './components/GalleryImage.jsx';
import ChatBubble from './components/ChatBubble';
import styled from "styled-components";
import { ConfigContext } from '../../contexts/ConfigContext';
import axios from 'axios';
import jsPDF from 'jspdf';
const PdfQuery = () => {
    const configContext = useContext(ConfigContext);
    const { historySelectedFile, historyfilemessages, historyfileassistantId, historymainassistantId, historyfileid, historyassistantId, historyFilename } = configContext.state;
    const { dispatch } = configContext;
    const [selectedFile, setSelectedFile] = useState();
    const [isDragging, setIsDragging] = useState(false);
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [messages, setMessages] = useState(); // For storing chat messages
    const [isUploadLoading, setIsUploadLoading] = useState(false);
    const fileInputRef = useRef(null);
    const [fileassistantId, setfileassistantId] = useState();
    const [mainassistantId, setmainassistantId] = useState();
    const [fileid, setfileid] = useState();
    const [allContext, setAllContext] = useState(false);
    const [isNotes, setIsNotes] = useState(false);
    const [notes, setNotes] = useState('');
    const [notesTItle, setNotesTitle] = useState('');
    const id = '1'; // user id

    useEffect(() => {
        // console.log(historySelectedFile, historyfilemessages, historyfileassistantId, historymainassistantId, historyfileid);
        if (historySelectedFile === null) return;
        setSelectedFile(base64ToBlob(historySelectedFile));
        setMessages(historyfilemessages);
        setfileassistantId(historyfileassistantId);
        setmainassistantId(historymainassistantId);
        setfileid(historyfileid);
        setIsCollapsed(true);
    }, [historySelectedFile, historyfilemessages, historyfileassistantId, historymainassistantId, historyfileid, historyFilename]);
    const base64ToBlob = (base64, type = 'application/pdf') => {
        const byteCharacters = atob(base64);
        const byteNumbers = new Uint8Array(byteCharacters.length);

        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }

        return new Blob([byteNumbers], { type });
    };
    const handleFileSelect = (event) => {
        setSelectedFile(event.target.files[0]);
    };

    const handleDrop = (event) => {
        event.preventDefault();
        event.stopPropagation();
        setIsDragging(false);
        if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
            setSelectedFile(event.dataTransfer.files[0]);
            event.dataTransfer.clearData();
        }
    };

    const handleDragOver = (event) => {
        event.preventDefault();
        event.stopPropagation();
        setIsDragging(true);
    };

    const handleDragLeave = (event) => {
        event.preventDefault();
        event.stopPropagation();
        setIsDragging(false);
    };

    const handleBoxClick = () => {
        fileInputRef.current.click();
    };

    const handleSubmit = () => {
        if (selectedFile) {
            setIsUploadLoading(true);
            setMessages([]);
            console.log('File ready to upload:', selectedFile);
            const formData = new FormData();
            formData.append('file', selectedFile);
            axios
                .post(`FileUpload/upload/${id}`, formData, {
                    headers: {
                        'Content-Type': 'multipart/form-data'
                    }
                })
                .then((response) => {
                    console.log('File uploaded successfully:', response);
                    setAllContext(false);
                    setfileassistantId(response.data.fileassistantid);
                    setmainassistantId(response.data.mainassistantid);
                    setfileid(response.data.fileId);
                    setIsUploadLoading(false);
                })
                .catch((error) => {
                    console.error('Error uploading file:', error);
                })
                .then(setIsCollapsed(true)); // Collapse the form after the file is uploaded
        }
    };

    const handleRemoveFile = () => {
        setSelectedFile(null);
        setIsCollapsed(false); // Expand the form after removing the file
    };


    const handleChatSubmit = (event) => {
        event.preventDefault();
        const question = event.target.elements.message.value.trim();
        setMessages([...messages, { question: question, isLoading: true, isNotHistory: true }]);
        // create chat id from file id, user id and assistant id
        let chatid = `${fileid}-${id}-${allContext ? mainassistantId : fileassistantId}`;
        axios.post(`ChatAssistant/chatAssistant/${fileassistantId}/${mainassistantId}/${chatid}/${fileid}/${id}/${question}/${allContext}`).then((response) => {
            console.log('Chat response:', response);
            // setMessages([response.data]);
            // asign answer to corresponding question
            setMessages([...messages, { question: question, answer: response.data, isLoading: false, isNotHistory: true }]);
        });
    };
    const welcomeMessage = `Hello and welcome! 🎉 This PDF file is a treasure trove of resources and inspiration for chat UI design, featuring a curated collection of examples from talented designers around the world. It also includes links to engaging video tutorials on how to interact with PDF files using various chat applications. Dive in and explore the world of chat UI design and innovative ways to enhance your PDF experience!

                                Here are three example questions you can ask about the file:

                                What are some key features of the chat UI designs showcased in the PDF?

                                Can you provide a summary of the video tutorials mentioned in the document?

                                How can I implement the chat functionalities for my own PDF files as suggested in the PDF?`;

    const getFileName = () => {
        return selectedFile.name ? selectedFile.name : historyFilename;
    };

    const handleNotesSubmit = () => {
        // convert notes to pdf
        const doc = new jsPDF();
        doc.text(notes, 10, 10);
        const pdfBlob = doc.output('blob');
        const file = new File([pdfBlob], `${notesTItle}.pdf`, { type: "application/pdf" });
        setSelectedFile(file);
        console.log('File ready to upload:', file);
        setNotes('');
        setNotesTitle('');
        setIsNotes(false);
        handleSubmit();
    }

    return (
        <Container>
            <div>
                {isCollapsed && selectedFile ? (
                    <div
                        style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            margin: '10px auto'
                        }}
                    >
                        <div>
                            <h1
                                style={{
                                    fontSize: '20px',
                                    fontWeight: '900',

                                }}
                            >Pdf Chatbot</h1>
                        </div>
                        <div
                            style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                            }}
                        >
                            <i
                                className="fi fi-rr-progress-upload"
                                style={{
                                    fontSize: '20px',
                                    cursor: 'pointer',
                                    marginRight: '10px',
                                    marginTop: '5px'

                                }}
                                onClick={() => setIsCollapsed(!isCollapsed)}
                                aria-controls="file-upload-collapse"
                                aria-expanded={isCollapsed}
                            >

                            </i>
                            <div>{getFileName()}</div>
                        </div>
                        {/* feature name Query Pdf */}
                    </div>
                ) : null}

                <Collapse in={!isCollapsed || !selectedFile}>
                    <Row id="file-upload-collapse">
                        <Col lg={6}>
                            <div >
                                <Form>
                                    <div
                                        className={`file-drop-box ${isDragging ? 'dragging' : ''}`}
                                        onDragOver={handleDragOver}
                                        onDragLeave={handleDragLeave}
                                        onDrop={handleDrop}
                                        onClick={handleBoxClick}
                                    >
                                        <Form.Label>{selectedFile ? getFileName() : 'Drag and drop a file here, or click to select a file'}</Form.Label>
                                        {selectedFile && (
                                            <XCircle
                                                onClick={handleRemoveFile}
                                                size={20}
                                                style={{
                                                    cursor: 'pointer',
                                                    marginLeft: '10px',
                                                    marginTop: '-5px'
                                                }}
                                            />
                                        )}
                                        <Form.Control type="file" accept='.pdf' onChange={handleFileSelect} ref={fileInputRef} style={{ display: 'none' }} />
                                    </div>
                                    {selectedFile && (
                                        <Button
                                            style={{
                                                display: 'block',
                                                margin: 'auto',
                                                marginTop: '10px'
                                            }}
                                            onClick={handleSubmit}
                                            disabled={!selectedFile}
                                        >
                                            Upload
                                        </Button>
                                    )}
                                    {/* <Button
                                        style={{
                                            display: 'block',
                                            margin: 'auto',
                                            marginTop: '10px'
                                        }}
                                        onClick={handleSubmit}
                                        disabled={!selectedFile}
                                    >
                                        Upload
                                    </Button> */}
                                </Form>

                                {/* Feature description before PDF upload */}
                                <div
                                    style={{
                                        justifyContent: 'center',
                                        alignItems: 'center',
                                        margin: '10px auto',
                                        width: '70%',
                                        marginTop: '40px'

                                    }}
                                >
                                    <p>Users can seamlessly upload PDF documents through an intuitive drag-and-drop interface or by selecting files manually.</p>
                                    <p>
                                        Users can enter natural language queries, and the integrated LLM processes these queries to extract relevant information
                                        from the uploaded PDF.
                                    </p>
                                </div>

                                {/* Render a dropdown for LLM Models to query with */}
                            </div>
                        </Col>
                        {/* text seaction to take text input and conver it to pdf before uploading */}
                        <Col lg={6}>
                            <div >
                                <Form>
                                    <div
                                        className='file-drop-box'
                                        style={{
                                            height: isNotes ? '450px' : '200px',
                                            padding: isNotes ? '20px' : '0px',
                                        }}
                                    >
                                        {!isNotes ? <i
                                            onClick={() => setIsNotes(true)}
                                            style={{
                                                fontSize: '50px',
                                                cursor: 'pointer',
                                            }}
                                            className="fi fi-rr-edit"></i> :

                                            <div
                                                style={{
                                                    width: '100%',
                                                }}
                                            >

                                                <i
                                                    onClick={() => setIsNotes(false)}
                                                    style={{
                                                        fontSize: '20px',
                                                        cursor: 'pointer',
                                                        // position: 'relative',
                                                        left: '0',
                                                        top: '0',
                                                        float: 'right',
                                                    }}
                                                    className="fi fi-tr-circle-xmark"></i>
                                                <Form.Control
                                                    value={notes}
                                                    onChange={(e) => setNotes(e.target.value)}
                                                    as="textarea" rows={15} placeholder="Enter text here to convert to PDF" />
                                                <Form.Control
                                                    style={{
                                                        marginTop: '10px'
                                                    }}
                                                    value={notesTItle}
                                                    onChange={(e) => setNotesTitle(e.target.value)}
                                                    as="textarea" rows={1} placeholder="Enter title for Notes" />
                                            </div>
                                        }
                                    </div>
                                </Form>
                                {isNotes ? <Button
                                    style={{
                                        display: 'block',
                                        margin: 'auto',
                                        marginTop: '10px',
                                        marginBottom: '10px'
                                    }}
                                    disabled={!notes || !notesTItle}
                                    onClick={handleNotesSubmit}
                                >
                                    Upload the text
                                </Button> :
                                    <div
                                        style={{
                                            justifyContent: 'center',
                                            margin: '10px auto',
                                            width: '70%',
                                            marginTop: '40px'

                                        }}
                                    >
                                        <p>Users can seamlessly convert text to PDF documents through an intuitive text area interface.</p>
                                        <p>
                                            Users can enter natural language queries, and the integrated LLM processes these queries to extract relevant information
                                            from the entered text.
                                        </p>
                                    </div>

                                }

                                {/* Feature description before PDF upload */}
                            </div>
                        </Col>
                        <Form.Control
                            style={{
                                width: '50%',
                                margin: 'auto',
                            }}
                            as="select">
                            <option>Choose an LLM Model</option>
                            <option>GPT-4</option>
                            <option>GPT-3</option>
                            <option>BERT</option>
                            <option>T5</option>
                        </Form.Control>
                    </Row>
                </Collapse>
            </div>

            {
                isCollapsed && selectedFile && (
                    <div
                        style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            margin: '20px auto',
                            width: '100%',
                            height: '80vh'
                        }}
                    >
                        {/* Left half for PDF Viewer */}
                        <div style={{ flex: 1, marginRight: '20px' }}>

                            <iframe
                                style={{
                                    border: '1px solid #ddd',
                                    borderRadius: '5px',
                                    boxShadow: '0 4px 8px rgba(0, 0, 0, 0.1)',


                                }}
                                src={URL.createObjectURL(selectedFile)} width="100%" height="100%" className="w-full min-h-screen" />
                        </div>

                        {/* Right half for Chat Interface */}
                        <div
                            style={{
                                flex: 1,
                                display: 'flex',
                                flexDirection: 'column',
                                border: '1px solid #ddd',
                                padding: '10px'
                            }}
                        >
                            <div
                                style={{
                                    flex: 1
                                }}
                            >
                                <div
                                    style={{
                                        display: 'flex',
                                        justifyContent: 'space-between'
                                    }}
                                >
                                    <div
                                        style={{
                                            fontSize: '20px',
                                            fontWeight: 'bold',
                                            marginBottom: '10px'
                                        }}
                                    >
                                        Chat
                                    </div>
                                    <ImageGallery />
                                </div>
                                {isUploadLoading ? (
                                    <ChatBubble messages={[{ question: "Ask anything related to the file", isLoading: true }]} />
                                ) : (
                                    <ChatBubble messages={messages} />
                                )}
                            </div>
                            <Form onSubmit={handleChatSubmit}>
                                <InputGroup>
                                    <FormControl
                                        style={{
                                            borderRadius: '5px',
                                            padding: '5px',
                                        }}
                                        name="message" placeholder="Type a message..." />
                                    <Button
                                        style={{
                                            marginLeft: '5px',
                                            borderRadius: '5px',
                                            padding: '5px',
                                        }}
                                        type="submit" variant="primary">
                                        <Icon loading="lazy" src='https://cdn.builder.io/api/v1/image/assets/TEMP/08e6ab5962df8e9fb721c48580bd87816dca26877e5b3c813aaa4aff628c459e?placeholderIfAbsent=true&apiKey=73af7fcffe284688b01dde92703db4e5' />
                                    </Button>
                                    {/* summarize button */}
                                    <Button
                                        style={{
                                            marginLeft: '5px',
                                            borderRadius: '5px',
                                            padding: '5px',
                                        }}
                                        onClick={() => {
                                            setMessages([...messages, { question: 'Summarize', isLoading: true, isNotHistory: true }]);
                                            let chatid = `${fileid}-${id}-${allContext ? mainassistantId : fileassistantId}`;
                                            axios.post(`ChatAssistant/chatAssistant/${fileassistantId}/${mainassistantId}/${chatid}/${fileid}/${id}/Summarize/${allContext}`).then((response) => {
                                                // console.log('Chat response:', response);
                                                setMessages([...messages, { question: 'Summarize', answer: response.data, isLoading: false, isNotHistory: true }]);
                                            });
                                        }}
                                    >
                                        Summarize
                                    </Button>
                                    {/* button to switch between all files context and single file context */}
                                    <Button
                                        style={{
                                            marginLeft: '5px',
                                            borderRadius: '5px',
                                            padding: '5px',
                                        }}
                                        onClick={() => {
                                            setAllContext(!allContext);
                                        }}
                                    >
                                        {allContext ? 'Switch to Current File Context' : 'Switch to All Files Context'}
                                    </Button>
                                </InputGroup>
                            </Form>
                        </div>
                    </div>
                )
            }
        </Container >
    );
};


const Icon = styled.img`
  aspect-ratio: 1;
  object-fit: contain;
  object-position: center;
  width: 20px;
`;

export default PdfQuery;
