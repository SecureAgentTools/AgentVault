# A2A Client Wrapper for the MCP Test Pipeline

import asyncio
import json
import logging
import uuid
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, AsyncGenerator, List

import httpx
import pydantic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

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
    _AGENTVAULT_AVAILABLE = True
except ImportError as e:
    logging.getLogger(__name__).critical(f"Failed import 'agentvault': {e}. Wrapper using placeholders.")
    # Define placeholders
    class AgentVaultClient: pass # type: ignore
    class KeyManager: pass # type: ignore
    class agent_card_utils: pass # type: ignore
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class DataPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class AgentCard: pass # type: ignore
    class TaskState:
        SUBMITTED = "SUBMITTED"; WORKING = "WORKING"; INPUT_REQUIRED = "INPUT_REQUIRED"
        COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELED = "CANCELED"
    class Task: pass # type: ignore
    class A2AEvent: pass # type: ignore
    class TaskStatusUpdateEvent: pass # type: ignore
    class TaskMessageEvent: pass # type: ignore
    class TaskArtifactUpdateEvent: pass # type: ignore
    class AgentVaultError(Exception): pass # type: ignore
    class A2AError(AgentVaultError): pass # type: ignore
    class A2AConnectionError(A2AError): pass # type: ignore
    class A2ARemoteAgentError(A2AError): pass # type: ignore
    class A2ATimeoutError(A2AError): pass # type: ignore
    class A2AMessageError(A2AError): pass # type: ignore
    class AgentCardFetchError(AgentVaultError): pass # type: ignore
    class KeyManagementError(AgentVaultError): pass # type: ignore
    class TaskNotFoundError(A2AError): pass # type: ignore
    _AGENTVAULT_AVAILABLE = False # type: ignore

TaskStateEnum = TaskState if _AGENTVAULT_AVAILABLE else None

# Import config for this pipeline (defines local ConfigurationError)
from .config import McpTestPipelineConfig, get_pipeline_config, ConfigurationError

logger = logging.getLogger(__name__)
class AgentProcessingError(Exception): pass

# MCP test pipeline only needs the proxy agent
MCP_AGENT_HRIS = ["local-poc/mcp-tool-proxy"]

AGENT_PORT_MAP = {
    "8059": "mcp-tool-proxy-agent"
}

RETRYABLE_EXCEPTIONS = (A2AConnectionError, A2ATimeoutError, httpx.ConnectError, httpx.ReadTimeout)
retry_strategy = retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS), before_sleep=before_sleep_log(logger, logging.WARNING))

class A2AClientWrapper:
    """Wraps AgentVaultClient for the MCP test pipeline."""
    def __init__(self, config: Optional[McpTestPipelineConfig] = None):
        if not _AGENTVAULT_AVAILABLE: raise ConfigurationError("AgentVault library required.")
        self.config = config or get_pipeline_config()
        self.registry_url = self.config.orchestration.registry_url
        # Use AgentVaultClient for all operations including SSE
        self.client = AgentVaultClient()
        self.key_manager = KeyManager()
        self.agent_cards: Dict[str, AgentCard] = {}
        self._is_initialized = False
        logger.info(f"A2AClientWrapper initialized for MCP Test Pipeline. Registry: {self.registry_url}")

    async def initialize(self):
        if self._is_initialized: return
        logger.info(f"Initializing A2AClientWrapper: Discovering MCP proxy agent from registry at {self.registry_url}...")
        self.agent_cards = {}; discovered_count = 0
        required_hris = [self.config.mcp_tool_proxy_agent.hri]
        
        async with httpx.AsyncClient() as http_client: # Use a temporary client for discovery
            for agent_hri in required_hris:
                logger.debug(f"Discovering agent: {agent_hri}")
                encoded_hri = urllib.parse.quote(agent_hri, safe='')
                lookup_url = f"{self.registry_url.rstrip('/')}/api/v1/agent-cards/id/{encoded_hri}"
                try:
                    response = await http_client.get(lookup_url, follow_redirects=True, timeout=15.0)
                    if response.status_code == 404: logger.error(f"Agent card '{agent_hri}' not found at {lookup_url}."); continue
                    response.raise_for_status()
                    card_full_data = response.json(); card_data_dict = card_full_data.get("card_data")
                    if not card_data_dict: raise AgentCardFetchError(f"Registry response for {agent_hri} missing 'card_data'.")
                    agent_card = AgentCard.model_validate(card_data_dict)
                    url_str = str(agent_card.url); original_url_str = url_str
                    for port, service_name in AGENT_PORT_MAP.items():
                        if f"localhost:{port}" in url_str:
                            new_url = url_str.replace(f"localhost:{port}", f"{service_name}:{port}")
                            agent_card.url = pydantic.HttpUrl(new_url) # Ensure it's HttpUrl type
                            logger.info(f"Replaced URL for HRI {agent_hri}: {original_url_str} -> {new_url}"); break
                    self.agent_cards[agent_hri] = agent_card; logger.info(f"Discovered card for agent: {agent_hri} at {agent_card.url}"); discovered_count += 1
                except Exception as e: logger.error(f"Error discovering agent '{agent_hri}': {e}", exc_info=True)
        missing = set(required_hris) - set(self.agent_cards.keys())
        if missing: raise ConfigurationError(f"Could not discover MCP proxy agent. Missing: {missing}")
        self._is_initialized = True; logger.info(f"A2AClientWrapper init complete. Discovered {discovered_count} cards.")
        logger.info("--- AGENT CARD MAPPING ---"); [logger.info(f"HRI: {hri} -> URL: {str(card.url)}") for hri, card in self.agent_cards.items()]; logger.info("-------------------------")

    async def close(self):
        await self.client.close() # Close AV client
        logger.info("A2AClientWrapper closed.")

    @retry_strategy
    async def _initiate_task_with_retry(self, agent_card: AgentCard, message: Message) -> str:
        # Use the AV client for this standard method
        return await self.client.initiate_task(agent_card, message, self.key_manager)

    @retry_strategy
    async def _get_task_status_with_retry(self, agent_card: AgentCard, task_id: str) -> Task:
        # Use the AV client for this standard method
        return await self.client.get_task_status(agent_card, task_id, self.key_manager)

    async def _try_sse_subscription(self, agent_card: AgentCard, task_id: str, key_manager: KeyManager, max_attempts: int = 3, retry_delay: float = 5.0) -> AsyncGenerator[A2AEvent, None]:
        """Get SSE events for a task using the agentvault client's receive_messages method."""
        event_method = getattr(self.client, "receive_messages", None)
        if not event_method: raise AttributeError("'receive_messages' method not found")

        attempt = 0
        last_error = None

        while attempt < max_attempts:
            attempt += 1
            logger.info(f"Attempting SSE subscription for task {task_id} (attempt {attempt}/{max_attempts})")
            try:
                async for event in event_method(agent_card, task_id, key_manager):
                    logger.debug(f"SSE Event type: {type(event).__name__} for task {task_id}")
                    yield event
                # If the loop finishes without error, return (stream ended gracefully)
                logger.info(f"SSE stream for task {task_id} ended gracefully.")
                return
            except Exception as e:
                last_error = e
                error_text = str(e).lower()
                # Check for specific retryable errors (like task not found initially)
                if "task not found" in error_text and attempt < max_attempts:
                    logger.info(f"Task {task_id} not found yet during SSE attempt, retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    continue
                # Check for client disconnection or other non-retryable errors
                elif "client disconnected" in error_text or isinstance(e, asyncio.CancelledError):
                    logger.info(f"SSE stream for task {task_id} cancelled or client disconnected.")
                    return # Treat as graceful end from client perspective
                else:
                    logger.error(f"Non-retryable SSE subscription error for task {task_id}: {e}")
                    raise # Re-raise other errors

        # If we reach here, we've exhausted all retry attempts for retryable errors
        logger.error(f"Failed to establish SSE stream after {max_attempts} attempts for task {task_id}.")
        raise last_error if last_error else A2AError("Failed to establish SSE stream after multiple attempts.")

    async def run_a2a_task(self, agent_hri: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Runs task, waits, returns agent's RESULT message content (expected dict)."""
        if not self._is_initialized: await self.initialize()
        if agent_hri not in self.agent_cards: raise ConfigurationError(f"Agent card '{agent_hri}' not loaded.")
        agent_card = self.agent_cards[agent_hri]
        logger.info(f"Running task on agent: {agent_hri} ({agent_card.name})")
        try: initial_message = Message(role="user", parts=[DataPart(content=input_payload)])
        except Exception as e: raise AgentProcessingError(f"Cannot create initial message for {agent_hri}") from e

        task_id: Optional[str] = None
        try:
            task_id = await self._initiate_task_with_retry(agent_card, initial_message)
            logger.info(f"Task {task_id} initiated on {agent_hri}.")
            # Add a small delay *after* initiation before trying SSE
            await asyncio.sleep(1.0)
        except A2AError as e: raise AgentProcessingError(f"A2A Error initiating task on {agent_hri}: {e}") from e
        except Exception as e: raise AgentProcessingError(f"Unexpected error initiating task on {agent_hri}: {e}") from e

        final_state_val: Optional[Any] = None
        final_result_content: Optional[Dict[str, Any]] = None
        final_message_text: Optional[str] = None
        sse_error = None
        sse_timeout_seconds = self.config.timeouts.sse_stream_timeout or 60.0 # Use configured timeout
        sse_processed_message = False # Flag to track if message was received via SSE

        try: # SSE Stream processing with timeout
            logger.info(f"Starting SSE streaming for task {task_id} on {agent_hri} with {sse_timeout_seconds}s timeout...")

            async def process_sse_events():
                nonlocal final_state_val, final_message_text, final_result_content, sse_processed_message
                # Add a small delay to allow agent processing to start
                await asyncio.sleep(0.5)
                logger.info(f"Starting SSE event processing for task {task_id}")

                async for event in self._try_sse_subscription(agent_card, task_id, self.key_manager):
                    if isinstance(event, TaskStatusUpdateEvent):
                        final_state_val = event.state
                        final_message_text = event.message # Capture potential error message from status
                        logger.info(f"Task {task_id} status update via SSE: {final_state_val}")
                        # Don't break here anymore, let stream continue or timeout
                    elif isinstance(event, TaskMessageEvent):
                        if event.message.role == "assistant" and event.message.parts:
                            # Ensure parts is treated as a list even if single element
                            parts_list = event.message.parts if isinstance(event.message.parts, list) else [event.message.parts]
                            for part in parts_list:
                                if isinstance(part, DataPart) and isinstance(part.content, dict):
                                    final_result_content = part.content
                                    sse_processed_message = True # Mark that we got the message via SSE
                                    logger.info(f"Received result data via SSE for task {task_id}")
                                    # Don't break inner loop, process all parts if multiple
                                elif isinstance(part, TextPart):
                                    logger.debug(f"Task {task_id} text message via SSE: {part.content[:100]}...")

            try:
                await asyncio.wait_for(process_sse_events(), timeout=sse_timeout_seconds)
                logger.info(f"SSE processing finished for {task_id} (either completed or timed out).")
            except asyncio.TimeoutError:
                logger.warning(f"SSE stream explicitly timed out after {sse_timeout_seconds}s for task {task_id}. Will proceed to final poll.")
                sse_error = "SSE stream timeout"
            except A2AError as sse_a2a_err: # Catch errors from _try_sse_subscription
                 logger.error(f"A2AError during SSE stream for task {task_id}: {sse_a2a_err}")
                 sse_error = sse_a2a_err # Store the error but continue to polling
            except Exception as sse_err:
                logger.error(f"Unexpected error during SSE stream processing for task {task_id}: {sse_err}", exc_info=True)
                sse_error = sse_err # Store the error but continue to polling

            await asyncio.sleep(0.5) # Short delay after SSE attempt finishes

        except Exception as outer_sse_err: # Catch errors setting up the SSE processing
            logger.error(f"Outer error during SSE setup/processing for task {task_id}: {outer_sse_err}", exc_info=True)
            sse_error = outer_sse_err

        # --- Final Poll for Status and Results ---
        logger.info(f"Performing final status poll for task {task_id} on {agent_hri}.")
        try:
            final_task_status: Task = await self._get_task_status_with_retry(agent_card, task_id)
            final_state_val = final_task_status.state
            logger.info(f"Final polled status for task {task_id}: {final_state_val}")

            # Extract result from messages if not already received via SSE
            if not sse_processed_message and final_task_status.messages:
                logger.info(f"Attempting to extract result from polled messages for task {task_id}...")
                assistant_msgs = [m for m in final_task_status.messages if m.role == 'assistant' and m.parts]
                if assistant_msgs:
                    # Find the last message with a DataPart
                    for msg in reversed(assistant_msgs):
                         # Ensure parts is treated as a list even if single element
                         parts_list = msg.parts if isinstance(msg.parts, list) else [msg.parts]
                         for part in parts_list:
                             if isinstance(part, DataPart) and isinstance(part.content, dict):
                                 final_result_content = part.content
                                 logger.info(f"Extracted result data from final polled status for task {task_id}.")
                                 break # Found the data part in this message
                         if final_result_content: break # Found data part in the outer loop
                    if not final_result_content:
                         logger.warning(f"Found assistant messages for task {task_id}, but none contained the expected DataPart dict.")
                else:
                     logger.warning(f"No assistant messages found in final polled status for task {task_id}.")

            # Update final message text if task failed and we didn't get it from SSE status
            is_failed_poll = False
            if TaskStateEnum: is_failed_poll = final_state_val == TaskStateEnum.FAILED
            elif isinstance(final_state_val, str): is_failed_poll = final_state_val == "FAILED"

            if is_failed_poll and not final_message_text:
                 # Try to get a more specific error message from the Task object if available
                 polled_error_message = getattr(final_task_status, 'message', None) or getattr(final_task_status, 'status_message', 'Task failed (polled)')
                 final_message_text = polled_error_message
                 logger.info(f"Extracted failure message from polled status for task {task_id}: {final_message_text}")

        except Exception as e:
            if isinstance(e, TaskNotFoundError):
                logger.error(f"CRITICAL: Task {task_id} not found during final poll on {agent_hri}. This should not happen.")
                raise AgentProcessingError(f"Task {task_id} disappeared before final poll.")
            elif isinstance(e, A2AError):
                logger.error(f"A2A Error during final poll for task {task_id}: {e}")
                # If polling fails, we rely on whatever state we got from SSE (if any)
                if final_state_val is None: # If SSE also failed badly
                    raise AgentProcessingError(f"SSE failed and final poll failed for task {task_id}: {e}") from e
            else:
                logger.exception(f"Unexpected error during final poll for task {task_id}: {e}")
                if final_state_val is None:
                    raise AgentProcessingError(f"SSE failed and unexpected final poll error for task {task_id}: {e}") from e

        # --- Final Check on Completion Status ---
        is_complete = False
        if TaskStateEnum: is_complete = final_state_val == TaskStateEnum.COMPLETED
        elif isinstance(final_state_val, str): is_complete = final_state_val == "COMPLETED"

        if not is_complete:
            error_msg = f"Task {task_id} on {agent_hri} did not complete successfully. Final State: {final_state_val}. Message: {final_message_text}"
            logger.error(error_msg)
            # Include SSE error if relevant
            if sse_error: error_msg += f" (SSE Error: {sse_error})"
            raise AgentProcessingError(error_msg)

        if not final_result_content:
            logger.warning(f"Task {task_id} ({agent_hri}) completed but no result data found after SSE and final poll.")
            return {}  # Return empty dict if no result

        logger.info(f"Task {task_id} ({agent_hri}) completed successfully. Returning result data.")
        return final_result_content
