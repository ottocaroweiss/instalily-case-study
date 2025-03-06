import React, { useState } from "react";
import "./App.css";
import ChatWindow from "./components/ChatWindow";

function App() {

  return (
    <div className="App">
      <div className="heading">
        <h3>PartSelector Chat</h3>
      </div>
        <ChatWindow/>
    </div>
  );
}

export default App;
