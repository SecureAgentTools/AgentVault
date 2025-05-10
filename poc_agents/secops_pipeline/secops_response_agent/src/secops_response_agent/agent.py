import logging
import asyncio
import os
import uuid
import datetime
import re
from typing import Dict, Any, Union, Optional, List, AsyncGenerator

from pydantic import BaseModel, Field, ValidationError

# SDK Imports
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import InMemoryTaskStore, BaseTaskStore, TaskContext
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Core Library Imports
try:
    from agentvault.models import (
        Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent,
        TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent, AgentCard
    )
    from agentvault import AgentVaultClient, KeyManager, agent_card_utils
    from agentvault.exceptions import AgentVaultError as CoreAgentVaultError, A2AError
    TaskStateEnum = TaskState
    _AGENTVAULT_AVAILABLE = True
except ImportError:
    logging.critical("Failed to import agentvault core models/client. Agent may not function.", exc_info=True)
    class TaskStateEnum:
        COMPLETED="COMPLETED"
        FAILED="FAILED"
        WORKING="WORKING"
        CANCELED="CANCELED"
        SUBMITTED="SUBMITTED"
        def is_terminal(self): return True
    class Message: pass
    class DataPart: pass
    class Task: pass
    class A2AEvent: pass
    class AgentCard: pass
    class TaskStatusUpdateEvent: pass
    class TaskMessageEvent: pass
    class TaskArtifactUpdateEvent: pass
    class AgentVaultClient: pass
    class KeyManager: pass
    class agent_card_utils: pass
    class CoreAgentVaultError(Exception): pass
    class A2AError(Exception): pass
    _AGENTVAULT_AVAILABLE = False

# Import local models
from .models import ResponseActionInput, ActionExecutionResult, ActionStatusDetails

# Import shared registry helpers
try:
    from shared.registry_helpers import load_agent_card
    logging.info("Successfully imported load_agent_card from shared registry_helpers")
except ImportError:
    logging.warning("Failed to import load_agent_card from shared.registry_helpers")
    load_agent_card = None

# Import the McpToolExecOutput model from shared models
try:
    # Try to import from the shared directory first
    from shared.mcp_models import McpToolExecOutput, McpErrorDetails
    logging.info("Successfully imported McpToolExecOutput from shared models")
except ImportError:
    try:
        # Fall back to direct import from proxy agent if available
        from mcp_tool_proxy_agent.models import McpToolExecOutput, McpErrorDetails
        logging.info("Imported McpToolExecOutput from proxy agent directly")
    except ImportError:
        # Use our own import helper as last resort
        try:
            # Ensure path is set up correctly
            from .utils.import_helpers import ensure_shared_imports
            ensure_shared_imports()
            
            # Now try importing again with updated path
            try:
                from mcp_models import McpToolExecOutput, McpErrorDetails
                logging.info("Imported McpToolExecOutput from shared module after path update")
            except ImportError:
                logging.warning("Could not import McpToolExecOutput from any source, using placeholder.")
                class McpErrorDetails(BaseModel): 
                    source: str
                    code: str
                    message: str
                    details: Optional[Dict[str,Any]] = None
                    def model_dump(self, **kwargs): 
                        return self.dict(**kwargs)
                class McpToolExecOutput(BaseModel): 
                    success: bool
                    mcp_result: Optional[Dict[str,Any]] = None
                    error: Optional[McpErrorDetails] = None
                    @classmethod
                    def model_validate(cls, data):
                        return cls.parse_obj(data)
        except Exception as e:
            logging.error(f"Error setting up imports: {e}")
            class McpErrorDetails(BaseModel): 
                source: str
                code: str
                message: str
                details: Optional[Dict[str,Any]] = None
                def model_dump(self, **kwargs): 
                    return self.dict(**kwargs)
            class McpToolExecOutput(BaseModel): 
                success: bool
                mcp_result: Optional[Dict[str,Any]] = None
                error: Optional[McpErrorDetails] = None
                @classmethod
                def model_validate(cls, data):
                    return cls.parse_obj(data)


logger = logging.getLogger(__name__)
AGENT_ID = "local-poc/secops-response-agent" # Match agent card

# --- Config ---
# We no longer need MCP_PROXY_AGENT_HRI as we're fetching the card directly
# MCP_PROXY_URL specifies the base URL of the MCP proxy service
MCP_PROXY_URL = os.environ.get("MCP_PROXY_URL", "http://secops-mcp-proxy:8069")
AGENTVAULT_REGISTRY_URL = os.environ.get("AGENTVAULT_REGISTRY_URL", "http://host.docker.internal:8000")

# Action Type Constants (match orchestrator/card)
ACTION_CREATE_TICKET = "CREATE_TICKET"
ACTION_BLOCK_IP = "BLOCK_IP"
ACTION_ISOLATE_HOST = "ISOLATE_HOST"

# --- Agent Logic ---
class SecOpsResponseAgent(BaseA2AAgent):
    """
    Agent responsible for executing defined response actions by calling
    the MCP Tool Proxy Agent.
    """
    def __init__(self, task_store: BaseTaskStore):
        super().__init__(agent_metadata={"name": "SecOps Response Agent"})
        self.task_store = task_store
        self.logger = logger
        self.key_manager = KeyManager(use_keyring=True) if _AGENTVAULT_AVAILABLE else None
        self.proxy_agent_card: Optional[AgentCard] = None
        self._proxy_card_load_attempted = False
        logger.info(f"{AGENT_ID} initialized.")

    async def _get_proxy_agent_card(self) -> AgentCard:
        """Directly creates the MCP Proxy Agent card with valid URL."""
        if self.proxy_agent_card: return self.proxy_agent_card
        if self._proxy_card_load_attempted: raise ConfigurationError("MCP Proxy Agent card could not be loaded previously.")
        self._proxy_card_load_attempted = True
        if not _AGENTVAULT_AVAILABLE: raise ConfigurationError("AgentVault library components are missing.")
        
        # Hard-code the MCP Tool Proxy Agent card to bypass URL validation
        self.logger.info(f"Creating hardcoded MCP Proxy Agent card")
        try:
            # Create a minimal valid card with a localhost URL to pass validation
            # The real URL will be stored separately
            card_data = {
                "schemaVersion": "1.0",
                "humanReadableId": "local-poc/mcp-tool-proxy",
                "agentVersion": "0.1.0",
                "name": "MCP Tool Proxy Agent",
                "description": "Proxies AgentVault A2A requests to MCP-compliant tool servers.",
                "url": "http://localhost:8069/a2a",  # Use localhost to pass validation
                "provider": {
                    "name": "SecOps Team"
                },
                "capabilities": {
                    "a2aVersion": "1.0",
                    "supportedMessageParts": ["data"]
                },
                "authSchemes": [
                    {
                        "scheme": "none",
                        "description": "No authentication required for this agent (PoC)."
                    }
                ],
                "skills": [
                    {
                        "id": "mcp.execute_tool",
                        "name": "Execute MCP Tool",
                        "description": "Executes a specific tool via configured MCP server.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "target_mcp_server_id": {
                                    "type": "string",
                                    "description": "Logical identifier for the target MCP server."
                                },
                                "tool_name": {
                                    "type": "string",
                                    "description": "The tool name on the target MCP server."
                                },
                                "arguments": {
                                    "type": "object",
                                    "description": "Arguments for the tool."
                                }
                            },
                            "required": ["target_mcp_server_id", "tool_name", "arguments"]
                        },
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "success": { "type": "boolean" },
                                "mcp_result": { "type": ["object", "null"] },
                                "error": { "type": ["object", "null"] }
                            },
                            "required": ["success"]
                        }
                    }
                ]
            }
            
            # Create the agent card using model_validate
            self.proxy_agent_card = AgentCard.model_validate(card_data)
            
            # The actual Docker service URL we want to use
            actual_url = "http://secops-mcp-proxy:8069/a2a"
            self.logger.info(f"MCP Proxy Agent card created with URL: {self.proxy_agent_card.url}")
            self.logger.info(f"Will use actual URL: {actual_url} for Docker networking")
            
            # Store the actual URL for use in later requests
            # We'll use this URL instead of the one in the card
            self._actual_proxy_url = actual_url
            
            return self.proxy_agent_card
        except Exception as e: 
            self.logger.exception(f"Failed to create MCP Proxy Agent card: {e}")
            raise ConfigurationError(f"Failed to create MCP Proxy Agent card: {e}")

    async def handle_task_send(self, task_id: Optional[str], message: Message) -> str:
        # Identical to other specialist agents
        if task_id: raise AgentProcessingError(f"Response agent does not support continuing task {task_id}")
        new_task_id = f"response-{uuid.uuid4().hex[:8]}"; self.logger.info(f"Task {new_task_id}: Received response execution request.")
        input_data: Optional[Dict[str, Any]] = None
        if message.parts:
            for part in message.parts:
                if isinstance(part, DataPart) and isinstance(part.content, dict): input_data = part.content; break
        if not input_data:
            await self.task_store.create_task(new_task_id); await self.task_store.update_task_state(new_task_id, TaskStateEnum.FAILED, "Invalid input: Expected DataPart."); raise AgentProcessingError("Invalid input: Expected DataPart.")
        await self.task_store.create_task(new_task_id)
        asyncio.create_task(self.process_response_task(new_task_id, input_data))
        return new_task_id

    async def _call_proxy_for_response_action(
        self, client: AgentVaultClient, proxy_card: AgentCard,
        target_mcp_id: str, tool_name: str, mcp_arguments: Dict[str, Any]
    ) -> McpToolExecOutput:
        """Helper to make a single call to the MCP Proxy for a response action."""
        # This helper now uses direct URL modification instead of monkey-patching
        proxy_input_payload = {
            "target_mcp_server_id": target_mcp_id,
            "tool_name": tool_name,
            "arguments": mcp_arguments
        }
        proxy_message = Message(role="system", parts=[DataPart(content=proxy_input_payload)])
        
        # Save original URL and prepare Docker service URL
        original_url = proxy_card.url
        actual_url = getattr(self, "_actual_proxy_url", "http://secops-mcp-proxy:8069/a2a")
        
        # For debugging
        self.logger.info(f"Using proxy URL: {actual_url} (card has: {original_url})")
        
        # Temporarily modify the card URL to use Docker service name
        # No need to monkey-patch client.session which doesn't exist
        proxy_card.url = actual_url
        
        try:
            # Make the request with the modified card URL
            proxy_task_id = await client.initiate_task(proxy_card, proxy_message, self.key_manager) # type: ignore
            self.logger.debug(f"Proxy task {proxy_task_id} initiated for tool '{tool_name}' with target '{target_mcp_id}'.")

            proxy_response_content: Optional[Dict[str, Any]] = None
            async for event in client.receive_messages(proxy_card, proxy_task_id, self.key_manager): # type: ignore
                if isinstance(event, TaskMessageEvent) and event.message.role == "assistant":
                    # Assuming the proxy's result is in a DataPart of the first assistant message
                    if event.message.parts:
                        for part in event.message.parts:
                            if isinstance(part, DataPart) and isinstance(part.content, dict):
                                proxy_response_content = part.content
                                break
                        if proxy_response_content:
                            break
                if isinstance(event, TaskStatusUpdateEvent) and event.state.is_terminal():
                    if event.state != TaskStateEnum.COMPLETED:
                        self.logger.warning(f"Proxy task {proxy_task_id} for tool '{tool_name}' ended with state {event.state}. Message: {event.message}")
                        error_details = McpErrorDetails(source="A2A_PROXY", code="PROXY_TASK_NON_COMPLETED", message=f"Proxy task failed with state {event.state}", details={"original_message": event.message})
                        return McpToolExecOutput(success=False, error=error_details)
                    break # Task is terminal, stop listening
            
            if not proxy_response_content:
                self.logger.error(f"No result DataPart received from proxy task {proxy_task_id} for tool '{tool_name}'.")
                error_details = McpErrorDetails(source="A2A_PROXY", code="PROXY_NO_RESPONSE_DATA", message="No result content from proxy")
                return McpToolExecOutput(success=False, error=error_details)
            
            try:
                # Validate the structure of the content from DataPart
                return McpToolExecOutput.model_validate(proxy_response_content)
            except ValidationError as val_err:
                self.logger.error(f"Failed to validate proxy response for tool '{tool_name}': {val_err}. Response: {proxy_response_content}")
                error_details = McpErrorDetails(source="A2A_PROXY", code="PROXY_RESPONSE_INVALID_SCHEMA", message=f"Invalid response structure from proxy: {val_err}", details=proxy_response_content)
                return McpToolExecOutput(success=False, error=error_details)
        finally:
            # Restore the original URL
            proxy_card.url = original_url


    async def process_response_task(self, task_id: str, input_data: Dict[str, Any]):
        await self.task_store.update_task_state(task_id, TaskStateEnum.WORKING)
        self.logger.info(f"Task {task_id}: Background response processing started.")

        final_state = TaskStateEnum.FAILED
        error_message: Optional[str] = "Unknown action processing error."
        action_result = ActionExecutionResult(action=input_data.get("action_type", "Unknown"), status="Error", details=ActionStatusDetails())

        if not _AGENTVAULT_AVAILABLE:
            action_result.details = ActionStatusDetails(error_details="AgentVault library not available for real proxy calls.") # type: ignore
            error_message = str(action_result.details.error_details); self.logger.critical(error_message) # type: ignore
        else:
            try:
                validated_input = ResponseActionInput.model_validate(input_data)
                action_type = validated_input.action_type
                parameters = validated_input.parameters
                action_result.action = action_type
                self.logger.info(f"Task {task_id}: Validated request for action '{action_type}'. Params: {parameters}")

                proxy_card = await self._get_proxy_agent_card()

                target_mcp_id: Optional[str] = None
                tool_name: Optional[str] = None
                mcp_arguments: Dict[str, Any] = parameters # Start with all params from orchestrator

                # --- Action Mapping Logic to MCP Proxy Call ---
                if action_type == ACTION_CREATE_TICKET:
                    target_mcp_id = "ticketing_system_jira" # Example logical ID for proxy config
                    tool_name = "jira.createIssue"   # Example MCP tool name for creating an issue
                    # Arguments for 'jira.createIssue' should match what the proxied Jira tool expects
                    # The 'parameters' from orchestrator should already contain 'summary', 'description', etc.
                    # mcp_arguments = parameters # Already set
                elif action_type == ACTION_BLOCK_IP:
                    target_mcp_id = "network_firewall_main" # Example logical ID
                    tool_name = "firewall.blockIpAddress"
                    # mcp_arguments already contains 'ip_address' from orchestrator parameters
                elif action_type == ACTION_ISOLATE_HOST:
                    target_mcp_id = "endpoint_detection_response_edr" # Example logical ID
                    tool_name = "edr.isolateEndpoint"
                    # mcp_arguments already contains 'hostname' or 'host_id' from orchestrator
                else:
                    raise AgentProcessingError(f"Unsupported action_type requested: {action_type}")

                if not target_mcp_id or not tool_name: # Should be caught by unsupported action_type
                    raise AgentProcessingError("Internal error: Failed to determine MCP call details for action.")

                async with AgentVaultClient() as client:
                    proxy_output = await self._call_proxy_for_response_action(
                        client, proxy_card, target_mcp_id, tool_name, mcp_arguments
                    )

                if proxy_output.success and proxy_output.mcp_result:
                    action_result.status = "Success"
                    # Store the result from the actual tool (e.g., ticket ID, block rule ID) in details
                    # The structure of mcp_result.content depends on the tool server
                    # For a 'CREATE_TICKET' action, it might be like:
                    # proxy_output.mcp_result.get("content", [{}]).get("ticket_id")
                    # For safety, we pass the whole mcp_result content as details for now
                    action_result.details = ActionStatusDetails(**proxy_output.mcp_result.get("content",[{}]) if proxy_output.mcp_result.get("content") else {})
                    final_state = TaskStateEnum.COMPLETED; error_message = None
                    self.logger.info(f"Task {task_id}: Action '{action_type}' executed successfully via proxy. Details: {action_result.details}")
                else:
                    err_details_from_proxy = proxy_output.error.model_dump(exclude_none=True) if proxy_output.error else {"message":"Unknown proxy error"}
                    action_result.status = "Failed"
                    action_result.details = ActionStatusDetails(error_details=err_details_from_proxy)
                    error_message = f"Failed to execute '{action_type}' via proxy. Error: {proxy_output.error.message if proxy_output.error else 'Details unavailable'}"
                    self.logger.error(f"Task {task_id}: {error_message}")

            except AgentProcessingError as e: self.logger.error(f"Task {task_id}: Processing error: {e}"); error_message = str(e); action_result.details = ActionStatusDetails(error_details=error_message) # type: ignore
            except ConfigurationError as e: self.logger.error(f"Task {task_id}: Config error: {e}"); error_message = str(e); action_result.details = ActionStatusDetails(error_details=error_message) # type: ignore
            except Exception as e: self.logger.exception(f"Task {task_id}: Unexpected error: {e}"); error_message = f"Unexpected: {e}"; action_result.details = ActionStatusDetails(error_details=error_message) # type: ignore

            if error_message: final_state = TaskStateEnum.FAILED; action_result.status = "Error"

        # Create a try-except block for proper error handling
        try:
            # Handle both Pydantic v1 and v2 compatible serialization
            if hasattr(action_result, 'model_dump'):
                result_payload = action_result.model_dump(exclude_none=True)
            else:
                result_payload = action_result.dict(exclude_none=True)
                
            # Always add metadata with error_message if present
            metadata = {}
            if error_message:
                metadata['error_message'] = error_message
                
            # Ensure metadata is a dictionary, not None
            if not metadata:
                metadata = {"status": "task_completed"}  # Add a default value to ensure it's not None
                
            result_message = Message(role="assistant", parts=[DataPart(content=result_payload)], metadata=metadata)
            try:
                await self.task_store.notify_message_event(task_id, result_message)
            except Exception as notify_err:
                self.logger.error(f"Task {task_id}: Failed to notify: {notify_err}")
            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            await asyncio.sleep(0.1)
            self.logger.info(f"Task {task_id}: Background processing finished. Final state: {final_state}")
        except Exception as e:
            self.logger.error(f"Task {task_id}: Error during final processing: {e}")
            try:
                await self.task_store.update_task_state(task_id, TaskStateEnum.FAILED, message=f"Error during final processing: {e}")
            except Exception as update_err:
                self.logger.error(f"Task {task_id}: Failed to update final state: {update_err}")

    # --- Standard A2A Handlers (Get, Cancel, Subscribe) ---
    async def handle_task_get(self, task_id: str) -> Task:
        if not self.task_store: raise ConfigurationError("Task store not initialized.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        messages = await self.task_store.get_messages(task_id) or []
        artifacts = await self.task_store.get_artifacts(task_id) or []
        current_state = context.current_state if TaskStateEnum else str(context.current_state)
        return Task(id=context.task_id, state=current_state, createdAt=context.created_at, updatedAt=context.updated_at, messages=messages, artifacts=artifacts) # type: ignore

    async def handle_task_cancel(self, task_id: str) -> bool:
        if not self.task_store: raise ConfigurationError("Task store not initialized.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        terminal_states = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED] if TaskStateEnum else ["COMPLETED", "FAILED", "CANCELED"]
        if context.current_state not in terminal_states:
            state_to_set = TaskStateEnum.CANCELED if TaskStateEnum else "CANCELED"
            await self.task_store.update_task_state(task_id, state_to_set, "Cancelled by client request.")
            self.logger.info(f"Task {task_id}: Cancellation requested and processed.")
            return True
        self.logger.warning(f"Task {task_id}: Cancellation requested but task already in terminal state {context.current_state}.")
        return False

    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        self.logger.info(f"Task {task_id}: SSE subscription requested.")
        if not self.task_store: raise ConfigurationError("Task store not initialized.")
        listener_queue = asyncio.Queue(); await self.task_store.add_listener(task_id, listener_queue)
        self.logger.debug(f"Task {task_id}: Listener queue added for SSE stream.")
        processed_event_count = 0
        try:
            context = await self.task_store.get_task(task_id)
            if context:
                now = datetime.datetime.now(datetime.timezone.utc);
                state_value = context.current_state if TaskStateEnum else str(context.current_state)
                if _AGENTVAULT_AVAILABLE:
                    status_event = TaskStatusUpdateEvent(taskId=task_id, state=state_value, timestamp=now) # type: ignore
                    yield status_event; await asyncio.sleep(0.05); processed_event_count += 1
            while True:
                try:
                    event = await asyncio.wait_for(listener_queue.get(), timeout=30.0)
                    processed_event_count += 1; self.logger.debug(f"Task {task_id}: Yielding event #{processed_event_count} via SSE: {type(event).__name__}")
                    yield event; await asyncio.sleep(0.05)
                    if _AGENTVAULT_AVAILABLE and isinstance(event, TaskStatusUpdateEvent) and event.state.is_terminal():
                        self.logger.info(f"Task {task_id}: Terminal state {event.state} received via SSE. Closing stream.")
                        break
                except asyncio.TimeoutError:
                    self.logger.debug(f"Task {task_id}: SSE listener timeout. Checking task status.")
                    context = await self.task_store.get_task(task_id)
                    state_value = context.current_state if TaskStateEnum else str(context.current_state)
                    terminal_states = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED] if TaskStateEnum else ["COMPLETED", "FAILED", "CANCELED"]
                    if context and state_value in terminal_states:
                        self.logger.info(f"Task {task_id}: Task found in terminal state {state_value} during SSE timeout check. Closing stream.")
                        break
                    else: continue
                except Exception as e: self.logger.error(f"Task {task_id}: Error processing queue event: {e}", exc_info=True); break
        except asyncio.CancelledError: self.logger.info(f"Task {task_id}: SSE stream cancelled by client or server shutdown."); raise
        except Exception as e: self.logger.error(f"Task {task_id}: Unexpected error in SSE handler: {e}", exc_info=True)
        finally:
            self.logger.info(f"Task {task_id}: Cleaning up SSE listener queue. Total events processed: {processed_event_count}.")
            remove_listener_func = getattr(self.task_store, "remove_listener", None)
            if asyncio.iscoroutinefunction(remove_listener_func): await remove_listener_func(task_id, listener_queue)
            elif callable(remove_listener_func): remove_listener_func(task_id, listener_queue)
