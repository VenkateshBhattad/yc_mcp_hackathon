import asyncio
import os
from typing import List, Dict, Any, Union
from contextlib import AsyncExitStack

import gradio as gr
from gradio.components.chatbot import ChatMessage

# Import necessary modules from langchain_mcp.py
from langchain_community.chat_models import ChatOCIGenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage
# from IPython.display import Image, display # May not be necessary in Gradio
import re
import base64

# Load environment variables from .env file (OpenAI API key, etc.)
from dotenv import load_dotenv
load_dotenv()

# asyncio event loop setup
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

class LangchainMCPApp:
    def __init__(self):
        self.mcp_client = None
        self.modeling_agent = None # Agent for 3D modeling
        self.exit_stack = None

        # Initialize each LLM model (here, assuming the same model is used and roles are differentiated by prompts)
        # Can be changed to different models or settings as needed
        self.calculation_model = ChatAnthropic(model="claude-3-7-sonnet-20250219") # LLM for design calculations
        self.documentation_model = ChatAnthropic(model="claude-3-7-sonnet-20250219") # LLM for document generation
        # Model for the 3D modeling agent (passed when creating the agent)
        self.modeling_llm = ChatAnthropic(model="claude-3-7-sonnet-20250219")


    async def _initialize_modeling_agent_and_tools(self):
        """Initializes the MCP client and Langchain agent for 3D modeling asynchronously."""
        # Close existing ExitStack if any (in case of re-initialization)
        if self.exit_stack:
            try:
                await self.exit_stack.aclose()
            except Exception as e:
                print(f"Error closing existing exit_stack: {e}")

        self.exit_stack = AsyncExitStack()

        # MultiServerMCPClient configuration (brought from langchain_mcp.py)
        self.mcp_client = await self.exit_stack.enter_async_context(
            MultiServerMCPClient(
                {
                    # "stock": {
                    #     "command": "python",
                    #     "args": ["yahoofinance_server.py"],
                    #     "transport": "stdio",
                    # },
                    # "chart": {
                    #     "command": "python",
                    #     "args": ["repl_server.py"],
                    #     "transport": "stdio",
                    # },
                    "playwright": {
                        "command": "npx",
                        "args": ["@playwright/mcp@latest"],
                        "env": {
                        "DISPLAY": ":1" # Set according to your environment
                        }
                    },
                    "freecad": {
                        "command": "uvx",
                        "args": [
                        "freecad-mcp"
                        ]
                    }
                }
            )
        )
        tools = self.mcp_client.get_tools()
        self.modeling_agent = create_react_agent(self.modeling_llm, tools) # Use modeling_llm
        return "MCP Client and Modeling Agent initialized successfully."

    async def initialize_resources(self) -> str:
        """Initializes resources asynchronously, mainly for the modeling agent."""
        if not self.modeling_agent: # Initialize if the modeling agent is not already initialized
            return await self._initialize_modeling_agent_and_tools() # Call with await
        return "MCP Client and Modeling Agent are already initialized."

    async def _run_calculation_step(self, user_query: str, history: List[Dict[str, Any]]) -> str:
        """Step 1: Use the design calculation LLM to determine specifications."""
        # Include history and current user request in the prompt
        prompt_messages = []
        for item in history:
            if item["role"] == "user" and item["content"]:
                prompt_messages.append(HumanMessage(content=item["content"]))
            elif item["role"] == "assistant" and item["content"]: # Also include past AI responses in the context
                prompt_messages.append(AIMessage(content=item["content"]))

        prompt_messages.append(HumanMessage(content=f"User\'s request: '{user_query}'\n\nBased on the above request, calculate the necessary mechanical specifications and determine the detailed specifications. Please describe them clearly in bullet points."))

        try:
            response = await self.calculation_model.ainvoke(prompt_messages)
            return response.content
        except Exception as e:
            print(f"Error in calculation step: {e}")
            return f"An error occurred during design calculation: {str(e)}"

    async def _run_modeling_step(self, specifications: str) -> str:
        """Step 2: Use the 3D model LLM (agent) to generate a 3D model."""
        if not self.modeling_agent:
            init_status = await self.initialize_resources()
            if "error" in init_status.lower() or "not initialized" in init_status.lower():
                return f"Failed to initialize modeling agent: {init_status}"

        prompt = f"Create a 3D model based on the following specifications:\n{specifications}\nThe final output should be an image of the generated model (data:image/png;base64 format)."

        try:
            # modeling_agent is created with create_react_agent, so input is in the format {"messages": [HumanMessage(...)]}
            agent_input = {"messages": [HumanMessage(content=prompt)]}
            agent_response = await self.modeling_agent.ainvoke(agent_input)

            response_content = ""
            if isinstance(agent_response, dict):
                if "output" in agent_response:
                    response_content = str(agent_response["output"])
                elif "messages" in agent_response and isinstance(agent_response["messages"], list):
                    ai_messages = [msg for msg in agent_response["messages"] if isinstance(msg, AIMessage)]
                    if ai_messages:
                        # Get the content of the last AI message and extract appropriately if it contains thought processes
                        final_ai_message_content = ai_messages[-1].content
                        # Check if base64 image data is included
                        match = re.search(r'(data:image/png;base64,[A-Za-z0-9+/=]+)', final_ai_message_content)
                        if match:
                            response_content = match.group(1) # Return only image data
                        else:
                            response_content = final_ai_message_content # Text response
                    else:
                        response_content = str(agent_response) # If there are no AI messages
                else:
                    response_content = str(agent_response) # If neither "output" nor "messages" exists
            else:
                response_content = str(agent_response) # If not a dict

            return response_content
        except Exception as e:
            print(f"Error in modeling step: {e}")
            return f"An error occurred during 3D modeling: {str(e)}"

    async def _run_documentation_step(self, user_query: str, calculation_output: str, modeling_output: str) -> str:
        """Step 3: Use the final output LLM to generate documentation."""
        prompt = f"""Based on the following information, create a design proposal document for the user.
Assume it will be saved in Markdown format as 'proposal.md'.

Original user request:
{user_query}

Design calculation results and specifications:
{calculation_output}

Summary of 3D modeling results:
{( "3D model generated successfully. Please check the preview in the chat." if "data:image/png;base64" in modeling_output else modeling_output if modeling_output else "3D model was not generated.")}

The document should include the following elements:
1.  Summary of user request
2.  Proposed specifications (mechanical specs, etc.)
3.  Design points and rationale
4.  Information about the 3D model (if generated)
5.  Next steps or recommendations (if any)
"""
        try:
            response = await self.documentation_model.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            print(f"Error in documentation step: {e}")
            return f"An error occurred during document generation: {str(e)}"

    async def _execute_full_flow(self, user_query: str, history: List[Dict[str, Any]]):
        """Executes the entire 3-step processing flow."""
        # Step 1: Design calculation
        # Format history information to pass
        current_chat_history_for_calc = []
        for entry in history:
            if entry["role"] == "user":
                current_chat_history_for_calc.append(HumanMessage(content=entry["content"]))
            elif entry["role"] == "assistant":
                current_chat_history_for_calc.append(AIMessage(content=entry["content"]))

        # Also include the user's current message in the history for the design calculation LLM
        # calculation_history_context = current_chat_history_for_calc + [HumanMessage(content=user_query)]

        # In the first step, pass the user's latest query and the history up to that point
        # processed_history, when passed from chat_interface, is the past interaction excluding the current user_query
        calculation_specifications = await self._run_calculation_step(user_query, history) # history excludes the most recent user_query

        # Prepare messages for UI display
        flow_responses = []
        flow_responses.append({"role": "assistant", "content": f"**Step 1: Design Calculation Complete**\n```\n{calculation_specifications}\n```"})

        # Step 2: 3D Modeling
        # Attempt to initialize the modeling agent (if not already)
        if not self.modeling_agent:
            init_msg = await self.initialize_resources() # Call with await
            if "error" in init_msg.lower() or "not initialized" in init_msg.lower():
                 flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Modeling Skipped**\nFailed to initialize modeling agent: {init_msg}"})
                 modeling_output_for_doc = f"Modeling agent initialization failed: {init_msg}"
            else:
                 flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Modeling in Progress...**\nGenerating model based on specifications.\nSpecifications:\n```\n{calculation_specifications}\n```"})
                 modeling_result = await self._run_modeling_step(calculation_specifications)
                 if "data:image/png;base64" in modeling_result:
                     img_html = f'''<img src="{modeling_result}" alt="generated 3d model" />'''
                     flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Modeling Complete**\n{img_html}"})
                     modeling_output_for_doc = "3D model generated. Please see the preview above."
                 else:
                     flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Modeling Result**\n```\n{modeling_result}\n```"})
                     modeling_output_for_doc = modeling_result # Error message or text response
        else: # If already initialized
            flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Modeling in Progress...**\nGenerating model based on specifications.\nSpecifications:\n```\n{calculation_specifications}\n```"})
            modeling_result = await self._run_modeling_step(calculation_specifications)
            if "data:image/png;base64" in modeling_result:
                img_html = f'''<img src="{modeling_result}" alt="generated 3d model" />'''
                flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Modeling Complete**\n{img_html}"})
                modeling_output_for_doc = "3D model generated. Please see the preview above."
            else:
                flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Modeling Result**\n```\n{modeling_result}\n```"})
                modeling_output_for_doc = modeling_result

        # Step 3: Document Generation
        flow_responses.append({"role": "assistant", "content": "**Step 3: Document Generation in Progress...**"})
        proposal_md = await self._run_documentation_step(user_query, calculation_specifications, modeling_output_for_doc)
        flow_responses.append({"role": "assistant", "content": f"**Step 3: Document Generation Complete**\nProposal document is ready. Please download and review.\n\nSummary:\n{proposal_md[:300]}..."}) # Display only the first 300 characters

        return flow_responses, proposal_md # List of messages for chat display and markdown content

    def chat_interface(self, message: str, history: List[List[str]]):
        """Processing function for Gradio's chat interface."""
        processed_history: List[Dict[str, Any]] = []
        for user_msg, assistant_msg in history:
            if user_msg:
                processed_history.append({"role": "user", "content": user_msg})
            if assistant_msg:
                 processed_history.append({"role": "assistant", "content": assistant_msg})

        # initialize_resources() is mainly responsible for initializing the modeling agent.
        # Here, it's set to be called as needed at the start of the flow.
        # Since _initialize_modeling_agent_and_tools is called within the flow, a pre-call here might not be essential.
        # However, if there's no use case for explicitly pressing an initialize button from the UI, initializing on the first message processing is natural.

        # Add the user's current message to history for display (reflect input)
        # history.append([message, "Processing..."]) # If the UI is updated here, subsequent messages will be split

        # Call _execute_full_flow and get the response
        # processed_history contains past interactions, message contains the current user input
        flow_chat_responses, proposal_md_content = loop.run_until_complete(
            self._execute_full_flow(message, processed_history)
        )

        # Create the final Gradio history
        # User's current message
        updated_gradio_history = history + [[message, None]] # First, add only the user message

        # Add each response from the flow to the history
        current_assistant_response_parts = []
        for resp in flow_chat_responses:
            if resp["role"] == "assistant":
                current_assistant_response_parts.append(resp["content"])

        if updated_gradio_history[-1][1] is None: # If there's no AI response yet for the last user message
            updated_gradio_history[-1][1] = "\n\n".join(current_assistant_response_parts)
        else: # Theoretically should not happen, but just in case
            updated_gradio_history.append([None, "\n\n".join(current_assistant_response_parts)])

        # Process to save proposal.md as a file (for Gradio's File component)
        # In Gradio, the file component is updated by the return value of fn
        # Here, return the filename or a temporary file path
        md_file_path = "proposal.md"
        with open(md_file_path, "w", encoding="utf-8") as f:
            f.write(proposal_md_content)

        return updated_gradio_history, md_file_path # Updated chat history and path to the generated file

app_instance = LangchainMCPApp()

def gradio_app_interface():
    with gr.Blocks(title="Design & Modeling Agent") as demo:
        gr.Markdown("# Design & Modeling Agent")
        gr.Markdown("Performs design calculations, 3D modeling, and document generation based on user requests.")

        chatbot = gr.Chatbot(
            value=[],
            label="Chat History",
            height=600,
            show_copy_button=True,
            avatar_images=("👤", "🤖"), # User, Assistant
            bubble_full_width=False # Adjust message width
        )

        with gr.Row():
            msg_textbox = gr.Textbox(
                label="Your message:",
                placeholder="Enter your requirements for the design...",
                scale=4,
                show_label=False,
                container=False
            )

        proposal_file_output = gr.File(label="Download Proposal (proposal.md)")

        def handle_chat_submit(message, chat_history):
            # Initialization is done as needed within _execute_full_flow
            # app_instance.initialize_resources() # Not necessary to call here

            # To reflect the user message immediately on the UI, temporarily fill the AI response part with None
            # chat_history.append([message, None]) # Including this in the submit return value reflects it immediately, but it gets overwritten by the next update

            updated_history, md_file_path_or_obj = app_instance.chat_interface(message, chat_history)
            return updated_history, "", md_file_path_or_obj # History, clear textbox, file output

        msg_textbox.submit(
            handle_chat_submit,
            [msg_textbox, chatbot],
            [chatbot, msg_textbox, proposal_file_output] # Update chatbot, clear msg_textbox, update proposal_file_output
        )

        clear_btn = gr.Button("Clear Chat & Output")
        def clear_all():
            if os.path.exists("proposal.md"):
                os.remove("proposal.md")
            return [], "", None # Clear chatbot, clear textbox, clear file output
        clear_btn.click(clear_all, None, [chatbot, msg_textbox, proposal_file_output])

    return demo

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"): # Also need to consider OCI GenAI
        print("Warning: API keys (e.g., OPENAI_API_KEY, ANTHROPIC_API_KEY) not found in environment variables.")
        print("Please set them in your .env file or environment for the LLM to work.")

    # Attempt initialization once when the application starts
    # loop.run_until_complete(app_instance._initialize_client_and_agent())
    # Either have Gradio call this automatically on startup, or initialize on the first message

    interface = gradio_app_interface()
    interface.launch(debug=True)
    # Cleanup when the application exits
    # loop.run_until_complete(app_instance.exit_stack.aclose() if app_instance.exit_stack else asyncio.sleep(0))
    # Depends on how Gradio handles exit processing