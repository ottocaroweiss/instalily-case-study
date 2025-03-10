from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import BaseTool
from typing import List
import logging
import threading
import re
from agents.utils import conversation_to_string
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    filename="llm.log",  # File where logs should be saved
    filemode="a"       # Append mode
)
import os

from dotenv import load_dotenv
load_dotenv()  # Looks for .env in current or parent directories
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

from agents.my_tools import (
            # search_all_parts_tool,
            search_all_customer_text_on_individual_part_tool,
            search_customer_support_on_individual_part_tool,
            search_parts_of_an_appliance,
            get_part_by_id,
            get_refrigerator_or_dishwasher_by_id,
            check_model_part_compatibility,
            scrape_model_symptoms,
        )

TOOLS = [
            search_all_customer_text_on_individual_part_tool,
            search_customer_support_on_individual_part_tool,
            search_parts_of_an_appliance,
            get_part_by_id,
            get_refrigerator_or_dishwasher_by_id,
            check_model_part_compatibility,
            scrape_model_symptoms,
        ]


logger = logging.getLogger(__name__)

logger.info("Logging is now configured.")

class MainAgent:
    """
    A single agent that can:
     - see the user's query
     - call any relevant tools (search, get_part_by_id, etc.)
     - store conversation history and produce a final response with multi-turn context
    """

    def __init__(self):
        # self.searcher = ...
        self.system_prompt = """You are a chat bot for PartSelect.com, providing help around refrigerator and dishwasher parts specifically. Your main tasks are providing product details and supporting customer transactions.
        
        IMPORTANT: IF THE USER'S REQUEST IS OUT OF THIS SCOPE, POLITELY RESPOND THAT YOU CAN ONLY PROVIDE HELP ON PARTSELECT.COM'S DISHWASHER OR REFRIGERATOR PARTS. 

        Most user requests involve either an appliance (dishwasher/refrigerator) or a part (part of said appliances). If don't know what the user is looking for or providing, clarify first. You may provide information on parts, models, compatibility, and symptoms, or anything else that would help the user. You are always given the user's query and any relevant context from previous interactions.

        If they need help finding their specific refrigerator/dishwasher id, you may also provide them with the following two links:\n
        [Find Your Dishwasher Model Number](https://www.partselect.com/Find-Your-Dishwasher-Model-Number/)
        [Find Your Refrigerator Model Number](https://www.partselect.com/Find-Your-Refrigerator-Model-Number/)

        If the user needs help with repairs, you may also provide them with the following two links:\n
        "[How to Repair Dishwasher](https://www.partselect.com/Repair/Dishwasher/)"
        "[How to Repair Refrigerator](https://www.partselect.com/Repair/Refrigerator/)"
        
        If other directly relevant links are provided, share them in the same format [link title](url).

        DO NOT PROVIDE ANY INFORMATION THAT IS NOT RELEVANT TO THE USER'S REQUEST. DO NOT PROVIDE ANY INFORMATION THAT IS NOT RELATED TO DISHWASHER OR REFRIGERATOR PARTS. ONLY INCLUDE URLS THAT ARE PROVIDED TO YOU.
                
        You ONLY assist with dishwasher or refrigerator part requests (from PartSelect).
        Rules:\n\n"
        1. If the user's query is out-of-scope (not about dishwashers or refrigerators parts, or completely off topic), politely respond that you can only provide help on partselect.com's dishwasher or refrigerator parts.
        2. If the user is done or just says 'thank you', you can politely say goodbye and mention that you are there if they need anymore help.\n
        """

        self.with_tools_system_prompt = self.system_prompt + "\n You may also call on your tools to assist the user. Please make use of your tools when it makes sense, but do not mention them to the user. Try to get either a part or appliance ID from the user, and then use your tools to provide the user with the information they need. Use the search tools can answer a question. The process should usually be to ask the user for a part id or a dishwaser/refrigerator ID, then you can access speciifc symptoms or use the search tools to answer more questions. If you can't find the information, you can ask the user for more information or let them know you couldn't find the information they requested."
        # Initialize the LLM
        llm_with_tools = ChatDeepSeek(model="deepseek-chat", max_retries=2)
        # Bind tools so LLM can produce structured calls
        self.llm_with_tools = llm_with_tools.bind_tools(TOOLS)
        self.llm = ChatDeepSeek(model="deepseek-chat", max_retries=2)
        self.tools = {tool.name: tool for tool in TOOLS}

        # We store the “tool context” and “conversation context” as AI text from summarizer agents.
        self.tool_context = None
        self.conversation_context = None

        # self.conversation is rebuilt on every run() to include system prompt, tool context, conversation context, and user input
        self.conversation: List = []

    def get_response(self, withTools: bool = False):
        """
        Single helper method to invoke the LLM, optionally with or without tools.
        Also calls clean_response() on response.content and returns the full response object.
        """
        possible_system_prompt: str = self.conversation[0].content
        if possible_system_prompt.startswith("You are a chat bot for PartSelect.com, "):
            self.conversation = self.conversation[1:]
        if withTools:
            self.conversation.insert(0, SystemMessage(self.with_tools_system_prompt))
            response = self.llm_with_tools.invoke(self.conversation)
        else:
            self.conversation.insert(0, SystemMessage(self.system_prompt))
            response = self.llm.invoke(self.conversation)
        response.content = self.clean_response(response.content)
        return response

    @staticmethod
    def clean_response(text: str) -> str:
        """
        Clean up the response text by removing double newlines.
        """
        text = text.strip()
        while "\n\n" in text:
            text = text.replace("\n\n", "\n")
        return text

    def format_response(self, text: str, status: str = "message") -> str:
        """
        Return SSE-friendly response with optional status.
        """
        return f"event: {status}\n\ndata: {self.clean_response(text)}\n\n"

    def run(self, user_input: str, retry = False) -> str:
        """
        Orchestrate a conversation with the user:
         1) Build the conversation: [System, AI(tool context), AI(conversation context), User(user input)]
         2) Call the LLM; if tool calls are made, handle them.
         3) Return final LLM text.
         4) In a finally block, concurrently update tool_context and conversation_context.
        """
        logger.info("PREVIOUS CONVERSATION: %s", self.conversation)
        # Force the conversation format
        if not retry:
            self.conversation = []
            if self.tool_context:
                self.conversation.append(SystemMessage("INFO FROM YOUR RAG AGENT:\n" + self.tool_context))
            if self.conversation_context:
                self.conversation.append(SystemMessage("CONVERSATION CONTEXT: \n" + self.conversation_context))
            self.conversation.append(HumanMessage(user_input))
        else:
            self.conversation.append(HumanMessage("RETRY: " + user_input))
        # Track the new messages (the user input is at index -1)
        # Make a local copy for any summarizer logic

        try:
            # First pass: LLM sees system + tool context + conversation context + user input
            logger.info("Invoking LLM for the first pass.")
            response = self.get_response(withTools=True)
            logger.info("LLM response (first pass): %s", response.content)
            if response.content:
            # Insert the LLM’s response so the next pass can see it
                self.conversation.append(AIMessage(response.content))

            # If the LLM made any tool calls, handle them
            if response.tool_calls:
                logger.info("Tool calls detected: %s", response.tool_calls)
                tools_called = []
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tools_called.append(tool_name)
                    selected_tool = self.tools.get(tool_name)
                    if not selected_tool:
                        logger.warning("Tool '%s' not found.", tool_name)
                        continue
                    
                    tool_call_det = f"Called {tool_name} with args - {tool_args}" 
                    logger.info(tool_call_det)
                    # Invoke the tool
                    tool_result = selected_tool.invoke(tool_args)
                    if tool_result.startswith("FAILURE:") and not retry:
                        logger.error(f"Error invoking tool {tool_name}: {tool_result}")
                        self.conversation.append(SystemMessage(f"FAILURE invoking tool {tool_name}: {tool_result} {tool_result}"))
                        return self.run(user_input, retry=True)
                    tool_response_det = tool_call_det + ", producing the following response: \n"
                    logger.info(tool_response_det + tool_result)

                    # Put the tool response into the conversation
                    tool_msg = f"NEW FROM RAG AGENT - {tool_response_det}: {tool_result}"
                    self.conversation.append(AIMessage(tool_msg))
                # Second pass: ask LLM to incorporate tool results
                logger.info("Invoking LLM for the second pass after tool calls.")
                final_system_message ="The user has no knowledge of your tool use. Please continue the conversation naturally by following your system prompt. Please be concise, providing only the relevant information in your response."
                if tools_called == ["get_refrigerator_or_dishwasher_by_id"] or tools_called == ["get_part_by_id"]:
                    final_system_message += "If your rag agent has not provided information directly relevant to the question (only given basic info about an item), you may ask the user if they would like you to perform a wider search. Please do not make anything up or provide false information. If you don't know the answer, it's better to tell the user that you're not sure or offer to look up more information."
                self.conversation.append(SystemMessage(final_system_message))
                final_response = self.get_response(withTools=False)
                final_text = self.clean_response(final_response.content)
                self.conversation.append(AIMessage(final_response.content))
            else:
                # No tool calls, so the first pass is the final
                final_text = self.clean_response(response.content)

            logger.info("Final CONVERSATION: %s", conversation_to_string(self.conversation))
            return final_text

        except Exception as e:
            logger.error("Error during run: %s", e, exc_info=True)
            response = "An error occurred. Please try again."
            return response

        finally:
            # After returning, we want to update:
            # 1) self.tool_context (via a “tool context agent”)
            # 2) self.conversation_context (via a “conversation context agent”)
            original_conversation = self.conversation.copy()
            def update_tool_context():
                """
                Summarize the tool usage or relevant content from the conversation,
                and set self.tool_context accordingly.
                """
                # Quick example of summarizing tool usage from new_messages
                # In real usage, you might gather all AI tool-call messages from the entire conversation.
                if not original_conversation:
                    logger.info("No conversation found to summarize.")
                    return
                conversation_context = ""
                new_tool_context = ""
                old_rag_context = ""
                for msg in original_conversation:
                    if isinstance(msg, HumanMessage):
                        conversation_context += f"User: \n{msg.content}\n"
                    elif isinstance(msg, AIMessage):
                        conversation_context += f"AI: \n{msg.content}\n"
                    elif isinstance(msg, SystemMessage) and self.system_prompt not in msg.content:
                        if msg.content.startswith("INFO FROM YOUR RAG AGENT:"):
                            self.conversation_context += msg.content
                            old_rag_context += re.sub(r"^INFO FROM RAG AGENT:\s*", "", msg.content)
                        elif msg.content.startswith("NEW FROM YOUR RAG AGENT:"):
                            cleaned = re.sub(r"^NEW FROM RAG AGENT - \{.*?\}:\s*", "", msg.content)
                            new_tool_context = re.sub(r"^NEW FROM RAG AGENT - \{.*?\}:\s*", "", msg.content)
                        else:
                            conversation_context += f"Previous context from conversation: \n{msg.content}\n"

                if not self.tool_context:
                    system_prompt = "You are RAG agent that maintains the relevant information provided by tool calls from a previous conversation. Your response will be provided to the main agent in the next round of messages. Please maintain all text from the new tool call that could serve useful in the next round. Your response should mirror the format of the tool response. In other words, remove any excess text provided by the tool that is not relevant to conversation and respond with this streamlined version of the tool response."
                    new_tool_context = f"NEW INFO FROM TOOL: {new_tool_context}. \n Please respond with the streamlined version of the tool response to maintain for the next round of conversation."

                else:
                    system_prompt = "You are RAG agent that updates and streamlines relevant information context for an e-commerce chat bot following tool calls in a conversation. Your response will be provided to the main agent in the next round of messages. Please update the 'INFO FROM YOUR RAG AGENT' with the relevant information provided by the new tool call. Your response should mirror the format of the tool and other RAG agent responses. So, remove any excess text provided by the tool or previous agent that is not relevant to conversation, and add all information provided by the tool which could serve useful in future responses."
                    new_tool_context = f"CURRENT INFO: {old_rag_context} \n\n NEW INFO FROM TOOL: {new_tool_context}. Please respond with the updated and streamlined version of the tool response to maintain for the next round of converssation."
                update_messages = [
                        SystemMessage(system_prompt),
                        HumanMessage("CONVERSATION OVERVIEW:\n" + conversation_context),
                        HumanMessage(new_tool_context),
                    ]
                try:
                    summary = self.llm.invoke(update_messages)
                    cleaned = self.clean_response(summary.content)
                    cleaned = re.sub(r"^INFO FROM[A-Z\s]+:\s*", "", cleaned)
                    self.tool_context = cleaned
                except Exception as e2:
                    logger.error("Error updating tool_context: %s", e2)
            
            def update_conversation_context():
                """
                Summarize the user-assistant conversation (excluding tool use) and update self.conversation_context.
                """
                if not original_conversation:
                    logger.info("No conversation found to summarize.")
                    return

                new_conversation_context = ""
                previous_conversation_context = ""

                # Extract relevant messages from the conversation
                for msg in original_conversation:
                    if isinstance(msg, HumanMessage):
                        new_conversation_context += f"User: \n{msg.content}\n"
                    elif isinstance(msg, AIMessage):
                        new_conversation_context += f"AI: \n{msg.content}\n"
                    elif isinstance(msg, SystemMessage) and self.system_prompt not in msg.content:
                        previous_conversation_context = re.sub(r"^CONVERSATION CONTEXT:\s*", "", msg.content)
                

                # If there's no prior conversation context, establish the first one
                if not self.conversation_context:
                    system_prompt = (
                        "You are a RAG agent maintaining relevant conversation history for an e-commerce chat bot. "
                        "Your response will be provided to the main agent in the next round of messages. "
                        "Please summarize the user-assistant interaction while keeping only information relevant "
                        "for future responses."
                    )
                    new_conversation_context = (
                        f"NEW CONVERSATION INFO: {new_conversation_context}. \n"
                        "Please summarize the relevant details from this conversation to maintain for future context."
                    )
                
                # If a prior conversation context exists, update it
                else:
                    system_prompt = (
                        "You are a RAG agent that updates conversation history for an e-commerce chat bot. "
                        "Your response will be used to maintain continuity in future interactions. "
                        "Please update the Conversation Context to incorporate the interactions"
                        "from the latest conversation. Remove redundant details while ensuring all critical "
                        "context is preserved."
                    )
                    new_conversation_context = (
                        f"CURRENT CONVERSATION CONTEXT: \n {previous_conversation_context} \n\n"
                        f"NEW CONVERSATION: \n {new_conversation_context}. \n"
                        "Please provide an updated, streamlined version of the conversation context for the next round."
                    )

                update_messages = [
                    SystemMessage(system_prompt),
                    HumanMessage(new_conversation_context),
                    HumanMessage("Given the newly provided user-assistance interaction, please update the conversation context according to your guidelines."),
                ]

                try:
                    summary = self.llm.invoke(update_messages)
                    cleaned = self.clean_response(summary.content)
                    cleaned = re.sub(r"^[A-Z\s]CONVERSATION[A-Z\s]+:\s*", "", cleaned)  # Remove any leading "INFO FROM" text
                    self.conversation_context = cleaned
                except Exception as e2:
                    logger.error("Error updating conversation_context:\n %s", e2)
            # Launch both summarizers concurrently
            t_tool = threading.Thread(target=update_tool_context)
            t_conv = threading.Thread(target=update_conversation_context)
            t_tool.start()
            t_conv.start()


            logger.info("Conversation cleanup triggered for tool context and conversation context.")
            logger.info("Conversation reset after run.")
