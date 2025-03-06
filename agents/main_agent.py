from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import BaseTool
from typing import List, AsyncGenerator
import logging
from sse_starlette.sse import EventSourceResponse
from fastapi import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MainAgent:
    """
    A single agent that can:
     - see the user's query
     - call any relevant tools (search, get_part_by_id, etc.)
     - store conversation history and produce a final response with multi-turn context
    """

    def __init__(self, tools: List[BaseTool]):
        #self.searcher = 
        self.system_prompt = """You are a chat bot for PartSelect.com, specializing in refrigerator and dishwasher parts. Your main tasks are providing product details and supporting customer transactions.

        Most user requests involve either an appliance (dishwasher/refrigerator) or a part (part of said appliances). If don't know what the user is looking for or providing, clarify first. You may provide information on parts, models, compatibility, and symptoms, or anything else that would help the user.
        
        You ONLY assist with dishwasher or refrigerator part requests (from PartSelect).
        Rules:\n\n"
        1. If the user's query is out-of-scope (not about dishwashers or refrigerators parts, or completely off topic), politely respond that you can only provide help on partselect.com's dishwasher or refrigerator parts.
        2. If the user is done or just says 'thank you', you can politely say goodbye and mention that you are there if they need anymore help.\n

        If they need help finding their model id, you may also provide them with the following two links:\n
        [Find Your Dishwasher Model Number](https://www.partselect.com/Find-Your-Dishwasher-Model-Number/)
        [Find Your Refrigerator Model Number](https://www.partselect.com/Find-Your-Refrigerator-Model-Number/)

        If the user needs help with repairs, you may also provide them with the following two links:\n
        "[How to Repair Dishwasher](https://www.partselect.com/Repair/Dishwasher/)"
        "[How to Repair Refrigerator](https://www.partselect.com/Repair/Refrigerator/)"
        
        If other directly relevant links are provided, share them in the same format [link title](url).

        Be economic with your tool calls, accounting for response time. Do not make unnessecarry calls. Ensure that the information you provide is accurate and relevant to the user's needs.
        
        DO NOT PROVIDE ANY SPECIFIC INFORMATION THAT DOES NOT COME FROM THE TOOLS. DO NOT PROVIDE ANY INFORMATION THAT IS NOT RELEVANT TO THE USER'S REQUEST. DO NOT PROVIDE ANY INFORMATION THAT IS NOT RELATED TO DISHWASHER OR REFRIGERATOR PARTS. 
        """
        # Initialize the LLM
        self.llm = ChatDeepSeek(model="deepseek-chat", max_retries=2)
        # Bind tools so LLM can produce structured calls
        self.llm_with_tools = self.llm.bind_tools(tools)
        self.tools = {tool.name: tool for tool in tools}
        # Keep a conversation list of (role, content).
        # We'll place the system prompt as the first assistant message or in a separate store.
        self.conversation: List = [
            SystemMessage(self.system_prompt)
        ]
    

    def cleanup_conversation(self, new_messages: List):
        """
        Summarizes all user+assistant messages (ignoring tool calls/system prompts),
        then replaces the entire conversation with:
        [SystemMessage(self.system_prompt), SystemMessage(summary)]
        so we keep the important context while discarding irrelevant details.
        """
        logger.info("Starting cleanup_conversation with %d new_messages", len(new_messages))
        
        # Gather user & AI messages (ignore system & tool messages)
        conversation_to_summarize = []
        conversation_to_summarize.append({"role": "user", "content": new_messages[0].content})
        logger.info("Added first message for summarization: %s", new_messages[0].content)
        
        for i, msg in enumerate(new_messages[1:], start=1):
            if isinstance(msg, HumanMessage):
                conversation_to_summarize.append({"role": "tool", "content": msg.content})
                logger.info("Added HumanMessage at index %d for summarization: %s", i, msg.content)
            elif isinstance(msg, AIMessage):
                conversation_to_summarize.append({"role": "assistant", "content": msg.content})
                logger.info("Added AIMessage at index %d for summarization: %s", i, msg.content)
            else:
                logger.info("Skipping message of type %s at index %d", type(msg), i)

        # If there's no user/assistant content, do nothing
        if not conversation_to_summarize:
            logger.info("No conversation to summarize. Exiting cleanup_conversation.")
            return

        # The prompt for summarization
        system = (
            "You are a context maintainer conversation chain between a user and a chat bot on an appliance part e-commerce site. "
            "Please summarize the conversation so far. Your response will be provided as context for the main chat bot. "
            "Maintain relevant context from the conversation thus far, including relevant information from tool calls if present. "
        )

        # Build a summarizer conversation (we’ll use the same self.llm or a smaller model)
        summarizer_messages = [
            SystemMessage(system),
            HumanMessage(
                f"Conversation to summarize:\n{conversation_to_summarize}\n\n"
            )
        ]
        logger.info("Summarizer messages constructed: %s", summarizer_messages)

        # Invoke the LLM to get a short summary
        summary_response = self.llm.invoke(summarizer_messages)
        logger.info("Received summary response from LLM: %s", summary_response.content)
        
        summary_text = "Conversation context provided by summarizer agent: \n" + summary_response.content.strip()
        logger.info("Final summary text: %s", summary_text)

        # Now, rebuild self.conversation by returning a summary message (to be appended as a new system message)
        return AIMessage(summary_text)

    @staticmethod
    def format_response(text: str, status: str = "message") -> str:
        """
        Remove double newlines from a text.
        """
        while "\n\n" in text:
            text = text.replace("\n\n", "\n")
        
        return f"event: {status}\n\ndata: {text}\n\n"
    
    async def stream_run(self, user_input: str, request: Request=None) -> AsyncGenerator[str, None]:
        """
        Similar to run(), but yields each agent message as a formatted SSE string.
        That way, we can push partial/intermediate responses via SSE.
        """

        # Append user input
        self.conversation.append(HumanMessage(user_input))
        if len(self.conversation) > 3:
            new_messages = self.conversation[-2:]
        else:
            new_messages = self.conversation[1:]
        
        original_conversation = self.conversation.copy()
        logger.info("User input appended to conversation.")
        try:
            # First LLM pass
            response = self.llm_with_tools.invoke(self.conversation)
            self.conversation.append(AIMessage(response.content))
            logger.info("LLM response (first pass): %s", response.content)
            new_messages.append(AIMessage(response.content))
            
            # If LLM made any tool calls, handle them
            if response.tool_calls:
                logger.info("Tool calls detected: %s", response.tool_calls)
                # Mapping from tool names to informative messages.
                informative_messages = {
                    "search_all_parts_tool": "Searching for parts...",
                    "search_all_customer_text_on_individual_part_tool": "Reviewing customer reviews and stories...",
                    "search_customer_support_on_individual_part_tool": "Reviewing customer support Q&A...",
                    "get_part_by_id": "Gathering detailed information for the specified part...",
                    "get_appliance_by_id": "Retrieving details for the specified appliance model...",
                    "check_model_part_compatibility": "Checking compatibility between the part and the appliance...",
                    "scrape_model_symptoms": "Fetching symptom details for the appliance...",
                }
        
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
        
                    selected_tool = self.tools.get(tool_name)
                    if not selected_tool:
                        logger.warning("Tool '%s' not found.", tool_name)
                        continue
                    # Yield an informative message for this tool call
                    yield self.format_response(informative_messages.get(tool_name, f"Invoking tool {tool_name}..."), status="update")
                    info_msg = informative_messages.get(tool_name, f"Invoking tool {tool_name}...")
                    logger.info("Yielding info message: %s", info_msg)
        
                    # Execute the tool
                    tool_result = selected_tool.invoke(tool_args)
                    logger.info("Tool '%s' invoked with args %s; result: %s", tool_name, tool_args, tool_result)
        
                    # Create a message with the tool result details
                    msg_text = (
                        f"**Tool Called**: {tool_name}\n\n"
                        f"**Args**: {tool_args}\n\n"
                        f"**Tool Result**:\n{tool_result}\n"
                    )
                    self.conversation.append(AIMessage(msg_text))
                    new_messages.append(AIMessage(msg_text))
                    logger.info("Tool result added to conversation: %s", msg_text)
                yield self.format_response(informative_messages.get(tool_name, f"Putting parts together..."), status="update")
                # Second pass: Incorporate tool results
                system_msg = ("Here are the tool results (if any). The user has no knowledge of your tool use. "
                            "Please continue the conversation naturally.")
                self.conversation.append(SystemMessage(system_msg))
                new_messages.append(SystemMessage(system_msg))
                final_response = self.llm_with_tools.invoke(self.conversation)
                self.conversation.append(AIMessage(final_response.content))
                new_messages.append(AIMessage(final_response.content))
                logger.info("LLM final response (after tool calls): %s", final_response.content)
                response = self.format_response(final_response.content)
                yield response
            else:
                response = self.format_response(response.content)
                yield response
        except Exception as e:
            logger.error("Error during stream_run: %s", e)
            response = self.format_response("An error occurred. Please try again.", status="error")
            yield response
        finally:
            original_conversation.append(self.cleanup_conversation(new_messages))
            self.conversation = original_conversation
            logger.info("Conversation reset after stream_run.")

    def run(self, user_input: str) -> str:
        """
        Orchestrate a conversation with the user:
         1) Append the system prompt and user message.
         2) Call the LLM; if tool calls are made, handle them.
         3) Return final LLM text.
        """
        self.conversation.append(HumanMessage(user_input))
        logger.info("User input appended to conversation.")

        # First pass: LLM sees prompt + user input
        response = self.llm_with_tools.invoke(self.conversation)
        self.conversation.append(AIMessage(response.content))
        logger.info("LLM response (first pass): %s", response.content)

        # If LLM made any tool calls, handle them
        if response.tool_calls:
            logger.info("Tool calls detected: %s", response.tool_calls)
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                selected_tool = self.tools.get(tool_name)
                if not selected_tool:
                    logger.warning("Tool '%s' not found.", tool_name)
                    continue
                logger.info("Tool '%s' called with args: %s", tool_name, tool_args)
                # Invoke the tool
                tool_result = selected_tool.invoke(tool_args)
                logger.info("Tool '%s' result: %s", tool_name, tool_result)
                text = f"You called tool '{tool_name}' with arguments '{tool_args}' result: \n\n {tool_result}"
                self.conversation.append(AIMessage(content=text))
            logger.info("Conversation so far: %s", self.conversation)
            # Second pass: Ask LLM to incorporate tool results
            self.conversation.append(
                SystemMessage("Here are the tool results (if any). The user has no knowledge of your tool use. Please continue the conversation naturally, without revealing tool use.")
            )
            response = self.llm.invoke(self.conversation)
            self.conversation.append(AIMessage(response.content))
            logger.info("LLM final response (after tool calls): %s", response.content)

        # Return the final text
        final_text = response.content.strip()
        logger.info("Final agent response: %s", final_text)
        return final_text
