import logging
import asyncio
import json
import os
import datetime
from typing import Dict, Any, Union, Optional, List, AsyncGenerator
import uuid

import httpx
from fastapi import BackgroundTasks
from pydantic import ValidationError

# Set up logger first before any usage
logger = logging.getLogger(__name__)

# Import base class and SDK components
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import TaskState as SdkTaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Import models from this agent's models.py
from .models import McpToolExecInput, McpToolExecOutput, McpErrorDetails

# --- Direct Import of Core Models ---
from agentvault.models import (
    Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent,
    TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent
)

# --- TaskStateEnum assignment ---
TaskStateEnum = TaskState
AGENT_ID = "local-poc/mcp-tool-proxy"  # Matches agent card

# --- MCP Configuration ---
MCP_SERVER_MAP_JSON = os.environ.get("MCP_SERVER_MAP", "{}")
MCP_CALL_TIMEOUT = float(os.environ.get("MCP_CALL_TIMEOUT", 60.0))
MCP_SERVER_URLS: Dict[str, str] = {}
try:
    MCP_SERVER_URLS = json.loads(MCP_SERVER_MAP_JSON)
    if not isinstance(MCP_SERVER_URLS, dict):
        logger.error(f"MCP_SERVER_MAP is not a valid JSON dictionary: {MCP_SERVER_MAP_JSON}")
        MCP_SERVER_URLS = {}
    else:
        logger.info(f"Loaded MCP Server Map: {MCP_SERVER_URLS}")
except json.JSONDecodeError:
    logger.error(f"Failed to parse MCP_SERVER_MAP JSON: {MCP_SERVER_MAP_JSON}")
    MCP_SERVER_URLS = {}

# --- Helper function for SSE Formatting ---
def _agent_format_sse_event_bytes(event: A2AEvent) -> Optional[bytes]:
    event_type: Optional[str] = None
    if isinstance(event, TaskStatusUpdateEvent): event_type = "task_status"
    elif isinstance(event, TaskMessageEvent): event_type = "task_message"
    elif isinstance(event, TaskArtifactUpdateEvent): event_type = "task_artifact"
    if event_type is None: return None
    try:
        # Use model_dump_json if available (Pydantic v2), fallback for safety
        json_data = event.model_dump_json(by_alias=True) if hasattr(event, 'model_dump_json') else json.dumps(event)
        sse_message = f"event: {event_type}\ndata: {json_data}\n\n"
        return sse_message.encode("utf-8")
    except Exception as e: logger.error(f"Failed to format SSE event: {e}"); return None
# --- End Helper ---


class MCPToolProxyAgent(BaseA2AAgent):
    """Agent to proxy A2A requests to underlying MCP tool servers for SecOps pipeline."""
    def __init__(self):
        super().__init__(agent_metadata={"name": "SecOps MCP Tool Proxy Agent"})
        self.http_client = httpx.AsyncClient(timeout=MCP_CALL_TIMEOUT)
        self.task_store: Optional[Any] = None
        self.logger = logger
        self.mcp_server_map = MCP_SERVER_URLS
        if not self.mcp_server_map:
            logger.warning("MCP_SERVER_MAP is empty or invalid. Proxy will not be able to route requests.")
        logger.info(f"SecOps MCP Tool Proxy Agent initialized. Map: {self.mcp_server_map}")

    def _get_mcp_server_url(self, target_id_or_tool_name: str) -> Optional[str]:
        """
        Finds the base URL for a given target server ID or tool name prefix from the map.
        Matches exact target_id first, then tries matching prefixes.
        """
        # 1. Exact match for target_mcp_server_id
        url = self.mcp_server_map.get(target_id_or_tool_name)
        if url:
            self.logger.debug(f"Found exact match for target_id '{target_id_or_tool_name}' -> URL: {url}")
            return url

        # 2. Prefix match based on tool_name (e.g., "ip" for "ip.report")
        if '.' in target_id_or_tool_name:
            prefix = target_id_or_tool_name.split('.')[0]  # Get the prefix before the dot
            url = self.mcp_server_map.get(prefix)
            if url:
                self.logger.debug(f"Found prefix match for tool '{target_id_or_tool_name}' using prefix '{prefix}' -> URL: {url}")
                return url

        self.logger.warning(f"Could not find MCP server URL mapping for target/tool: '{target_id_or_tool_name}'")
        return None

    async def _call_mcp_server(self, mcp_base_url: str, tool_name: str, arguments: Dict[str, Any]) -> McpToolExecOutput:
        """
        Makes the actual HTTP call to the MCP server's /rpc endpoint.
        Uses the tool_name as the JSON-RPC method.
        First tries POST (standard for JSON-RPC), then falls back to GET if needed.
        """
        output = McpToolExecOutput(success=False, mcp_result=None, error=None)
        request_id = f"mcp-req-{uuid.uuid4().hex[:8]}"

        mcp_request_payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": tool_name,
            "params": arguments
        }

        # Append /rpc endpoint to base URL
        target_url = f"{mcp_base_url.rstrip('/')}/rpc"
        logger.debug(f"Determined target RPC endpoint: {target_url}")

        try:
            # First attempt with POST (standard for JSON-RPC)
            self.logger.info(f"Proxying MCP call to {target_url} for tool '{tool_name}' using POST (Req ID: {request_id})")
            self.logger.debug(f"MCP Request Payload: {mcp_request_payload}")

            try:
                response = await self.http_client.post(
                    target_url,
                    json=mcp_request_payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"}
                )
                
                # If we get a 405 Method Not Allowed, the server might expect GET
                if response.status_code == 405:
                    self.logger.warning(f"POST method not allowed for {target_url}, falling back to GET")
                    
                    # For GET, we need to convert params to query string
                    # This is a simplified approach - for complex nested params, proper conversion needed
                    import urllib.parse
                    query_params = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": tool_name
                    }
                    
                    # Add arguments as top-level query params
                    for key, value in arguments.items():
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            query_params[key] = value
                        else:
                            # Convert complex values to JSON string
                            query_params[key] = json.dumps(value)
                    
                    self.logger.info(f"Retrying with GET request to {target_url}")
                    self.logger.debug(f"GET query params: {query_params}")
                    
                    response = await self.http_client.get(
                        target_url,
                        params=query_params,
                        headers={"Accept": "application/json"}
                    )
            except httpx.RequestError as req_err:
                # If POST fails with connection error, try GET as fallback
                self.logger.warning(f"POST request failed for {target_url}: {req_err}, trying GET")
                
                # Same GET approach as above
                import urllib.parse
                query_params = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": tool_name
                }
                
                for key, value in arguments.items():
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        query_params[key] = value
                    else:
                        query_params[key] = json.dumps(value)
                
                self.logger.info(f"Trying GET request to {target_url}")
                self.logger.debug(f"GET query params: {query_params}")
                
                response = await self.http_client.get(
                    target_url,
                    params=query_params,
                    headers={"Accept": "application/json"}
                )

            self.logger.debug(f"MCP Server Response Status: {response.status_code}")

            try:
                # Handle potential non-JSON responses gracefully, especially 404s
                if response.status_code == 404:
                    self.logger.error(f"MCP server returned 404 Not Found for {target_url}. Body: {response.text[:500]}")
                    output.error = McpErrorDetails(source="MCP_PROTOCOL", code="-32601", message=f"Method not found (HTTP 404 at {target_url})", details={"http_status": response.status_code, "response_body": response.text[:500]})
                    return output

                mcp_response_data = response.json()
                self.logger.debug(f"MCP Response Body: {mcp_response_data}")

            except json.JSONDecodeError as json_err:
                self.logger.error(f"Failed to decode JSON response from MCP server {target_url}: {json_err}. Status: {response.status_code}. Body: {response.text[:500]}")
                output.error = McpErrorDetails(source="A2A_PROXY", code="MCP_INVALID_RESPONSE", message=f"Invalid JSON from MCP server: {json_err}", details={"http_status": response.status_code, "response_body": response.text[:500]})
                return output

            if not isinstance(mcp_response_data, dict):
                self.logger.error(f"MCP response from {target_url} is not a dictionary: {mcp_response_data}")
                output.error = McpErrorDetails(source="A2A_PROXY", code="MCP_INVALID_RESPONSE", message="MCP response was not a JSON object", details={"http_status": response.status_code, "response_body": str(mcp_response_data)[:500]})
                return output

            # Check for JSON-RPC level error (Protocol Error)
            if "error" in mcp_response_data:
                mcp_error_obj = mcp_response_data["error"]
                self.logger.warning(f"MCP server {target_url} returned protocol error: {mcp_error_obj}")
                output.error = McpErrorDetails(
                    source="MCP_PROTOCOL",
                    code=str(mcp_error_obj.get("code", "MCP_UNKNOWN_PROTOCOL_ERROR")),
                    message=str(mcp_error_obj.get("message", "Unknown MCP protocol error")),
                    details={"mcp_protocol_error_data": mcp_error_obj.get("data")}
                )
                return output

            # Check for JSON-RPC success result
            elif "result" in mcp_response_data:
                mcp_result_obj = mcp_response_data["result"]
                if not isinstance(mcp_result_obj, dict):
                    self.logger.error(f"MCP success response 'result' field is not a dictionary: {mcp_result_obj}")
                    output.error = McpErrorDetails(source="A2A_PROXY", code="MCP_INVALID_RESULT", message="MCP success result was not a JSON object", details={"http_status": response.status_code, "mcp_result_type": type(mcp_result_obj).__name__})
                    return output

                # Check for Tool Execution Error (isError: true)
                if mcp_result_obj.get("isError") is True:
                    self.logger.warning(f"MCP server {target_url} reported tool execution error for '{tool_name}': {mcp_result_obj}")
                    output.error = McpErrorDetails(
                        source="MCP_TOOL",
                        code="TOOL_EXECUTION_FAILED",
                        message=f"Execution failed for tool '{tool_name}'",
                        details={"mcp_tool_error_content": mcp_result_obj.get("content")}
                    )
                    return output
                else:
                    # Successful Tool Execution
                    self.logger.info(f"MCP tool '{tool_name}' executed successfully by {target_url}.")
                    output.success = True
                    # Ensure mcp_result contains at least 'content' if present
                    if "content" not in mcp_result_obj:
                        logger.warning(f"MCP success result for tool '{tool_name}' is missing 'content' field. Result: {mcp_result_obj}")
                        # Still treat as success, but result might be incomplete
                        output.mcp_result = mcp_result_obj
                    else:
                        output.mcp_result = mcp_result_obj  # Return the whole result object

                    output.error = None
                    return output
            else:
                # Invalid JSON-RPC response (missing error and result)
                self.logger.error(f"Invalid JSON-RPC response from MCP server {target_url}: Missing 'result' or 'error'. Body: {mcp_response_data}")
                output.error = McpErrorDetails(source="A2A_PROXY", code="MCP_INVALID_RESPONSE", message="Invalid JSON-RPC response from MCP server", details={"http_status": response.status_code, "response_body": mcp_response_data})
                return output

        except httpx.TimeoutException as timeout_err:
            self.logger.error(f"Timeout calling MCP server {target_url}: {timeout_err}")
            output.error = McpErrorDetails(source="A2A_PROXY", code="MCP_TIMEOUT", message=f"Timeout connecting to MCP server {target_url}")
            return output
        except httpx.RequestError as req_err:
            self.logger.error(f"Network error calling MCP server {target_url}: {req_err}")
            output.error = McpErrorDetails(source="A2A_PROXY", code="MCP_CONNECTION_ERROR", message=f"Network error connecting to MCP server {target_url}: {req_err}")
            return output
        except Exception as e:
            self.logger.exception(f"Unexpected error calling MCP server {target_url} for tool '{tool_name}': {e}")
            output.error = McpErrorDetails(source="A2A_PROXY", code="PROXY_INTERNAL_ERROR", message=f"Unexpected proxy error: {e}")
            return output

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: Optional[BackgroundTasks] = None) -> str:
        if task_id:
            raise AgentProcessingError(f"MCP proxy agent does not support continuing task {task_id}")
            
        new_task_id = f"mcp-proxy-{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Task {new_task_id}: Received MCP tool execution request.")
        
        if not self.task_store:
            raise ConfigurationError("Task store not initialized.")
            
        await self.task_store.create_task(new_task_id)
        input_content = None
        
        if message.parts:
            for part in message.parts:
                if isinstance(part, DataPart):
                    input_content = part.content
                    break
                    
        if not isinstance(input_content, dict):
            await self.task_store.update_task_state(new_task_id, TaskStateEnum.FAILED, "Invalid input: Expected DataPart dict.")
            raise AgentProcessingError("Invalid input: Expected DataPart dict.")

        await asyncio.sleep(0.5)

        self.logger.info(f"Task {new_task_id}: Scheduling process_task.")
        asyncio.create_task(self.process_task(new_task_id, input_content))
        return new_task_id

    async def process_task(self, task_id: str, content: Dict[str, Any]):
        if not self.task_store:
            self.logger.error(f"Task {task_id}: Task store missing.")
            return

        await self.task_store.update_task_state(task_id, TaskStateEnum.WORKING)
        self.logger.info(f"Task {task_id}: Background processing started for MCP proxy.")
        final_state = TaskStateEnum.FAILED
        error_message = "Failed MCP proxy execution."
        output_data: Optional[McpToolExecOutput] = None

        try:
            # 1. Validate A2A Input
            try:
                input_data = McpToolExecInput.model_validate(content)
                self.logger.info(f"Task {task_id}: Validated A2A input for tool '{input_data.tool_name}' targeting '{input_data.target_mcp_server_id}'.")
            except ValidationError as val_err:
                raise AgentProcessingError(f"Invalid A2A input for MCP proxy: {val_err}")

            # 2. Find Target MCP Server URL
            # Use target_mcp_server_id first, fallback to tool_name prefix
            target_url = self._get_mcp_server_url(input_data.target_mcp_server_id) or self._get_mcp_server_url(input_data.tool_name)
            if not target_url:
                raise ConfigurationError(f"No MCP server URL configured for target ID '{input_data.target_mcp_server_id}' or tool prefix '{input_data.tool_name.split('.')[0]}' in MCP_SERVER_MAP.")

            # 3. Call MCP Server
            # Pass the actual tool name and arguments
            output_data = await self._call_mcp_server(target_url, input_data.tool_name, input_data.arguments)

            # 4. Determine Final State based on Proxy Call Outcome
            if output_data.success:
                final_state = TaskStateEnum.COMPLETED
                error_message = None
                self.logger.info(f"Task {task_id}: MCP proxy call successful for tool '{input_data.tool_name}'.")
            else:
                final_state = TaskStateEnum.FAILED
                error_message = output_data.error.message if output_data.error else "Unknown MCP proxy failure."
                self.logger.error(f"Task {task_id}: MCP proxy call failed: {error_message}")

            # 5. Send A2A Response
            try:
                # Use a safe version of model_dump to avoid recursion errors
                output_content = {}
                if hasattr(output_data, 'model_dump') and callable(getattr(output_data, 'model_dump')):
                    try:
                        output_content = output_data.model_dump(exclude_none=True)
                    except RecursionError:
                        # Fallback for recursion issues
                        output_content = {
                            "success": output_data.success,
                            "mcp_result": output_data.mcp_result if output_data.success else None,
                            "error": {
                                "source": output_data.error.source if output_data.error else None,
                                "code": output_data.error.code if output_data.error else None,
                                "message": output_data.error.message if output_data.error else None
                            } if not output_data.success and output_data.error else None
                        }
                else:
                    # Basic fallback if model_dump is not available
                    output_content = {
                        "success": output_data.success,
                        "mcp_result": output_data.mcp_result,
                        "error": output_data.error
                    }
                
                response_msg = Message(role="assistant", parts=[DataPart(content=output_content)])
                await self.task_store.notify_message_event(task_id, response_msg)
                await asyncio.sleep(0.1)
            except Exception as msg_err:
                self.logger.error(f"Task {task_id}: Error sending result message event: {msg_err}")

        except AgentProcessingError as e:
            self.logger.error(f"Task {task_id}: Processing error: {e}")
            error_message = str(e)
            final_state = TaskStateEnum.FAILED
        except ConfigurationError as e:
            self.logger.error(f"Task {task_id}: Config error: {e}")
            error_message = str(e)
            final_state = TaskStateEnum.FAILED
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error during MCP proxy process: {e}")
            error_message = f"Unexpected error: {e}"
            final_state = TaskStateEnum.FAILED
        finally:
            self.logger.info(f"Task {task_id}: Setting final state to {final_state}")
            # Use the specific error message from output_data.error if available
            final_error_msg = error_message
            if output_data and output_data.error and not output_data.success:
                final_error_msg = f"[{output_data.error.source}/{output_data.error.code}] {output_data.error.message}"

            await self.task_store.update_task_state(task_id, final_state, message=final_error_msg)
            await asyncio.sleep(0.1)
            self.logger.info(f"Task {task_id}: Background processing finished.")

    # --- Standard A2A Handlers (Get, Cancel, Subscribe) ---
    async def handle_task_get(self, task_id: str) -> Task:
        if not self.task_store:
            raise ConfigurationError("Task store missing.")
            
        context = await self.task_store.get_task(task_id)
        if context is None:
            raise TaskNotFoundError(task_id=task_id)
            
        messages = await self.task_store.get_messages(task_id) or []
        artifacts = await self.task_store.get_artifacts(task_id) or []
        
        return Task(
            id=task_id, 
            state=context.current_state, 
            createdAt=context.created_at, 
            updatedAt=context.updated_at, 
            messages=messages, 
            artifacts=artifacts
        )

    async def handle_task_cancel(self, task_id: str) -> bool:
        if not self.task_store:
            raise ConfigurationError("Task store missing.")
            
        context = await self.task_store.get_task(task_id)
        if context is None:
            raise TaskNotFoundError(task_id=task_id)
            
        terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
        if context.current_state not in terminal:
            await self.task_store.update_task_state(task_id, TaskStateEnum.CANCELED, "Cancelled by request.")
            return True
            
        return False

    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        self.logger.info(f"Task {task_id}: Entered handle_subscribe_request.")
        
        if not self.task_store:
            raise ConfigurationError("Task store missing.")
            
        q = asyncio.Queue()
        await self.task_store.add_listener(task_id, q)
        self.logger.info(f"Task {task_id}: Listener queue added.")
        
        context = await self.task_store.get_task(task_id)
        if context:
            now = datetime.datetime.now(datetime.timezone.utc)
            status_event = TaskStatusUpdateEvent(taskId=task_id, state=context.current_state, timestamp=now)
            try:
                yield status_event
                await asyncio.sleep(0.05)
            except Exception as e:
                self.logger.error(f"Task {task_id}: Error yielding initial state: {e}")
                
        try:
            event_count = 0
            while True:
                try:
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=2.0)
                        event_count += 1
                        self.logger.info(f"Task {task_id}: Retrieved event #{event_count} from queue: type={type(event).__name__}")
                    except asyncio.TimeoutError:
                        context = await self.task_store.get_task(task_id)
                        if context and context.current_state in [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]:
                            break
                        continue
                        
                    try:
                        yield event
                        await asyncio.sleep(0.05)
                    except Exception as yield_err:
                        self.logger.error(f"Task {task_id}: Error during yield: {yield_err}", exc_info=True)
                        break
                        
                except Exception as loop_err:
                    self.logger.error(f"Task {task_id}: Error in main event processing loop: {loop_err}", exc_info=True)
                    break
                    
                context = await self.task_store.get_task(task_id)
                if context and context.current_state in [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]:
                    break
                    
        except asyncio.CancelledError:
            self.logger.info(f"Task {task_id}: SSE stream cancelled.")
            raise
        except Exception as loop_err:
            self.logger.error(f"Task {task_id}: Error in SSE generator outer loop: {loop_err}", exc_info=True)
        finally:
            await self.task_store.remove_listener(task_id, q)
            self.logger.info(f"Task {task_id}: SSE listener removed. Events yielded: {event_count}.")

    async def close(self):
        await self.http_client.aclose()
        self.logger.info("SecOps MCP Tool Proxy Agent closed.")
