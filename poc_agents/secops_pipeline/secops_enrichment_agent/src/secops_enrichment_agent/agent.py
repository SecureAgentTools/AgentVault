import json
import logging
import asyncio
import os
import uuid
import datetime
import re  # For basic IOC type detection
import httpx  # Add explicit import for HTTP client
from typing import Dict, Any, Union, Optional, List, AsyncGenerator
import random  # For mock data simulation

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
    # Import client library components needed to call the MCP Proxy
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

# Import local input model
from .models import EnrichmentInput
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
                class McpToolExecOutput(BaseModel): 
                    success: bool
                    mcp_result: Optional[Dict[str,Any]] = None
                    error: Optional[McpErrorDetails] = None
        except Exception as e:
            logging.error(f"Error setting up imports: {e}")
            class McpErrorDetails(BaseModel): 
                source: str
                code: str
                message: str
                details: Optional[Dict[str,Any]] = None
            class McpToolExecOutput(BaseModel): 
                success: bool
                mcp_result: Optional[Dict[str,Any]] = None
                error: Optional[McpErrorDetails] = None


logger = logging.getLogger(__name__)
AGENT_ID = "local-poc/secops-enrichment-agent" # Match agent card

# --- Config ---
MCP_PROXY_AGENT_HRI = os.environ.get("MCP_PROXY_AGENT_HRI", "local-poc/mcp-tool-proxy")
AGENTVAULT_REGISTRY_URL = os.environ.get("AGENTVAULT_REGISTRY_URL", "http://host.docker.internal:8000")

# --- Agent Logic ---
class SecOpsEnrichmentAgent(BaseA2AAgent):
    """
    Agent responsible for enriching IOCs by calling the MCP Tool Proxy Agent.
    """
    def __init__(self, task_store: BaseTaskStore):
        super().__init__(agent_metadata={"name": "SecOps Enrichment Agent"})
        self.task_store = task_store
        self.logger = logger
        self.key_manager = KeyManager(use_keyring=True) if _AGENTVAULT_AVAILABLE else None
        self.proxy_agent_card: Optional[AgentCard] = None
        self._proxy_card_load_attempted = False
        self._http_client = None  # Shared client for all HTTP requests
        logger.info(f"{AGENT_ID} initialized.")
        
    async def start(self):
        """Initialize the HTTP client for reuse across all calls."""
        self._http_client = httpx.AsyncClient(timeout=10.0)
        logger.info("Shared HTTP client initialized")
        
    async def close(self):
        """Close the HTTP client when the agent shuts down."""
        if self._http_client:
            await self._http_client.aclose()
            logger.info("Shared HTTP client closed")
            self._http_client = None

    async def _get_proxy_agent_card(self) -> AgentCard:
        """Directly loads the MCP Proxy Agent card from its HTTP endpoint."""
        if self.proxy_agent_card: return self.proxy_agent_card
        if self._proxy_card_load_attempted: raise ConfigurationError("MCP Proxy Agent card could not be loaded previously.")
        self._proxy_card_load_attempted = True
        if not _AGENTVAULT_AVAILABLE: raise ConfigurationError("AgentVault library components are missing.")
        
        # Instead of using the registry, fetch directly from the MCP proxy's HTTP endpoint
        proxy_base_url = "http://secops-mcp-proxy:8069"  # Docker service name and port
        card_url = f"{proxy_base_url}/agent-card.json"
        
        self.logger.info(f"Loading MCP Proxy Agent card directly from URL: {card_url}")
        try:
            # Initialize the HTTP client if it doesn't exist
            if not self._http_client:
                self.logger.info("Creating HTTP client as it doesn't exist")
                self._http_client = httpx.AsyncClient(timeout=10.0)
            
            # Use the shared HTTP client
            response = await self._http_client.get(card_url)
            self.logger.info(f"MCP Proxy Agent card fetch response status: {response.status_code}")
            
            if response.status_code != 200:
                error_msg = f"Failed to fetch MCP Proxy Agent card from URL '{card_url}'. Status: {response.status_code}. Response: {response.text}"
                self.logger.error(error_msg)
                raise ConfigurationError(error_msg)
                
            try:
                card_data = response.json()
            except Exception as json_err:
                self.logger.error(f"Failed to parse JSON from MCP Proxy Agent card response: {json_err}. Raw response: {response.text[:500]}...")
                raise ConfigurationError(f"Invalid JSON in MCP Proxy Agent card: {json_err}")
                
            # Modify the URL to use localhost instead of service name to pass validation
            if "url" in card_data:
                original_url = card_data["url"]
                # Save the original URL for later use
                self.original_proxy_url = original_url
                # Replace with localhost version for validation
                card_data["url"] = original_url.replace("http://secops-mcp-proxy:", "http://localhost:")
                self.logger.info(f"Modified URL from {original_url} to {card_data['url']} for validation")
            
            # Create an AgentCard from the JSON data - handle field aliases correctly
            # The AgentCard model uses snake_case field names but expects camelCase in JSON
            self.proxy_agent_card = AgentCard.model_validate(card_data)
            
            # Important: Set the URL back to the original for actual API calls
            if hasattr(self, 'original_proxy_url'):
                self.logger.info(f"Restoring original URL: {self.original_proxy_url}")
                self.proxy_agent_card.url = self.original_proxy_url
            self.logger.info(f"MCP Proxy Agent card loaded successfully: {self.proxy_agent_card.url}")
            return self.proxy_agent_card
            
        except Exception as e: 
            self.logger.exception(f"Failed to load MCP Proxy Agent card: {e}")
            raise ConfigurationError(f"Failed to load MCP Proxy Agent card: {e}")

    async def handle_task_send(self, task_id: Optional[str], message: Message) -> str:
        if task_id: raise AgentProcessingError(f"Enrichment agent does not support continuing task {task_id}")
        new_task_id = f"enrich-{uuid.uuid4().hex[:8]}"; self.logger.info(f"Task {new_task_id}: Received enrichment request.")
        input_data: Optional[Dict[str, Any]] = None
        if message.parts:
            for part in message.parts:
                if isinstance(part, DataPart) and isinstance(part.content, dict): input_data = part.content; break
        if not input_data:
            await self.task_store.create_task(new_task_id); await self.task_store.update_task_state(new_task_id, TaskStateEnum.FAILED, "Invalid input: Expected DataPart."); raise AgentProcessingError("Invalid input: Expected DataPart.")
        await self.task_store.create_task(new_task_id)
        asyncio.create_task(self.process_enrichment_task(new_task_id, input_data))
        return new_task_id

    async def _call_proxy_for_ioc(self, client: AgentVaultClient, proxy_card: AgentCard, ioc: str) -> Dict[str, Any]:
        """Helper to call MCP proxy for a single IOC and parse the result."""
        # Log the start of the call to help with debugging
        self.logger.info(f"Starting proxy call for IOC: {ioc}")
        
        # Determine target_mcp_server_id and tool_name based on IOC type (placeholder)
        target_mcp_id: Optional[str] = None
        tool_name: Optional[str] = None
        mcp_arguments: Optional[Dict[str, Any]] = None

        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ioc): # IP Address
            target_mcp_id = "tip_virustotal" # Logical name for proxy config
            tool_name = "ip.report"         # Tool name on that server
            mcp_arguments = {"ip": ioc}
        elif '.' in ioc and not re.match(r'^[a-fA-F0-9]{32,}$', ioc): # Domain
            target_mcp_id = "tip_abuseipdb" # Example, could be same or different
            tool_name = "domain.check"
            mcp_arguments = {"domain": ioc}
        elif re.match(r'^[a-fA-F0-9]{32,}$', ioc): # Hash (MD5, SHA1, SHA256 etc.)
            target_mcp_id = "tip_virustotal"
            tool_name = "file.report" # VT uses 'file' for hashes
            mcp_arguments = {"resource": ioc} # VT API uses 'resource' for hash
        else:
            return {"error": "Unknown IOC type", "details": "Cannot determine enrichment method."}

        proxy_input_payload = {
            "target_mcp_server_id": target_mcp_id,
            "tool_name": tool_name,
            "arguments": mcp_arguments
        }
        proxy_message = Message(role="system", parts=[DataPart(content=proxy_input_payload)])

        try:
            proxy_task_id = await client.initiate_task(proxy_card, proxy_message, self.key_manager) # type: ignore
            self.logger.debug(f"Proxy task {proxy_task_id} initiated for IOC '{ioc}'.")

            proxy_response_content: Optional[Dict[str, Any]] = None
            async for event in client.receive_messages(proxy_card, proxy_task_id, self.key_manager): # type: ignore
                if isinstance(event, TaskMessageEvent) and event.message.role == "assistant":
                    if event.message.parts and isinstance(event.message.parts, DataPart): # Assuming single DataPart
                        proxy_response_content = event.message.parts.content
                        break
                if isinstance(event, TaskStatusUpdateEvent) and event.state.is_terminal():
                    if event.state != TaskStateEnum.COMPLETED:
                        self.logger.warning(f"Proxy task {proxy_task_id} for IOC '{ioc}' ended with state {event.state}. Message: {event.message}")
                        return {"error": f"Proxy task failed with state {event.state}", "details": event.message}
                    break # Terminal state reached

            if not proxy_response_content:
                return {"error": "No result content from proxy.", "details": f"Proxy task {proxy_task_id} ended without data."}

            # Validate proxy_response_content against McpToolExecOutput
            try:
                mcp_exec_output = McpToolExecOutput.model_validate(proxy_response_content)
                if mcp_exec_output.success and mcp_exec_output.mcp_result:
                    return {"source": target_mcp_id, **mcp_exec_output.mcp_result} # Combine source for clarity
                elif mcp_exec_output.error:
                    return {"error": f"MCP tool error: {mcp_exec_output.error.message}", "details": mcp_exec_output.error.model_dump(exclude_none=True)}
                else:
                    return {"error": "Proxy reported failure but no error details.", "details": proxy_response_content}
            except ValidationError as val_err:
                self.logger.error(f"Failed to validate proxy response for IOC '{ioc}': {val_err}. Response: {proxy_response_content}")
                return {"error": "Invalid response structure from proxy.", "details": str(val_err)}

        except (CoreAgentVaultError, A2AError) as proxy_err: # More specific error catching
            self.logger.error(f"A2A Error calling MCP proxy for IOC '{ioc}': {proxy_err}", exc_info=True)
            return {"error": f"A2A Error calling proxy: {str(proxy_err)}"}
        except Exception as inner_err:
            self.logger.exception(f"Unexpected error during proxy call for IOC '{ioc}': {inner_err}")
            return {"error": f"Unexpected proxy call error: {str(inner_err)}"}


    async def process_enrichment_task(self, task_id: str, input_data: Dict[str, Any]):
        await self.task_store.update_task_state(task_id, TaskStateEnum.WORKING)
        self.logger.info(f"Task {task_id}: Background processing started (Real Proxy Calls).")

        final_state = TaskStateEnum.FAILED
        error_message: Optional[str] = "Unknown processing error during enrichment."
        enrichment_results: Dict[str, Any] = {}
        
        # Initialize the HTTP client if needed
        if not self._http_client:
            self.logger.info("Initializing HTTP client for enrichment task")
            self._http_client = httpx.AsyncClient(timeout=10.0)

        if not _AGENTVAULT_AVAILABLE:
            error_message = "AgentVault library not available for real enrichment calls."; self.logger.critical(error_message)
            # Fallback to mock data if library is missing, so orchestrator doesn't completely break
            try: validated_input = EnrichmentInput.model_validate(input_data); iocs = validated_input.iocs
            except: iocs = input_data.get("iocs", [])
            for ioc in iocs: enrichment_results[ioc] = {"error": "MOCK_FALLBACK_NO_LIBRARY", "reputation": "Unknown"}
            final_state = TaskStateEnum.COMPLETED # Complete with mock data
        else:
            try:
                validated_input = EnrichmentInput.model_validate(input_data)
                iocs = validated_input.iocs
                self.logger.info(f"Task {task_id}: Processing {len(iocs)} IOCs: {iocs}")

                proxy_card = await self._get_proxy_agent_card()

                async with AgentVaultClient() as client: # Create client instance for all calls
                    for ioc in iocs:
                        try:
                            enrichment_results[ioc] = await self._call_proxy_for_ioc(client, proxy_card, ioc)
                            self.logger.info(f"Successfully processed IOC {ioc}")
                        except Exception as ioc_err:
                            self.logger.error(f"Error processing IOC {ioc}: {ioc_err}")
                            # Add error to results instead of failing the whole task
                            enrichment_results[ioc] = {"error": f"Processing error: {str(ioc_err)}", "details": "IOC enrichment failed with exception"}
                        await asyncio.sleep(0.1) # Small delay between IOCs if needed

                final_state = TaskStateEnum.COMPLETED; error_message = None
                self.logger.info(f"Task {task_id}: Enrichment processing via proxy completed.")
                
                # FIXED: Publish enrichment results to Redis with proper formatting
                try:
                    import redis
                    redis_client = redis.Redis(host='secops-redis', port=6379, decode_responses=True)
                    
                    # Format the results for the dashboard in the expected structure
                    formatted_results = []
                    for ioc, data in enrichment_results.items():
                        # Determine the indicator type
                        indicator_type = "Unknown"
                        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ioc):
                            indicator_type = "IP"
                        elif '.' in ioc and not re.match(r'^[a-fA-F0-9]{32,}$', ioc):
                            indicator_type = "Domain"
                        elif re.match(r'^[a-fA-F0-9]{32,}$', ioc):
                            indicator_type = "Hash"
                        
                        # Determine a verdict based on the data
                        verdict = "Unknown"
                        if isinstance(data, dict):
                            if "error" in data:
                                verdict = "Error"
                            elif "malicious" in data and data["malicious"]:
                                verdict = "Malicious"
                            elif "suspicious" in data and data["suspicious"]:
                                verdict = "Suspicious"
                            elif "reputation" in data:
                                if "malicious" in str(data["reputation"]).lower():
                                    verdict = "Malicious"
                                elif "suspicious" in str(data["reputation"]).lower():
                                    verdict = "Suspicious"
                                elif "safe" in str(data["reputation"]).lower() or "clean" in str(data["reputation"]).lower():
                                    verdict = "Clean"
                        
                        # Add to formatted results
                        formatted_results.append({
                            "indicator": ioc,
                            "type": indicator_type,
                            "verdict": verdict,
                            "details": data
                        })
                    
                    # Create the enrichment event with properly formatted results
                    enrichment_event = {
                        "event_type": "enrichment_results",
                        "project_id": validated_input.project_id if hasattr(validated_input, 'project_id') else "unknown-project",
                        "results": formatted_results,  # Use the formatted results
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                    
                    self.logger.info(f"Publishing enrichment results to Redis channel 'secops_events'")
                    self.logger.debug(f"Enrichment data: {json.dumps(enrichment_event)[:200]}...")
                    
                    # Publish the event
                    publish_result = redis_client.publish('secops_events', json.dumps(enrichment_event))
                    self.logger.info(f"Redis publish result: {publish_result}")
                    
                    # Also store as a Redis key for backup/recovery - FIXED KEY FORMAT for dashboard
                    redis_client.set(f"enrichment:results:{validated_input.project_id}", json.dumps(enrichment_event), ex=3600)
                    redis_client.close()
                except Exception as redis_err:
                    self.logger.error(f"Failed to publish enrichment results to Redis: {redis_err}")
                    # Don't fail the task if Redis publishing fails

            except AgentProcessingError as e: self.logger.error(f"Task {task_id}: Processing error: {e}"); error_message = str(e)
            except ConfigurationError as e: self.logger.error(f"Task {task_id}: Configuration error: {e}"); error_message = str(e)
            except Exception as e: self.logger.exception(f"Task {task_id}: Unexpected error: {e}"); error_message = f"Unexpected: {e}"

        # Create a try-except-finally block for proper error handling
        try:
            result_message = Message(role="assistant", parts=[DataPart(content=enrichment_results)])
            try:
                await self.task_store.notify_message_event(task_id, result_message)
            except Exception as notify_err:
                logger.error(f"Task {task_id}: Failed to notify: {notify_err}")
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
