from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import uuid
from typing import Dict
from fastapi.responses import StreamingResponse
from agents.main_agent import MainAgent
from agents.utils import save_prompt
import logging
# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    session_id: str = None
    user_input: str

SESSIONS = {}
MAIN_MEMORY: Dict[str, MainAgent] = {}

def get_or_create_session(session_id: str):
    if not session_id:
        session_id = str(uuid.uuid4())

    if session_id not in SESSIONS:
        main_agent = MainAgent()
        SESSIONS[session_id] = {
            "main_agent": main_agent
        }

    return session_id, SESSIONS[session_id]


@app.get("/chat-stream")
async def chat_stream_endpoint(request: Request, session_id: str, user_input: str):
    session_id, session = get_or_create_session(session_id)
    main_agent: MainAgent = session["main_agent"]

    return StreamingResponse(main_agent.stream_run(user_input, request), media_type="text/event-stream", headers={"Access-Control-Allow-Origin": "*", 'Content-Type': 'text/event-stream;charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    'Content-Encoding': 'none',
    'Connection': 'keep-alive', "X-Accel-Buffering": "no"})


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    session_id, session = get_or_create_session(req.session_id)
    # alignment_agent: AlignmentAgent  = session["alignment_agent"]
    main_agent: MainAgent = session["main_agent"]

    main_reply = main_agent.run(req.user_input)
    save_prompt(session_id, req.user_input)
    
    return {
        "session_id": session_id,
        "agent_response": main_reply
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)