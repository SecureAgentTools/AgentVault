# A2A Client Wrapper for the SecOps Pipeline
# REQ-SECOPS-ORCH-1.7
# Adapted from Dynamics Pipeline Orchestrator

import asyncio
import json
import logging
import sys
import uuid
import urllib.parse
import re # For URL replacement
sys.path.insert(0, '/app/shared')
try:
    from task_state_helpers import apply_taskstate_patch, is_terminal
    apply_taskstate_patch()
    print("Applied TaskState patch successfully in orchestrator")
except Exception as e:
    print(f"Warning: Failed to apply TaskState patch in orchestrator: {e}")
from pathlib import Path
from typing import Dict, Any, Optional, AsyncGenerator, List, cast

import httpx
import pydantic # Ensure pydantic is imported for model validation
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log, RetryError

# Import core AgentVault types with fallback
try:
    from agentvault import AgentVaultClient, KeyManager, agent_card_utils
    from agentvault.models import (
        Message, TextPart, DataPart, Artifact, AgentCard, TaskState, A2AEvent, Task,
        TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent
    )
    from agentvault.exceptions import (
        AgentVaultError, A2AError, A2AConnectionError, A2ARemoteAgentError,
        A2ATimeoutError, A2AMessageError, AgentCardFetchError, KeyManagementError
    )
    # TaskNotFoundError might not be in the current agentvault version - define it locally
    class TaskNotFoundError(A2AError): pass
    _AGENTVAULT_AVAILABLE = True
except ImportError as e:
    # Log critical error if library is missing
    logging.getLogger(__name__).critical(f"CRITICAL ERROR: Failed import 'agentvault': {e}. Orchestrator cannot function.", exc_info=True)
    print(f"FATAL ERROR: Failed to import 'agentvault' library: {e}. Check installation.", file=sys.stderr)
    # Define minimal placeholders to allow script structure parsing, but it won't run
    class AgentVaultClient: pass
    class KeyManager: pass
    class agent_card_utils: pass
    class Message: pass
    class TextPart: pass
    class DataPart: pass
    class Artifact: pass
    class AgentCard: pass
    # Define TaskState as simple string constants
    class TaskState:
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"
        CANCELED = "CANCELED"
        UNKNOWN = "UNKNOWN"
        WORKING = "WORKING"
        SUBMITTED = "SUBMITTED"
    
    # Define helpers for state comparison
    TERMINAL_STATES = [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]
    
    def is_terminal_state(state):
        return state in TERMINAL_STATES
    class Task: pass
    class A2AEvent: pass
    class TaskStatusUpdateEvent: pass
    class TaskMessageEvent: pass
    class TaskArtifactUpdateEvent: pass
    class AgentVaultError(Exception): pass
    class A2AError(AgentVaultError): pass
    class A2AConnectionError(A2AError): pass
    class A2ARemoteAgentError(A2AError): 
        status_code=500
        response_body=""
    class A2ATimeoutError(A2AError): pass
    class A2AMessageError(A2AError): pass
    class AgentCardFetchError(AgentVaultError): pass
    class KeyManagementError(AgentVaultError): pass
    class TaskNotFoundError(A2AError): pass
    _AGENTVAULT_AVAILABLE = False

# Import config for this pipeline (defines local ConfigurationError)
# This import might fail if running this file standalone during dev without proper path setup
try:
    from .config import SecopsPipelineConfig, get_pipeline_config, ConfigurationError
except ImportError:
     logging.getLogger(__name__).warning("Could not import local config types for A2AClientWrapper.")
     class SecopsPipelineConfig: pass # type: ignore
     class ConfigurationError(Exception): pass # type: ignore

logger = logging.getLogger(__name__)
# Define local exception consistent with Dynamics POC
class AgentProcessingError(Exception): pass

# Define agent HRI keys expected in the SecOps config model
# These must match the keys used in SecopsPipelineConfig
SECOPS_AGENT_HRI_KEYS = [
    "alert_ingestor_agent", # Optional
    "enrichment_agent",
    "investigation_agent",
    "response_agent",
]

# --- Docker Service Name Mapping (Customize as needed) ---
# Maps localhost ports (from agent cards during local dev) to Docker service names
# This needs to be accurate for containerized runs.
AGENT_PORT_MAP = {
    "8070": "secops-alert-ingestor-agent",  # Example port assignment
    "8071": "secops-enrichment-agent",
    "8072": "secops-investigation-agent",
    "8073": "secops-response-agent",
    # Add MCP proxy if needed by any agents later
    # "8059": "mcp-tool-proxy-agent"
}

# --- Retry Strategy ---
RETRYABLE_EXCEPTIONS = (
    A2AConnectionError, A2ATimeoutError,
    httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout,
    # Retry on specific HTTP status codes indicating transient issues
    httpx.HTTPStatusError,
)
# Custom retry condition
def should_retry_exception(exception: BaseException) -> bool:
    if isinstance(exception, RETRYABLE_EXCEPTIONS):
        # Retry specific HTTPStatusErrors
        if isinstance(exception, httpx.HTTPStatusError):
            return exception.response.status_code in [429, 502, 503, 504]
        # Retry other network/timeout errors
        return True
    # Retry specific A2ARemoteAgentErrors if desired (e.g., rate limits)
    if isinstance(exception, A2ARemoteAgentError):
        # Example: retry on rate limit code or specific server errors
        return exception.status_code in [429, 503, -32099] # Adjust codes as needed
    return False

# Import this missing function from tenacity
from tenacity import retry_if_exception

retry_strategy = retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception(should_retry_exception), # Use custom function correctly
    before_sleep=before_sleep_log(logger, logging.WARNING)
)

class A2AClientWrapper:
    """Wraps AgentVaultClient for the SecOps pipeline, handling discovery and retries."""
    def __init__(self, config: SecopsPipelineConfig): # Config is now mandatory
        if not _AGENTVAULT_AVAILABLE:
            raise ConfigurationError("AgentVault core library is required but failed to import.")
        self.config = config
        self.registry_url = self.config.orchestration.registry_url
        if not self.registry_url:
             raise ConfigurationError("AgentVault Registry URL is required but not configured.")

        # Use AgentVaultClient for all operations
        self.client = AgentVaultClient(default_timeout=self.config.timeouts.agent_call_timeout)
        # Use default KeyManager, assuming config via env/keyring is handled externally
        self.key_manager = KeyManager(use_keyring=True)
        self.agent_cards: Dict[str, AgentCard] = {} # Cache for discovered agent cards
        self._is_initialized = False
        logger.info(f"A2AClientWrapper initialized for SecOps Pipeline. Registry: {self.registry_url}")

    async def initialize(self):
        """Discovers and caches agent cards for all required SecOps agents defined in config."""
        if self._is_initialized: return
        logger.info(f"Initializing A2AClientWrapper: Discovering SecOps agents from registry at {self.registry_url}...")
        self.agent_cards = {}
        discovered_count = 0

        # Get required HRIs from the loaded config
        required_hris: List[str] = []
        for key in SECOPS_AGENT_HRI_KEYS:
            agent_target_config = getattr(self.config, key, None)
            # Handle optional ingestor agent
            if key == "alert_ingestor_agent" and agent_target_config is None:
                 logger.info("Alert Ingestor Agent not configured, skipping discovery.")
                 continue
            # Check if the required agent config is present and valid
            if not agent_target_config or not hasattr(agent_target_config, 'hri'):
                 logger.error(f"Required agent configuration missing or invalid for key '{key}' in pipeline config.")
                 raise ConfigurationError(f"Missing or invalid agent configuration for '{key}'.")
            required_hris.append(agent_target_config.hri)

        if not required_hris:
             logger.warning("No required agent HRIs found in SecopsPipelineConfig to discover.")
             # Decide if this is an error or acceptable (e.g., if ingestor is optional and others aren't needed yet)
             # For now, let's allow it but log a warning.
             self._is_initialized = True
             return
             # raise ConfigurationError("No agent HRIs found in config to discover.")

        logger.debug(f"Required SecOps agent HRIs to discover: {required_hris}")

        # Discover agents concurrently
        discovery_tasks = {
             hri: self._discover_and_cache_agent(hri) for hri in required_hris
        }
        results = await asyncio.gather(*discovery_tasks.values(), return_exceptions=True)

        # Process results
        missing_agents = []
        for hri, result in zip(discovery_tasks.keys(), results):
            if isinstance(result, AgentCard):
                self.agent_cards[hri] = result
                discovered_count += 1
            else:
                logger.error(f"Failed to discover/cache agent '{hri}': {result}")
                missing_agents.append(hri)

        if missing_agents:
            logger.error(f"Could not discover all required SecOps agents. Missing: {missing_agents}")
            raise ConfigurationError(f"Failed to discover required SecOps agents: {', '.join(missing_agents)}")

        self._is_initialized = True
        logger.info(f"A2AClientWrapper init complete. Discovered {discovered_count} agent cards.")
        logger.info("--- AGENT CARD MAPPING ---")
        for hri, card in self.agent_cards.items(): logger.info(f"HRI: {hri} -> URL: {str(card.url)}")
        logger.info("-------------------------")

    async def _discover_and_cache_agent(self, agent_hri: str) -> AgentCard:
        """Helper function to discover a single agent with retries."""
        logger.debug(f"Discovering agent: {agent_hri}")
        # URL Encode the HRI in case it contains special characters like '/'
        encoded_hri = urllib.parse.quote(agent_hri, safe='')
        lookup_url = f"{str(self.registry_url).rstrip('/')}/api/v1/agent-cards/id/{encoded_hri}"

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), retry=retry_if_exception_type(httpx.RequestError))
        async def _fetch_card():
             async with httpx.AsyncClient() as http_client: # Use temporary client for discovery
                 logger.debug(f"Attempting lookup: {lookup_url}")
                 response = await http_client.get(lookup_url, follow_redirects=True, timeout=15.0)
                 if response.status_code == 404:
                     raise AgentCardFetchError(f"Agent card '{agent_hri}' not found at {lookup_url} (404).", status_code=404)
                 response.raise_for_status() # Raise for other errors (5xx etc)
                 return response.json()

        try:
            card_full_data = await _fetch_card()

            card_data_dict = card_full_data.get("card_data")
            if not card_data_dict or not isinstance(card_data_dict, dict):
                 raise AgentCardFetchError(f"Registry response for {agent_hri} missing 'card_data'.")

            # Validate the card data
            agent_card = AgentCard.model_validate(card_data_dict)

            # --- URL Replacement Logic ---
            url_str = str(agent_card.url); original_url_str = url_str
            url_updated = False
            for port, service_name in AGENT_PORT_MAP.items():
                pattern = rf"(https?://)(?:localhost|127\.0\.0\.1):{port}(/.*)?"
                replacement = rf"\1{service_name}:{port}\2"
                new_url, count = re.subn(pattern, replacement, url_str)
                if count > 0:
                    agent_card.url = pydantic.AnyUrl(new_url) # Re-validate after replacement
                    url_updated = True
                    logger.info(f"Replaced localhost URL for HRI {agent_hri}: {original_url_str} -> {new_url}")
                    break # Stop after first match
            if not url_updated: logger.debug(f"No localhost URL replacement needed for HRI {agent_hri}: {original_url_str}")
            # --- End URL Replacement ---

            return agent_card # Return the validated and potentially updated card

        except Exception as e:
            logger.error(f"Failed to discover/process agent card '{agent_hri}': {e}", exc_info=True)
            raise # Re-raise the exception to be caught by asyncio.gather

    async def close(self):
        """Closes the underlying AgentVaultClient."""
        if self.client and hasattr(self.client, 'close'):
            await self.client.close()
        logger.info("A2AClientWrapper closed.")

    @retry_strategy
    async def _initiate_task_with_retry(self, agent_card: AgentCard, message: Message) -> str:
        """Internal helper to initiate task with retries using AgentVaultClient."""
        logger.debug(f"Initiating task on {agent_card.human_readable_id}...")
        return await self.client.initiate_task(agent_card, message, self.key_manager)

    @retry_strategy
    async def _get_task_status_with_retry(self, agent_card: AgentCard, task_id: str) -> Task:
        """Internal helper to get task status with retries using AgentVaultClient."""
        logger.debug(f"Getting task status for {task_id} from {agent_card.human_readable_id}...")
        return await self.client.get_task_status(agent_card, task_id, self.key_manager)

    async def _try_sse_subscription(self, agent_card: AgentCard, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        """Tries to subscribe to SSE events with retries for initial 'Task not found' errors."""
        event_method = getattr(self.client, "receive_messages", None)
        if not event_method or not callable(event_method):
            raise AttributeError("AgentVaultClient missing 'receive_messages' method.")

        max_attempts = 3
        retry_delay = 5.0 # seconds
        attempt = 0
        last_error: Optional[Exception] = None

        while attempt < max_attempts:
            attempt += 1
            logger.info(f"Attempting SSE subscription for task {task_id} on {agent_card.human_readable_id} (attempt {attempt}/{max_attempts})")
            try:
                # Yield from the client's receive_messages generator
                async for event in event_method(agent_card=agent_card, task_id=task_id, key_manager=self.key_manager):
                    logger.debug(f"SSE Event type: {type(event).__name__} received for task {task_id}")
                    yield event
                # If the loop finishes without error, the stream ended gracefully
                logger.info(f"SSE stream for task {task_id} ended gracefully.")
                return # Exit the generator

            except TaskNotFoundError as e:
                last_error = e
                if attempt < max_attempts:
                    logger.warning(f"Task {task_id} not found during SSE attempt {attempt}, likely still initializing. Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    continue # Go to next attempt
                else:
                    logger.error(f"Task {task_id} still not found after {max_attempts} SSE attempts.")
                    raise # Re-raise the TaskNotFoundError after final attempt
            except A2AError as e:
                # Catch other specific A2A errors that might occur during streaming
                last_error = e
                logger.error(f"A2AError during SSE stream for task {task_id}: {e}")
                raise # Re-raise non-retryable A2A errors immediately
            except Exception as e:
                last_error = e
                # Handle generic exceptions (e.g., connection closed by peer)
                if "client disconnected" in str(e).lower() or isinstance(e, (asyncio.CancelledError, type(asyncio.CancelledError))):
                    logger.info(f"SSE stream for task {task_id} cancelled or client disconnected.")
                    return # Treat as graceful end
                else:
                    logger.error(f"Unexpected error during SSE stream for task {task_id}: {e}", exc_info=True)
                    raise # Re-raise unexpected errors

        # If loop finishes due to exhausted retries for TaskNotFound
        logger.error(f"Failed to establish SSE stream after {max_attempts} attempts due to TaskNotFound for task {task_id}.")
        raise last_error if last_error else A2AError(f"SSE Failed after retries for {task_id}")


    async def run_a2a_task(self, agent_hri: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs a task on a specified agent, streams SSE events, polls for final
        status, and returns the content of the final assistant DataPart message.

        Handles discovery, authentication, SSE streaming with timeout/retries,
        and final status polling. Raises AgentProcessingError on failure.
        """
        if not self._is_initialized: await self.initialize()
        if agent_hri not in self.agent_cards: raise ConfigurationError(f"Agent card '{agent_hri}' not loaded during init.")
        agent_card = self.agent_cards[agent_hri]
        logger.info(f"Running task on agent: {agent_hri} ({agent_card.name}) at {agent_card.url}")

        try:
            # Assume input payload is directly usable in a DataPart
            initial_message = Message(role="user", parts=[DataPart(content=input_payload)])
        except Exception as e:
            raise AgentProcessingError(f"Cannot create initial message for {agent_hri}: {e}") from e

        task_id: Optional[str] = None
        try:
            # Initiate task with retry logic handled by the helper
            task_id = await self._initiate_task_with_retry(agent_card, initial_message)
            logger.info(f"Task {task_id} initiated on {agent_hri}.")
        except RetryError as e: # Catch tenacity specific error
            logger.error(f"Failed to initiate task on {agent_hri} after multiple retries: {e.last_attempt.exception()}", exc_info=True)
            raise AgentProcessingError(f"A2A Error initiating task on {agent_hri}: {e.last_attempt.exception()}") from e.last_attempt.exception()
        except Exception as e:
            logger.error(f"Failed to initiate task on {agent_hri}: {e}", exc_info=True)
            raise AgentProcessingError(f"Unexpected error initiating task on {agent_hri}: {e}") from e

        final_state_val: Optional[TaskState] = None
        final_result_content: Optional[Dict[str, Any]] = None
        final_error_message: Optional[str] = None
        sse_error: Optional[Exception] = None
        sse_processed_message = False # Track if result was received via SSE
        sse_timeout_seconds = self.config.timeouts.sse_stream_timeout

        try:
            # --- SSE Streaming with Timeout ---
            logger.info(f"Starting SSE streaming for task {task_id} on {agent_hri} with {sse_timeout_seconds}s timeout...")
            start_time = asyncio.get_event_loop().time()

            async for event in self._try_sse_subscription(agent_card, task_id):
                 # Check for overall timeout within the loop
                 if asyncio.get_event_loop().time() - start_time > sse_timeout_seconds:
                     logger.warning(f"SSE stream timeout reached ({sse_timeout_seconds}s) for task {task_id}.")
                     sse_error = asyncio.TimeoutError("SSE stream timeout")
                     break # Exit the event processing loop

                 # Process different event types
                 if isinstance(event, TaskStatusUpdateEvent):
                     final_state_val = event.state
                     if event.state == TaskState.FAILED and event.message:
                         final_error_message = event.message # Capture error message from status
                     logger.info(f"Task {task_id} status update via SSE: {final_state_val}")
                     if final_state_val is not None and hasattr(final_state_val, 'is_terminal') and final_state_val.is_terminal():
                         logger.info(f"Task {task_id} reached terminal state ({final_state_val}) via SSE.")
                         break # Stop processing SSE on terminal state

                 elif isinstance(event, TaskMessageEvent):
                     if event.message.role == "assistant" and event.message.parts:
                         # Look for the DataPart containing the result
                         parts_list = event.message.parts if isinstance(event.message.parts, list) else [event.message.parts]
                         for part in parts_list:
                             if isinstance(part, DataPart) and isinstance(part.content, dict):
                                 final_result_content = part.content
                                 sse_processed_message = True # Mark as received
                                 logger.info(f"Received result data via SSE for task {task_id}")
                                 break # Assume only one DataPart result per message
                 # Add handling for TaskArtifactUpdateEvent if needed

            logger.info(f"SSE streaming loop finished or timed out for task {task_id}.")

        except asyncio.TimeoutError as e: # Catch timeout if _try_sse_subscription raises it somehow
             logger.warning(f"SSE stream wait timed out externally after {sse_timeout_seconds}s for task {task_id}.")
             sse_error = e
        except A2AError as e: # Catch errors re-raised by _try_sse_subscription
             logger.error(f"A2AError during SSE stream processing for task {task_id}: {e}")
             sse_error = e
        except Exception as e:
             logger.error(f"Unexpected error during SSE generation/processing for task {task_id}: {e}", exc_info=True)
             sse_error = e

        # --- Final Status Poll ---
        # Always poll unless SSE *definitively* completed the task AND gave us the result.
        if final_state_val is None or not final_state_val.is_terminal() or not sse_processed_message:
            logger.info(f"Polling for final status/result for task {task_id} on {agent_hri} (SSE State: {final_state_val}, SSE Msg Received: {sse_processed_message}).")
            polled_task_status: Optional[Task] = None
            try:
                polled_task_status = await self._get_task_status_with_retry(agent_card, task_id)
                final_state_val = polled_task_status.state # Update state from poll
                logger.info(f"Final polled status for task {task_id}: {final_state_val}")

                # Extract result from polled messages ONLY if not already received via SSE
                if not sse_processed_message and polled_task_status.messages:
                    logger.debug(f"Attempting to extract result from polled messages for task {task_id}...")
                    assistant_msgs = [m for m in polled_task_status.messages if m.role == 'assistant' and m.parts]
                    if assistant_msgs:
                        for msg in reversed(assistant_msgs):
                            parts_list = msg.parts if isinstance(msg.parts, list) else [msg.parts]
                            for part in parts_list:
                                if isinstance(part, DataPart) and isinstance(part.content, dict):
                                    final_result_content = part.content; logger.info(f"Extracted result data from final poll for {task_id}."); break
                            if final_result_content: break
                        if not final_result_content: logger.warning(f"No DataPart found in polled assistant messages for {task_id}.")
                    else: logger.warning(f"No assistant messages in final polled status for {task_id}.")

                # Extract error message if task failed and we didn't get one from SSE
                if final_state_val == TaskState.FAILED and not final_error_message:
                    # More careful error message extraction to handle None values
                    metadata_dict = {}
                    if hasattr(polled_task_status, 'metadata') and polled_task_status.metadata is not None:
                        if isinstance(polled_task_status.metadata, dict):
                            metadata_dict = polled_task_status.metadata
                    
                    polled_error_message = metadata_dict.get('error_message') or f"Task {task_id} failed (polled)"
                    final_error_message = polled_error_message
                    logger.info(f"Extracted failure message from polled status for task {task_id}: {final_error_message}")

            except TaskNotFoundError:
                logger.error(f"CRITICAL: Task {task_id} not found during final poll on {agent_hri}.")
                if final_state_val is None or not (hasattr(final_state_val, 'is_terminal') and final_state_val.is_terminal()):
                    raise AgentProcessingError(f"Task {task_id} disappeared before completion or final poll.")
                logger.warning(f"Task {task_id} reported terminal state {final_state_val} via SSE, but poll failed (TaskNotFound). Trusting SSE state.")
            except RetryError as e:
                logger.error(f"Final poll failed for task {task_id} after multiple retries: {e.last_attempt.exception()}", exc_info=True)
                if final_state_val is None: raise AgentProcessingError(f"SSE failed AND final poll failed for task {task_id}: {e.last_attempt.exception()}") from e.last_attempt.exception()
                logger.warning(f"Final poll failed for task {task_id}, relying on state from SSE: {final_state_val}")
            except Exception as poll_err:
                logger.error(f"Error during final poll for task {task_id}: {poll_err}", exc_info=True)
                if final_state_val is None: raise AgentProcessingError(f"SSE failed AND final poll failed for task {task_id}: {poll_err}") from poll_err
                logger.warning(f"Final poll failed for task {task_id}, relying on state from SSE: {final_state_val}")
        else:
             logger.info(f"Skipping final poll for task {task_id} as SSE reported terminal state '{final_state_val}' and result was received.")


        # --- Final Check and Return ---
        if final_state_val != TaskState.COMPLETED:
            error_msg = f"Task {task_id} on {agent_hri} did not complete successfully. Final State: {final_state_val}."
            if final_error_message: error_msg += f" Message: {final_error_message}"
            elif sse_error: error_msg += f" Error during SSE: {sse_error}"
            logger.error(error_msg)
            raise AgentProcessingError(error_msg)

        if not final_result_content:
            logger.warning(f"Task {task_id} ({agent_hri}) completed but no result data found in DataPart.")
            return {}  # Return empty dict if no result

        logger.info(f"Task {task_id} ({agent_hri}) completed successfully. Returning result data.")
        # Ensure result is a dict before returning
        return final_result_content if isinstance(final_result_content, dict) else {"raw_result": final_result_content}

logger.info("A2AClientWrapper for SecOps pipeline defined.")
