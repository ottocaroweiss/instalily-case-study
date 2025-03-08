import json
import os
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

def save_prompt(session_number: str, prompt: str, filename="agents/tests/prompt-log.json"):
    """
    Append a prompt entry to the JSON log file under the given session number.
    The JSON structure is:
    {
      "session_number": [
        {
          "prompts": [
            "Example prompt"
          ],
          "valid_description": ""
        },
        ...
      ]
    }
    """
    # Load existing data if the file exists; otherwise, start with an empty dict.
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    else:
        data = {}

    # Ensure there is a list for this session_number.
    if session_number not in data:
        data[session_number] = []

    # Create the new entry.
    new_entry = {
        "prompts": [prompt],
        "valid_description": ""
    }

    # Append the new entry to the session.
    data[session_number].append(new_entry)

    # Save back to the JSON file.
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def conversation_to_string(conversation):
    """
    Formats a list of message objects into a nicely formatted string.
    Each message is prefixed with its role (SYSTEM, USER, or AI).
    """
    lines = []
    for msg in conversation:
        # Determine the label from the message type
        if hasattr(msg, "role"):
            # If your messages have a 'role' attribute, use it.
            role = msg.role.upper()
        else:
            # Otherwise, determine the type via instance checking (assuming you have these classes).
            if isinstance(msg, SystemMessage):
                role = "SYSTEM"
            elif isinstance(msg, HumanMessage):
                role = "USER"
            elif isinstance(msg, AIMessage):
                role = "AI"
            else:
                role = "UNKNOWN"
        # Append the formatted message.
        # Stripping content ensures no extra whitespace, and we separate messages with two newlines.
        lines.append(f"\n_______________________________________________________________\n{role}: {msg.content.strip()}")
    return "\n\n".join(lines)