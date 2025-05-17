import asyncio
import os
from typing import List, Dict, Any, Union
from contextlib import AsyncExitStack
import json # Added import

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
        #self.modeling_llm = ChatOpenAI(model="gpt-4.1")


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
                    # "playwright": {
                    #     "command": "npx",
                    #     "args": ["@playwright/mcp@latest"],
                    #     "env": {
                    #     "DISPLAY": ":1" # Set according to your environment
                    #     }
                    # },
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
            # Ensure this is awaited as it's an async function
            init_status = await self._initialize_modeling_agent_and_tools()
            # Check status more reliably
            if "error" in init_status.lower() or "failed" in init_status.lower():
                 # Let the caller handle the error message display
                raise RuntimeError(f"Failed to initialize modeling agent: {init_status}")
            return init_status
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

    async def _extract_modeling_parameters(self, calculation_output: str) -> str:
        """Extracts parameters relevant for 3D modeling from the calculation output."""
        prompt_message = HumanMessage(
            content=f"""The following text contains detailed design specifications.
Please extract ONLY the information essential for 3D modeling, such as dimensions, shape descriptions, key components, and their spatial relationships.
Exclude information like material properties, manufacturing methods, usage instructions, or cost analysis unless they directly define the geometry.
Present the extracted information clearly, ideally in bullet points or a structured list.

Design Specifications:
{calculation_output}

Essential 3D Modeling Parameters:
"""
        )
        try:
            response = await self.calculation_model.ainvoke([prompt_message])
            return response.content
        except Exception as e:
            print(f"Error in modeling parameter extraction step: {e}")
            return f"An error occurred during modeling parameter extraction: {str(e)}\nFalling back to using full calculation output for modeling."

    async def _run_modeling_step(self, specifications: str, doc_name: str = "MyDesignDoc", obj_name:str = "MyExportedObject", screenshot_filename: str = "") -> Dict[str, Union[str, None]]:
        """Step 2: Use the 3D model LLM (agent) to generate a 3D model and export it."""
        # Return a dictionary: {"image_data": base64_string or None, "model_file_path": path_string or None, "error": error_message_string or None}

        if not self.modeling_agent:
            try:
                await self.initialize_resources()
            except RuntimeError as e:
                return {"image_data": None, "model_file_path": None, "error": str(e)}

        # Define a default filename and format, can be made more dynamic
        export_file_name = f"{obj_name}.step"
        export_format = "STEP"

        prompt = f"""
First, create a 3D model based on the following specifications in the document named '{doc_name}'.
Make sure the primary object you create or modify is named '{obj_name}'.
Specifications:
{specifications}

After successfully creating or verifying the object '{obj_name}' in document '{doc_name}',
use the 'export_object_as_file' tool to export the object '{obj_name}' from document '{doc_name}'.
Use the filename '{export_file_name}' and format '{export_format}'.
The final output should include any image of the generated model (data:image/png;base64 format) AND the result from the export tool.
If the export tool returns a JSON with 'file_content_b64', ensure that JSON string is part of your final response.
"""
        try:
            agent_input = {"messages": [HumanMessage(content=prompt)]}
            agent_response_dict = await self.modeling_agent.ainvoke(agent_input)

            agent_response_content = ""
            if isinstance(agent_response_dict, dict) and "messages" in agent_response_dict:
                ai_messages = [msg for msg in agent_response_dict["messages"] if isinstance(msg, AIMessage)]
                if ai_messages:
                    agent_response_content = ai_messages[-1].content
                else: # Should not happen with react agent, but handle defensively
                    agent_response_content = str(agent_response_dict)
            else: # Fallback if response structure is unexpected
                agent_response_content = str(agent_response_dict)


            image_data_b64 = None
            model_file_path = None
            error_message = None # This will hold the primary status/error message for the normal flow
            screenshot_file_path = None # Initialize screenshot_file_path

            # Check for recursion limit message in the agent's textual response
            is_recursion_error_in_agent_text = "Recursion limit" in agent_response_content and "GRAPH_RECURSION_LIMIT" in agent_response_content
            if is_recursion_error_in_agent_text:
                print("DEBUG: Recursion limit message detected in agent's textual response.")

            # Extract image data
            image_match = re.search(r'(data:image/png;base64,[A-Za-z0-9+/=]+)', agent_response_content)
            if image_match:
                image_data_b64 = image_match.group(1)
                # Save the screenshot if image_data_b64 is found and screenshot_filename is provided
                if image_data_b64 and screenshot_filename:
                    try:
                        # Ensure the 'model_exports' directory exists
                        exports_dir = "model_exports"
                        if not os.path.exists(exports_dir):
                            os.makedirs(exports_dir)
                        
                        screenshot_file_path = os.path.join(exports_dir, screenshot_filename)
                        # Remove the "data:image/png;base64," prefix before decoding
                        img_data_to_decode = image_data_b64.split(',')[1]
                        with open(screenshot_file_path, "wb") as f:
                            f.write(base64.b64decode(img_data_to_decode))
                        print(f"Screenshot saved to: {screenshot_file_path}")
                    except Exception as e:
                        print(f"Error saving screenshot: {e}")
                        # Optionally, set an error message or handle this error
                        # For now, we just print and continue, screenshot_file_path will remain None or its previous value

            # Extract exported file data
            # The export tool returns a JSON string as TextContent.
            # The agent's response should contain this JSON string.
            export_data_match = re.search(r'\{\s*"file_name":\s*".*?",\s*"file_format":\s*".*?",\s*"file_content_b64":\s*".*?",\s*"message":\s*".*?"\s*\}', agent_response_content, re.DOTALL)

            if export_data_match:
                try:
                    export_json_str = export_data_match.group(0)
                    export_data = json.loads(export_json_str)
                    if export_data.get("file_content_b64"):
                        file_content_b64 = export_data["file_content_b64"]
                        # Save the decoded file content
                        # Ensure the 'exports' directory exists
                        exports_dir = "model_exports"
                        if not os.path.exists(exports_dir):
                            os.makedirs(exports_dir)
                        
                        # Use the filename from the export tool's response
                        exported_filename = export_data.get("file_name", export_file_name) # Fallback to original name
                        model_file_path = os.path.join(exports_dir, exported_filename)
                        
                        with open(model_file_path, "wb") as f:
                            f.write(base64.b64decode(file_content_b64))
                        print(f"Model exported and saved to: {model_file_path}")
                    elif export_data.get("error"):
                        # This error_message might be overridden if is_recursion_error_in_agent_text is true
                        error_message = f"Export failed: {export_data.get('error')}"
                        print(error_message)
                    else:
                        # This error_message might be overridden if is_recursion_error_in_agent_text is true
                        error_message = "Export tool ran, but no file content or error found in its JSON response."
                        print(error_message)
                except json.JSONDecodeError as e:
                    # This error_message might be overridden if is_recursion_error_in_agent_text is true
                    error_message = f"Failed to parse export data JSON: {str(e)}. Raw: {export_json_str}"
                    print(error_message)
                except Exception as e:
                    # This error_message might be overridden if is_recursion_error_in_agent_text is true
                    error_message = f"Error processing exported file data: {str(e)}"
                    print(error_message)
            # No explicit "else" for export_data_match here, message construction below handles cases

            # Final message construction
            if is_recursion_error_in_agent_text:
                current_status_message = "Step 2 finished. Model generation may be partially complete due to recursion limit in agent response."
                if screenshot_file_path:
                    current_status_message += f" Screenshot saved as '{os.path.basename(screenshot_file_path)}'."
                elif image_data_b64:
                    current_status_message += " A model preview was generated."
                else:
                    current_status_message += " No screenshot or preview was generated."
                error_message = current_status_message # Override any previous error_message from export tool if recursion was detected
            elif not error_message and not model_file_path and not image_data_b64:
                # If no specific error from export, no model, and no image, then set a generic "no output" message
                error_message = "Modeling agent did not return image or export data."
            # If error_message was set due to an export issue (and no recursion error in text), it will be preserved.

            return {"image_data": image_data_b64, "model_file_path": model_file_path, "error": error_message, "screenshot_file_path": screenshot_file_path}

        except Exception as e:
            print(f"Error in modeling step: {e}")
            # Initialize error result, including a key for a potential fallback screenshot
            error_result = {"image_data": None, "model_file_path": None, "error": f"An error occurred during 3D modeling: {str(e)}", "screenshot_file_path": None, "fallback_screenshot_path": None}
            
            is_recursion_exception = "Recursion limit" in str(e) and "GRAPH_RECURSION_LIMIT" in str(e)

            if is_recursion_exception:
                error_result["error"] = "Step 2 finished. Model generation may be partially complete due to recursion limit exception."
            # else, the default error message from initialization is used for other exceptions.

            # Attempt to take a fallback screenshot if mcp_client is available
            if self.mcp_client:
                try:
                    print("Attempting to take a fallback screenshot due to modeling error...")
                    
                    # Try to get FreeCAD status using execute_code
                    execute_code_tool = None
                    # get_view_tool = None # Keep this for later # Not used in current fallback
                    available_tools = self.mcp_client.get_tools()
                    for tool_obj in available_tools:
                        if tool_obj.name == "execute_code":
                            execute_code_tool = tool_obj
                            break # Found execute_code, no need to search for get_view for this path
                    
                    if execute_code_tool:
                        print("Attempting fallback screenshot directly via execute_code...")
                        # Code inspired by FreeCADConnection.get_active_screenshot and export_object
                        screenshot_code = '''
import FreeCAD
import FreeCADGui
import base64
import os
import tempfile

img_b64 = None
error_msg = None
try:
    if FreeCAD.Gui.ActiveDocument and FreeCAD.Gui.ActiveDocument.ActiveView:
        view = FreeCAD.Gui.ActiveDocument.ActiveView
        view_type = type(view).__name__
        unsupported_views = ['SpreadsheetGui::SheetView', 'DrawingGui::DrawingView', 'TechDrawGui::MDIViewPage']
        
        if view_type in unsupported_views or not hasattr(view, 'saveImage'):
            error_msg = f"Current view ({view_type}) does not support screenshots."
        else:
            # Create a temporary file to save the image
            fd, temp_image_path = tempfile.mkstemp(suffix='.png', prefix='freecad_ss_')
            os.close(fd) # We only need the path
            try:
                view.saveImage(temp_image_path, 1920, 1080, 'White') # Example resolution and background
                if os.path.exists(temp_image_path) and os.path.getsize(temp_image_path) > 0:
                    with open(temp_image_path, 'rb') as f:
                        img_b64 = base64.b64encode(f.read()).decode('utf-8')
                else:
                    error_msg = "saveImage executed but file not created or empty."
            except Exception as e_save:
                error_msg = f"Error during view.saveImage: {str(e_save)}"
            finally:
                if os.path.exists(temp_image_path):
                    try:
                        os.remove(temp_image_path)
                    except Exception as e_clean:
                        print(f"Warning: Failed to remove temp_image_path {temp_image_path}: {str(e_clean)}") # Print on FreeCAD side
    elif not FreeCAD.ActiveDocument:
        error_msg = "No active document in FreeCAD to take screenshot from."
    else: # ActiveDocument exists, but no ActiveView
        error_msg = "No active view in FreeCADGui to take screenshot from."
except Exception as e_outer:
    error_msg = f"Outer error during screenshot script: {str(e_outer)}"

if img_b64:
    print(f"data:image/png;base64,{img_b64}") # Output base64 string directly
else:
    print(f"Error: {{error_msg}}") # Output error message
'''
                        try:
                            screenshot_response_list = await execute_code_tool.ainvoke({"code": screenshot_code})
                            fallback_image_data_b64 = None
                            response_text = ""
                            if isinstance(screenshot_response_list, list) and screenshot_response_list:
                                # Expecting list[TextContent]
                                content_item = screenshot_response_list[0]
                                if hasattr(content_item, 'text'):
                                    response_text = content_item.text
                                else:
                                    response_text = str(screenshot_response_list)
                            else:
                                # Sometimes returned as plain string
                                response_text = str(screenshot_response_list)
                            print(f"Response from execute_code for screenshot: {response_text}")

                            # Extract data:image/png;base64 string if present
                            match_b64 = re.search(r'data:image/png;base64,[A-Za-z0-9+/=]+', response_text)
                            if match_b64:
                                fallback_image_data_b64 = match_b64.group(0)
                            elif response_text.strip().startswith("Error:"):
                                print(f"execute_code for screenshot reported error: {response_text.strip()}")
                            else:
                                print("execute_code for screenshot did not include base64 image data.")

                            # Proceed with saving if fallback_image_data_b64 was obtained
                            if fallback_image_data_b64:
                                exports_dir = "model_exports"
                                if not os.path.exists(exports_dir):
                                    os.makedirs(exports_dir)
                                
                                import datetime
                                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                fallback_filename = f"fallback_direct_ss_{timestamp}.png"
                                fallback_save_path = os.path.join(exports_dir, fallback_filename)
                                
                                img_data_to_decode = fallback_image_data_b64.split(',')[1] # Remove data:image/png;base64, prefix
                                
                                with open(fallback_save_path, "wb") as f:
                                    f.write(base64.b64decode(img_data_to_decode))
                                print(f"Fallback screenshot directly saved to: {fallback_save_path}")
                                error_result["fallback_screenshot_path"] = fallback_save_path

                        except Exception as exec_ss_exc:
                            print(f"Exception during execute_code for direct screenshot: {exec_ss_exc}")
                        # else: # execute_code_tool not found, this was checked earlier
                            # print("execute_code tool not found, cannot attempt direct screenshot.")
                        
                except Exception as fallback_exc:
                    print(f"Outer exception in fallback screenshot block: {fallback_exc}")
                # else: # mcp_client not available, already handled by initial error_result["error"] message not being appended to.
                    # print("Fallback screenshot: mcp_client not available.")
            
            # Append fallback screenshot info to the error message if one was saved
            if error_result.get("fallback_screenshot_path"):
                error_result["error"] += f" A fallback screenshot '{os.path.basename(error_result['fallback_screenshot_path'])}' was captured."
            elif is_recursion_exception: # If it was a recursion exception and no fallback was captured
                error_result["error"] += " No fallback screenshot was captured."
                
            return error_result

    async def _run_documentation_step(self, user_query: str, calculation_output: str, modeling_step_output: Dict[str, Union[str, None]]) -> str:
        """Step 3: Use the final output LLM to generate documentation."""
        
        model_summary_for_doc = "3D model was not generated or encountered an error."
        if modeling_step_output:
            if modeling_step_output.get("model_file_path"):
                model_file_name = os.path.basename(modeling_step_output["model_file_path"])
                model_summary_for_doc = f"3D model generated and exported as '{model_file_name}'. "
                if modeling_step_output.get("image_data"):
                    model_summary_for_doc += "A preview is available in the chat."
                else:
                    model_summary_for_doc += "No preview image was generated."
            elif modeling_step_output.get("image_data"): # Only image, no file
                 model_summary_for_doc = "3D model preview generated. File export may have failed or was not performed."
            elif modeling_step_output.get("error"):
                model_summary_for_doc = f"3D modeling/export failed: {modeling_step_output['error']}"

            if modeling_step_output and modeling_step_output.get("screenshot_file_path"):
                screenshot_basename = os.path.basename(modeling_step_output["screenshot_file_path"])
                model_summary_for_doc += f" A screenshot '{screenshot_basename}' was also saved."

            if modeling_step_output and modeling_step_output.get("fallback_screenshot_path"):
                fallback_basename = os.path.basename(modeling_step_output["fallback_screenshot_path"])
                model_summary_for_doc += f" Due to a modeling error, a fallback screenshot '{fallback_basename}' was also captured and saved."


        prompt = f"""Based on the following information, create a design proposal document for the user.
Assume it will be saved in Markdown format as 'proposal.md'.

Original user request:
{user_query}

Design calculation results and specifications:
{calculation_output}

Summary of 3D modeling and export results:
{model_summary_for_doc}

The document should include the following elements:
1.  Summary of user request
2.  Proposed specifications (mechanical specs, etc.)
3.  Design points and rationale
4.  Information about the 3D model (e.g., filename if exported, or status if not)
5.  Next steps or recommendations (if any)
"""
        try:
            response = await self.documentation_model.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            print(f"Error in documentation step: {e}")
            return f"An error occurred during document generation: {str(e)}"

    async def _execute_post_calculation(self, user_query: str, history: List[Dict[str, str]], calculation_specifications: str):
        """Executes the remaining flow (parameter extraction, modeling, documentation) after calculation is done.
        Returns flow_responses, proposal_md, model_file_path, screenshot_file_path
        """
        # Step 1.5: Extract modeling parameters
        modeling_parameters = await self._extract_modeling_parameters(calculation_specifications)

        # Initialize containers for later messages and files (available regardless of extraction success)
        flow_responses: List[Dict[str, str]] = []
        modeling_result_data = None
        model_file_for_gradio = None
        screenshot_file_for_gradio = None
        fallback_screenshot_file_for_gradio = None

        if "An error occurred" in modeling_parameters:
            parameters_for_modeling_step = calculation_specifications
            print(f"Modeling parameter extraction failed. Using full calculation specifications. Error: {modeling_parameters}")
        else:
            parameters_for_modeling_step = modeling_parameters
            print("""Successfully extracted modeling parameters (post-calculation step).""")

        try:
            await self.initialize_resources()
            doc_name_for_modeling = "DesignDocument"
            object_name_for_modeling = "MainAssembly"
            screenshot_filename = f"{object_name_for_modeling}_preview.png"

            modeling_result_data = await self._run_modeling_step(
                parameters_for_modeling_step,
                doc_name=doc_name_for_modeling,
                obj_name=object_name_for_modeling,
                screenshot_filename=screenshot_filename
            )

            if modeling_result_data.get("error"):
                flow_responses.append({
                    "role": "assistant",
                    "content": f"**Step 2: 3D Modeling & Export Error**\n```\n{modeling_result_data['error']}\n```"
                })
            else:
                if modeling_result_data.get("image_data") and not modeling_result_data.get("screenshot_file_path"):
                    img_html = f'<img src="{modeling_result_data["image_data"]}" alt="generated 3d model" />'
                    flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Model Preview (not saved as file)**\n{img_html}"})

                if modeling_result_data.get("model_file_path"):
                    model_file_for_gradio = modeling_result_data["model_file_path"]
                    flow_responses.append({"role": "assistant", "content": f"**Step 2: Model Export Successful**\nModel exported to: {os.path.basename(model_file_for_gradio)}."})

                if modeling_result_data.get("screenshot_file_path"):
                    screenshot_file_for_gradio = modeling_result_data["screenshot_file_path"]
                    img_html_from_file = f'<img src="file={screenshot_file_for_gradio}" alt="generated 3d model screenshot" />'
                    flow_responses.append({"role": "assistant", "content": f"**Step 2: Screenshot Saved**\nScreenshot saved as: {os.path.basename(screenshot_file_for_gradio)}."})

                if modeling_result_data.get("fallback_screenshot_path"):
                    fallback_screenshot_file_for_gradio = modeling_result_data["fallback_screenshot_path"]
                    img_html_fallback = f'<img src="file={fallback_screenshot_file_for_gradio}" alt="Fallback screenshot due to error" />'
                    flow_responses.append({"role": "assistant", "content": f"**Step 2: Fallback Screenshot (due to modeling error)**\n{img_html_fallback}"})
                    if not screenshot_file_for_gradio:
                        screenshot_file_for_gradio = fallback_screenshot_file_for_gradio

                if not modeling_result_data.get("image_data") and not modeling_result_data.get("model_file_path") and not modeling_result_data.get("screenshot_file_path") and not modeling_result_data.get("fallback_screenshot_path"):
                    flow_responses.append({"role": "assistant", "content": "**Step 2: 3D Modeling & Export Result**\nNo specific output or error reported by the modeling step."})
        except RuntimeError as e:
            flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Modeling & Export Skipped**\nFailed to initialize modeling agent: {e}"})
            modeling_result_data = {"error": str(e)}
        except Exception as e:
            flow_responses.append({"role": "assistant", "content": f"**Step 2: 3D Modeling & Export Failed**\nUnexpected error: {e}"})
            modeling_result_data = {"error": str(e)}

        # Step 3: Document generation
        flow_responses.append({"role": "assistant", "content": "**Step 3: Document Generation in Progress...**"})
        proposal_md = await self._run_documentation_step(user_query, calculation_specifications, modeling_result_data)
        flow_responses.append({"role": "assistant", "content": f"**Step 3: Document Generation Complete**\nProposal document is ready."})

        return flow_responses, proposal_md, model_file_for_gradio, screenshot_file_for_gradio

    def chat_interface(self, message: str, history: List[Dict[str, str]]):
        """Processing function for Gradio's chat interface.
           When type="messages", history is List[Dict[str, str]] from Gradio.
        """
        # The `history` parameter from Gradio (with type="messages") is already
        # a list of dictionaries, e.g., [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        # This format is suitable for direct use in _execute_full_flow if its internal logic handles it,
        # which it does by converting to HumanMessage/AIMessage.

        # Call _execute_full_flow and get the response
        flow_chat_responses, proposal_md_content, model_file_path_for_ui, screenshot_file_path_for_ui = loop.run_until_complete(
            self._execute_full_flow(message, history) # Pass Gradio's history directly
        )

        # Create the final Gradio history for UI update
        # Start with the existing history (which is List[Dict[str, str]])
        updated_gradio_history = list(history) # Make a copy
        
        # Add the user's current message
        updated_gradio_history.append({"role": "user", "content": message})
        
        # Add all new assistant messages from the flow
        # flow_chat_responses is already a List[Dict[str, str]]
        updated_gradio_history.extend(flow_chat_responses)

        # Process to save proposal.md as a file
        md_file_path = "proposal.md"
        with open(md_file_path, "w", encoding="utf-8") as f:
            f.write(proposal_md_content)

        return updated_gradio_history, md_file_path, model_file_path_for_ui, screenshot_file_path_for_ui # Added screenshot path

    async def _execute_full_flow(self, *args, **kwargs):
        """Deprecated: Use new streaming-based flow with _execute_post_calculation."""
        raise NotImplementedError("_execute_full_flow is deprecated. Use _execute_post_calculation instead.")

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
            type="messages"  # Added to address UserWarning
        )

        with gr.Row():
            msg_textbox = gr.Textbox(
                label="Your message:",
                placeholder="Enter your requirements for the design...",
                scale=4,
                show_label=False,
                container=False
            )

        def handle_chat_submit(message, chat_history):
            """Handles chat submission with streamed updates so that Step1 result appears before Step2 processing."""
            # Step 1: Design calculation (synchronous wrapper)
            calculation_specifications = loop.run_until_complete(
                app_instance._run_calculation_step(message, chat_history)
            )

            # Build initial history to show Step1 result
            step1_message = {
                "role": "assistant",
                "content": f"**Step 1: Design Calculation Complete**\n```\n{calculation_specifications}\n```"
            }
            updated_history = list(chat_history) + [
                {"role": "user", "content": message},
                step1_message,
            ]

            # First yield: immediately show Step1 result, no files yet
            yield updated_history, "" # Removed proposal and screenshot file output

            # Step2 progress messageを追加してすぐに表示
            step2_progress_msg = {
                "role": "assistant",
                "content": "**Step 2: 3D Modeling & Export in Progress...**\nCreating 3D model...."
            }
            history_step2 = updated_history + [step2_progress_msg]
            yield history_step2, "" # Removed proposal and screenshot file output

            # Step 2以降を実行
            flow_responses, proposal_md_content, model_file_path, screenshot_file_path_or_obj = loop.run_until_complete(
                app_instance._execute_post_calculation(message, chat_history, calculation_specifications)
            )

            current_final_history = history_step2 + flow_responses

            # proposal.md を保存
            md_file_path = "proposal.md"
            with open(md_file_path, "w", encoding="utf-8") as f:
                f.write(proposal_md_content)
            current_final_history.append({
                "role": "assistant",
                "content": f"Saved proposal file (`{os.path.basename(md_file_path)}`)."
            })

            if model_file_path:
                current_final_history.append({
                    "role": "assistant",
                    "content": f"Saved 3D model file (`{os.path.basename(model_file_path)}`)."
                })

            if screenshot_file_path_or_obj:
                current_final_history.append({
                    "role": "assistant",
                    "content": f"Saved screenshot (`{os.path.basename(screenshot_file_path_or_obj)}`)."
                })

            # Final yield: 完了後に全てのファイルを返す
            yield current_final_history, "" # Removed proposal and screenshot file output

        msg_textbox.submit(
            handle_chat_submit,
            [msg_textbox, chatbot],
            [chatbot, msg_textbox] # Removed proposal_file_output, screenshot_file_output
        )

        clear_btn = gr.Button("Clear Chat & Output")
        def clear_all():
            if os.path.exists("proposal.md"):
                os.remove("proposal.md")
            # Clean up any exported models and screenshots in the 'model_exports' directory
            exports_dir = "model_exports"
            if os.path.exists(exports_dir):
                for f_name in os.listdir(exports_dir):
                    file_path = os.path.join(exports_dir, f_name)
                    if f_name.endswith((".step", ".stl", ".iges", ".brep", ".png")): # Added .png for screenshots
                        try:
                            os.remove(file_path)
                            print(f"Removed exported file: {file_path}")
                        except Exception as e:
                            print(f"Error removing file {file_path}: {e}")

            return [], "" # Clear chatbot, clear textbox (removed proposal and screenshot file outputs)
        clear_btn.click(clear_all, None, [chatbot, msg_textbox]) # Removed proposal_file_output, screenshot_file_output

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
