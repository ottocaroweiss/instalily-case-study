export const getAIMessage = async (userQuery, sessionId) => {
    try {
      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId || "default-session",  // Ensure session_id is always sent
  
          user_input: userQuery,
        }),
      });
  
      if (!response.ok) {
        throw new Error("Failed to fetch AI response");
      }
  
      const data = await response.json();
  
      // Extract response from API
      return {
        role: "assistant",
        content: data.agent_response || "Sorry, I couldn't understand that.",
      };
  
    } catch (error) {
      console.error("Error fetching AI response:", error);
      return {
        role: "assistant",
        content: "Oops! There was an error connecting to AI.",
      };
    }
  };
