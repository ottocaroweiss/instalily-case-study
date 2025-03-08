import React, { useState, useEffect, useRef } from "react";
import "./ChatWindow.css";
import ReactMarkdown from 'react-markdown';
import { getAIMessage } from "../api/api";

function ChatWindow() {
  const defaultMessage = [
    { role: "assistant", content: "Welcome! I am your **PartSelector Support Agent**, specializing in **Dishwashers and Refrigerators**. How can I help you today?" }
  ];

  const [messages, setMessages] = useState(defaultMessage);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false); // For showing a loader/spinner

  const messagesEndRef = useRef(null);

  // On mount, create/store user ID if none exists yet
  useEffect(() => {
    let userId;//localStorage.getItem("chatUserId");
    if (!userId) {
      // Generate a random ID
      userId = Math.random().toString(36).substring(2, 11);
      localStorage.setItem("chatUserId", userId);
      console.log("Created new userId:", userId);
    } else {
      console.log("Existing userId:", userId);
    }
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);



  const handleSend = async (input) => {
    if (input.trim() !== "") {
      // Set user message
      setMessages(prevMessages => [...prevMessages, { role: "user", content: input }]);
      setInput("");
      setLoading(true);
      // Call API & set assistant message
      const newMessage = await getAIMessage(input);
      console.log("NEW Message:", newMessage);
      setMessages(prevMessages => [...prevMessages, newMessage]);

      setLoading(false);
    }
  };



  // SSE-based send
  // const handleSend = (text) => {
  //   const trimmed = text.trim();
  //   if (!trimmed) return;

  //   // 1) Immediately add user's message to state
  //   setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
  //   setInput("");

  //   // 2) Build SSE URL (server must be GET /chat-stream)
  //   const sessionId = localStorage.getItem("chatUserId") || "default-session";
  //   const url = `http://localhost:8000/chat-stream?session_id=${sessionId}&user_input=${encodeURIComponent(trimmed)}`;

  //   // 3) Open SSE
  //   setLoading(true); // Start loading indicator
  //   const eventSource = new EventSource(url);

  //   eventSource.onmessage = (chat) => {
  //     if (!chat.data) return;
  //     const chat_response = chat.data;
  //     console.log("SSE chunk:", chat_response);
  //     if (chat.event !== "error") {
  //       if (chat.event === "message") {
  //         setLoading(false);
  //       }
  //       // Full response from server
  //       setMessages((prev) => [
  //         ...prev,
  //         { role: "assistant", content: chat_response }
  //       ]);
  //       eventSource.close();

  //     } else {
  //       console.log("assistant:", chat.event);
  //       // Partial or info chunk from server
  //       setMessages((prev) => [
  //         ...prev,
  //         { role: "assistant", content: "Something went wrong... Please ask again." }
  //       ]);
  //     }
  //   };

  //   eventSource.onerror = (err) => {
  //     eventSource.close();
  //     console.error("SSE error:", err);
  //     setLoading(false);
  //   };
  // };

  return (
    <div className="messages-container">
      {messages.map((message, index) => (
        <div key={index} className={`${message.role}-message-container`}>
          {message.role === "assistant" && (
            <img
              src="https://partselectcom-gtcdcddbene3cpes.z01.azurefd.net/images/ps-logo-mobile.svg"
              alt="Assistant Icon"
              style={{ width: 40, height: 40, marginRight: "1em" }}
            />
          )}
          <div className={`message ${message.role}-message`}>
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        </div>
      ))}

      {/* Anchor for auto-scroll */}
      <div ref={messagesEndRef} />

      {/* LOADING INDICATOR */}
      {loading && (
        <div className="loader-wrapper">
          <div className="spinner"></div>
          <div className="loader-text">Thinking about parts...</div>
        </div>
      )}

      {/* Input area */}
      <div className="input-container">
        <form className="input-area"
          onSubmit={(e) => {
            e.preventDefault();
            if (loading) return;
            if (input.trim()) {
              handleSend(input);
            }
          }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message..."
            aria-label="Chat message input"
          />
          <button className= "button" type="submit">Send</button>
        </form>
      </div>
    </div>
  );
}

export default ChatWindow;
