import React, { useState, useRef } from 'react';
import { Container, Form, Button, InputGroup, FormControl, Collapse } from 'react-bootstrap';
import { XCircle } from 'react-bootstrap-icons'; // Import the Bootstrap Icon for the close button
import './fileupload.css';

const PdfQuery = () => {
    const [selectedFile, setSelectedFile] = useState(null);
    const [isDragging, setIsDragging] = useState(false);
    const [isCollapsed, setIsCollapsed] = useState(false);
    const fileInputRef = useRef(null);

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
            console.log('File ready to upload:', selectedFile);
            setIsCollapsed(true);  // Collapse the form after the file is uploaded
        }
    };

    const handleRemoveFile = () => {
        setSelectedFile(null);
        setIsCollapsed(false);  // Expand the form after removing the file
    };

    return (
        <Container>
            <div>
                {isCollapsed && selectedFile ? (
                    <div style={{
                        display: 'flex',
                        justifyContent: 'center',
                        alignItems: 'center',
                        margin: '10px auto'
                    }}>
                        <Button
                            onClick={() => setIsCollapsed(!isCollapsed)}
                            aria-controls="file-upload-collapse"
                            aria-expanded={isCollapsed}
                            style={{
                                marginRight: '10px'
                            }}
                        >
                            {'File Uploaded: ' + selectedFile.name}
                        </Button>
                    </div>
                ) : null}

                <Collapse in={!isCollapsed || !selectedFile}>
                    <div id="file-upload-collapse">
                        <Form>
                            <div
                                className={`file-drop-box ${isDragging ? 'dragging' : ''}`}
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                                onClick={handleBoxClick}
                            >
                                <Form.Label>
                                    {selectedFile ? selectedFile.name : 'Drag and drop a file here, or click to select a file'}
                                </Form.Label>
                                {selectedFile && (
                                    <XCircle
                                        onClick={handleRemoveFile}
                                        size={20}
                                        style={{
                                            cursor: 'pointer',
                                            marginLeft: '10px',
                                        }}
                                    />
                                )}
                                <Form.Control
                                    type="file"
                                    accept='.pdf'
                                    onChange={handleFileSelect}
                                    ref={fileInputRef}
                                    style={{ display: 'none' }}
                                />
                            </div>
                            <Button
                                style={{
                                    display: 'block',
                                    margin: 'auto',
                                    marginTop: '10px',
                                }}
                                onClick={handleSubmit}
                                disabled={!selectedFile}
                            >
                                Upload
                            </Button>
                        </Form>
                        {/* feature disaription before pdf upload */}
                        <div style={{
                            // display: ',
                            justifyContent: 'center',
                            alignItems: 'center',
                            margin: '10px auto',
                            width: '70%',
                        }}>
                            <p>Users can seamlessly upload PDF documents through an intuitive drag-and-drop interface or by selecting files manually. The system supports various formats, making it convenient for users to analyze reports, research papers, contracts, or any other document.</p>
                            <p>Users can enter natural language queries, and the integrated LLM processes these queries to extract relevant information from the uploaded PDF. This allows users to quickly find answers or specific data points without manually searching through lengthy documents.
                                The system can handle complex queries, offering precise answers based on the context, as well as summarizing key points from the PDF.</p>
                        </div>
                        {/* render a dropdown for llm Modles to query with */}
                        <div style={{
                            display: 'flex',
                            justifyContent: 'center',
                            alignItems: 'center',
                            margin: '10px auto',
                            width: '70%',
                        }}>
                            <Form.Control as="select">
                                <option>Choose an LLM Model</option>
                                <option>GPT-4</option>
                                <option>GPT-3</option>
                                <option>BERT</option>
                                <option>T5</option>
                            </Form.Control>
                        </div>
                    </div>
                </Collapse>
            </div>

            {isCollapsed && selectedFile && (
                <div style={{
                    position: 'fixed',
                    bottom: '20px',
                    width: '70%',
                    display: 'flex',
                    justifyContent: 'center',
                }}>
                    <InputGroup className="mb-3">
                        <FormControl
                            placeholder="Search through the uploaded file..."
                            aria-label="Search"
                            aria-describedby="basic-addon2"
                        />
                    </InputGroup>
                </div>
            )}
        </Container>
    );
};

export default PdfQuery;
