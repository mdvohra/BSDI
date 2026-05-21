import React, { useState } from 'react';
import { chatWithModel } from '../services/api';
import { MessageCircle, X } from "lucide-react"; // nice icons

const Chat = ({ treeCount, totalArea, averageTreeArea, imageMetadata }) => {
  const [query, setQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [isOpen, setIsOpen] = useState(false); // toggle chat visibility

  const handleSend = async () => {
    if (!query.trim()) return;

    const newMessage = { sender: 'user', text: query };
    setChatHistory([...chatHistory, newMessage]);
    setLoading(true);
    setError('');

    try {
      const response = await chatWithModel(
        query,
        treeCount,
        totalArea,
        averageTreeArea,
        imageMetadata
      );
      const botMessage = { sender: 'bot', text: response.response };
      setChatHistory([...chatHistory, newMessage, botMessage]);
      setQuery('');
    } catch (err) {
      console.error(err);
      setError('Failed to get response from the server.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {/* Floating Icon Button */}
      {/* Floating Icon Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 bg-blue-600 p-4 rounded-full shadow-lg hover:bg-blue-700 transition"
          style={{ display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <img
            src="https://cdn-icons-png.flaticon.com/128/15861/15861364.png"
            alt="Chat Icon"
            className="w-6 h-6"
          />
        </button>
      )}


      {/* Chat Window */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 w-80 h-96 flex flex-col bg-white shadow-2xl rounded-2xl p-4">
          {/* Header */}
          <div className="flex justify-between items-center border-b pb-2 mb-2">
            <h2 className="text-lg font-semibold">Assistant</h2>
            <button onClick={() => setIsOpen(false)} className="text-gray-500 hover:text-gray-800">
              <X size={20} />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto mb-2">
            {chatHistory.map((msg, index) => (
              <div
                key={index}
                className={`mb-2 flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`px-4 py-2 rounded ${msg.sender === 'user'
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-200 text-gray-800'
                    }`}
                >
                  {msg.text}
                </div>
              </div>
            ))}
            {loading && (
              <div className="mb-2 flex justify-start">
                <div className="px-4 py-2 bg-gray-200 text-gray-800 rounded">
                  Querying...
                </div>
              </div>
            )}
          </div>

          {/* Error */}
          {error && <div className="text-red-500 mb-2">{error}</div>}

          {/* Input */}
          <div className="flex space-x-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="flex-1 border rounded px-3 py-2"
              placeholder="Type your query..."
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSend();
              }}
            />
            <button
              onClick={handleSend}
              disabled={loading}
              className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Chat;
