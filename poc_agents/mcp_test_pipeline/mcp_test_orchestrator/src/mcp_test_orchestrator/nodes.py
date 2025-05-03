import logging
import asyncio
import json
from typing import Dict, Any, List, Optional, cast, Union
import uuid

from pydantic import ValidationError, BaseModel # Added BaseModel for fallback

# Import state definition, models, config, and wrapper
from .state_definition import McpTestState
# Use our local wrapper instead of dynamics_orchestrator
from .a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
from .config import McpTestPipelineConfig
# Import proxy output model AND error details model for validation/creation
try:
    # Adjust path relative to this orchestrator's src if needed, but PYTHONPATH should handle it
    from mcp_tool_proxy_agent.models import McpToolExecOutput, McpErrorDetails
except ImportError:
    # Placeholders if run in isolation
    class McpErrorDetails(BaseModel):
        source: str = "UNKNOWN"
        code: str = "UNKNOWN"
        message: str = "Proxy model missing"
        details: Optional[Dict[str, Any]] = None
        # Add model_dump_json for compatibility if needed by safe_error_to_json
        def model_dump_json(self, *args, **kwargs): import json; return json.dumps(self.dict(*args, **kwargs))


    class McpToolExecOutput(BaseModel): # Inherit from BaseModel for validation methods
        success: bool = False
        mcp_result: Optional[Dict[str, Any]] = None
        error: Optional[McpErrorDetails] = None
        # Add model_validate for compatibility
        @classmethod
        def model_validate(cls, data): return cls.parse_obj(data)
        # Add model_dump for compatibility
        def model_dump(self, *args, **kwargs): return self.dict(*args, **kwargs)


# Import specific result models if needed
from .models import CodeExecutionResult

logger = logging.getLogger(__name__)

# --- Constants for node names ---
START_NODE = "start_mcp_test"
READ_FILE_NODE = "read_code_file_via_proxy"
EXECUTE_CODE_NODE = "execute_python_code_via_proxy"
WRITE_RESULT_NODE = "write_result_file_via_proxy"
ERROR_HANDLER_NODE = "handle_mcp_test_error"

# --- Helper Functions ---

# Helper function to safely get JSON representation of an error object
def safe_error_to_json(error_obj) -> str:
    """Safely convert an error object to JSON string, supporting both Pydantic v1 and v2."""
    if error_obj is None:
        return '"Unknown error"' # Return valid JSON string

    try:
        # Prioritize model_dump_json if available (Pydantic v2 style)
        if hasattr(error_obj, 'model_dump_json') and callable(getattr(error_obj, 'model_dump_json')):
            # Ensure exclude_none is handled correctly
            kwargs = {'exclude_none': True}
            return error_obj.model_dump_json(**kwargs)
        # Fallback to dict() for Pydantic v1 or other objects
        elif hasattr(error_obj, 'dict') and callable(getattr(error_obj, 'dict')):
             # Ensure exclude_none is handled correctly for Pydantic v1's dict()
             kwargs = {'exclude_none': True}
             return json.dumps(error_obj.dict(**kwargs))
        elif isinstance(error_obj, dict):
             # Basic dictionary serialization
             return json.dumps({k: v for k, v in error_obj.items() if v is not None})
        else:
            # Fallback for unexpected types
            fallback_dict = {
                "source": getattr(error_obj, 'source', "UNKNOWN"),
                "code": getattr(error_obj, 'code', "UNKNOWN"),
                "message": str(getattr(error_obj, 'message', str(error_obj))),
                "details": getattr(error_obj, 'details', None)
            }
            return json.dumps({k: v for k, v in fallback_dict.items() if v is not None})
    except Exception as e:
        logger.error(f"Failed to serialize error object to JSON: {e}")
        return json.dumps({"source": "SERIALIZATION_ERROR", "code": "UNKNOWN", "message": "Failed to serialize error details"})


async def _call_proxy(
    a2a_wrapper: A2AClientWrapper,
    proxy_hri: str,
    target_mcp_server_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    project_id: str,
    node_name: str
) -> McpToolExecOutput:
    """Helper function to call the MCP proxy agent and handle basic validation."""
    logger.info(f"NODE: {node_name} (Project: {project_id}) - Calling proxy ({proxy_hri}) for tool '{tool_name}' on target '{target_mcp_server_id}'")
    proxy_input = {
        "target_mcp_server_id": target_mcp_server_id,
        "tool_name": tool_name,
        "arguments": arguments
    }
    try:
        proxy_result_data = await a2a_wrapper.run_a2a_task(proxy_hri, proxy_input)

        # --- SIMPLIFIED VALIDATION ---
        # Directly check the structure and create the output object manually
        # This avoids potential Pydantic recursion issues with nested/generic types here.
        if isinstance(proxy_result_data, dict):
            success = proxy_result_data.get('success', False)
            mcp_result = proxy_result_data.get('mcp_result')
            error_dict = proxy_result_data.get('error')

            error_details: Optional[McpErrorDetails] = None
            if isinstance(error_dict, dict):
                 # Attempt to create McpErrorDetails from the dict
                 try:
                      error_details = McpErrorDetails.model_validate(error_dict)
                 except Exception as val_err:
                      logger.warning(f"Could not validate error details dict: {val_err}. Using raw dict.")
                      # Fallback: create a basic error detail if validation fails
                      error_details = McpErrorDetails(
                           source=error_dict.get("source", "A2A_PROXY"),
                           code=error_dict.get("code", "UNKNOWN_ERROR_STRUCTURE"),
                           message=error_dict.get("message", "Unknown error structure received"),
                           details=error_dict.get("details")
                      )

            # Construct the output object
            validated_output = McpToolExecOutput(
                success=success,
                mcp_result=mcp_result if success else None,
                error=error_details if not success else None
            )
            # Basic check: if success is false, ensure error object exists
            if not validated_output.success and validated_output.error is None:
                 logger.warning("Proxy reported failure but error details are missing. Creating generic error.")
                 validated_output.error = McpErrorDetails(source="A2A_PROXY", code="MISSING_ERROR_DETAILS", message="Proxy reported failure but did not provide error details.")

            return validated_output
        else:
             logger.error(f"NODE: {node_name} - Proxy response was not a dictionary: {type(proxy_result_data)}")
             error_details = McpErrorDetails(source="A2A_PROXY", code="PROXY_RESPONSE_INVALID", message="Proxy response was not a dictionary")
             return McpToolExecOutput(success=False, error=error_details)
        # --- END SIMPLIFIED VALIDATION ---

    except AgentProcessingError as e: # Catch error raised by run_a2a_task on failure
        logger.error(f"NODE: {node_name} - AgentProcessingError calling proxy agent {proxy_hri}: {e}")
        error_details = McpErrorDetails(source="A2A_PROXY", code="PROXY_TASK_FAILED", message=f"Proxy agent task failed: {e}")
        return McpToolExecOutput(success=False, error=error_details)
    except Exception as e:
        logger.exception(f"NODE: {node_name} - Unexpected error calling proxy agent {proxy_hri}: {e}")
        error_details = McpErrorDetails(source="A2A_PROXY", code="PROXY_CALL_UNEXPECTED_ERROR", message=f"Unexpected error calling proxy: {e}")
        return McpToolExecOutput(success=False, error=error_details)


# --- Node Functions ---

async def start_mcp_test(state: McpTestState) -> Dict[str, Any]:
    """Initial node: Logs start, validates essential state components."""
    project_id = state["project_id"]
    config: McpTestPipelineConfig = state.get("pipeline_config") # type: ignore
    a2a_wrapper: A2AClientWrapper = state.get("a2a_wrapper") # type: ignore
    input_path = state.get("input_file_path")
    input_code = state.get("input_python_code")

    if not config or not a2a_wrapper:
        return {"error_message": "Initial state missing config or wrapper."}
    if not input_path and not input_code:
         return {"error_message": "Initial state missing input_file_path or input_python_code."}

    logger.info(f"NODE: {START_NODE} (Project: {project_id}) - Starting MCP test pipeline.")
    logger.info(f"Input File Path: {input_path}")
    logger.info(f"Input Python Code: {'Provided' if input_code else 'Not Provided'}")

    return {"current_step": START_NODE, "error_message": None}

async def read_code_file_via_proxy(state: McpTestState) -> Dict[str, Any]:
    """Node to read Python code from a file using the filesystem MCP server via proxy."""
    if not state.get("input_file_path"):
        logger.info("No input file path provided, skipping file read node.")
        return {"current_step": READ_FILE_NODE, "error_message": None} # Skip if no path

    try:
        config: McpTestPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        file_path = state["input_file_path"]
    except KeyError as e:
        return {"error_message": f"State missing key: {e}"}

    proxy_hri = config.mcp_tool_proxy_agent.hri
    tool_name = "filesystem.readFile" # Standard MCP tool name assumption
    target_server_id = "filesystem" # Matches key in MCP_SERVER_MAP
    arguments = {"path": file_path}

    proxy_output = await _call_proxy(a2a_wrapper, proxy_hri, target_server_id, tool_name, arguments, project_id, READ_FILE_NODE)

    if not proxy_output.success or not proxy_output.mcp_result:
        error_detail = safe_error_to_json(proxy_output.error) # Use helper
        logger.error(f"Failed to read file '{file_path}' via proxy: {error_detail}")
        return {"error_message": f"Failed to read file via proxy: {error_detail}"}

    # Extract content - assumes MCP result format: {"content": [{"type": "text", "text": "..."}]}
    file_content: Optional[str] = None
    try:
        content_list = proxy_output.mcp_result.get("content", [])
        if content_list and isinstance(content_list, list) and len(content_list) > 0:
            first_item = content_list[0]
            if isinstance(first_item, dict) and first_item.get("type") == "text":
                file_content = first_item.get("text")
    except Exception as e:
        logger.error(f"Error parsing readFile result content from proxy: {e}. Result: {proxy_output.mcp_result}")
        return {"error_message": f"Error parsing file content from proxy: {e}"}

    if file_content is None:
        logger.warning(f"Proxy returned success for readFile '{file_path}', but content was missing or invalid format. Result: {proxy_output.mcp_result}")
        # Return error as we cannot proceed without the code
        return {"error_message": f"Proxy succeeded for readFile but content format was unexpected."}

    logger.info(f"Successfully read content from '{file_path}' via proxy (length: {len(file_content)}).")
    return {"read_file_content": file_content, "current_step": READ_FILE_NODE, "error_message": None}

async def execute_python_code_via_proxy(state: McpTestState) -> Dict[str, Any]:
    """Node to execute Python code using the code runner MCP server via proxy."""
    try:
        config: McpTestPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        # Prioritize code read from file, fallback to direct input code
        python_code = state.get("read_file_content") or state.get("input_python_code")
    except KeyError as e:
        return {"error_message": f"State missing key: {e}"}

    if not python_code:
        return {"error_message": "No Python code available to execute (neither direct input nor file content)."}

    proxy_hri = config.mcp_tool_proxy_agent.hri
    tool_name = "code.runPython" # Assumed MCP tool name
    target_server_id = "code" # Matches key in MCP_SERVER_MAP
    arguments = {"code": python_code}

    proxy_output = await _call_proxy(a2a_wrapper, proxy_hri, target_server_id, tool_name, arguments, project_id, EXECUTE_CODE_NODE)

    if not proxy_output.success or not proxy_output.mcp_result:
        error_detail = safe_error_to_json(proxy_output.error) # Use helper
        logger.error(f"Failed to execute Python code via proxy: {error_detail}")
        return {"error_message": f"Failed to execute code via proxy: {error_detail}"}

    # Parse the code execution result - assumes MCP result format:
    # {"content": [{"type": "code_output", "stdout": "...", "stderr": "...", "result": ...}]}
    # Adjust parsing based on the actual code runner MCP server's output schema
    execution_result_data: Optional[Dict[str, Any]] = None
    try:
        content_list = proxy_output.mcp_result.get("content", [])
        if content_list and isinstance(content_list, list) and len(content_list) > 0:
            first_item = content_list[0]
            # Assuming the code runner returns the output directly in the first content item
            if isinstance(first_item, dict):
                 # Check for common keys like stdout/stderr, adjust if needed
                 if "stdout" in first_item or "stderr" in first_item:
                      execution_result_data = first_item
                 else:
                      # Fallback if structure is different, maybe just text?
                      if first_item.get("type") == "text":
                           execution_result_data = {"stdout": first_item.get("text")}


        if execution_result_data:
             # Validate against our Pydantic model
             validated_exec_result = CodeExecutionResult.model_validate(execution_result_data)
             logger.info(f"Successfully executed Python code via proxy. Stdout length: {len(validated_exec_result.stdout or '')}, Stderr length: {len(validated_exec_result.stderr or '')}")
             return {"code_execution_output": validated_exec_result, "current_step": EXECUTE_CODE_NODE, "error_message": None}
        else:
             logger.warning(f"Proxy returned success for runPython, but content format was unexpected or missing stdout/stderr. Result: {proxy_output.mcp_result}")
             # Treat as success but with potentially empty output
             return {"code_execution_output": CodeExecutionResult(), "current_step": EXECUTE_CODE_NODE, "error_message": None}


    except (ValidationError, Exception) as e:
        logger.error(f"Error parsing/validating runPython result content from proxy: {e}. Result: {proxy_output.mcp_result}")
        return {"error_message": f"Error parsing code execution result from proxy: {e}"}


async def handle_mcp_test_error(state: McpTestState) -> Dict[str, Any]:
    """Node to handle pipeline errors."""
    error = state.get("error_message", "Unknown error")
    last_step = state.get("current_step", "Unknown step")
    project_id = state["project_id"]
    logger.error(f"MCP TEST PIPELINE FAILED (Project: {project_id}) at step '{last_step}'. Error: {error}")
    # Return only the error message and step to avoid large state dumps on error
    return {"error_message": f"Pipeline failed at step: {last_step}. Reason: {error}", "current_step": ERROR_HANDLER_NODE}


logger.info("MCP Test pipeline node functions defined.")
