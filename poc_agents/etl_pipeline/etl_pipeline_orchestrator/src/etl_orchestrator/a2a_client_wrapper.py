# Adapting A2AClientWrapper for the ETL Pipeline
# Corrected Version 2

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
    # CORRECTED: Removed import of non-existent AgentVaultConfigurationError
    from agentvault.exceptions import (
        AgentVaultError, A2AError, A2AConnectionError, A2ARemoteAgentError,
        A2ATimeoutError, A2AMessageError, AgentCardFetchError, KeyManagementError
    )
    _AGENTVAULT_AVAILABLE = True
except ImportError as e:
    logging.getLogger(__name__).critical(f"Failed to import core 'agentvault' library: {e}. A2AClientWrapper using placeholders.")
    # Define placeholders on separate lines
    class AgentVaultClient: pass
    class KeyManager: pass
    class agent_card_utils: pass
    class Message: pass
    class TextPart: pass
    class DataPart: pass
    class Artifact: pass
    class AgentCard: pass
    class TaskState: # Define TaskState placeholder
        SUBMITTED = "SUBMITTED"; WORKING = "WORKING"; INPUT_REQUIRED = "INPUT_REQUIRED"
        COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELED = "CANCELED"
    class Task: pass
    class A2AEvent: pass
    class TaskStatusUpdateEvent: pass
    class TaskMessageEvent: pass
    class TaskArtifactUpdateEvent: pass
    class AgentVaultError(Exception): pass
    class A2AError(AgentVaultError): pass
    class A2AConnectionError(A2AError): pass
    class A2ARemoteAgentError(A2AError): pass
    class A2ATimeoutError(A2AError): pass
    class A2AMessageError(A2AError): pass
    # AgentVaultConfigurationError is NOT defined here as it wasn't imported
    class AgentCardFetchError(AgentVaultError): pass
    class KeyManagementError(AgentVaultError): pass
    _AGENTVAULT_AVAILABLE = False # type: ignore

# Use the imported or placeholder TaskState consistently
TaskStateEnum = TaskState if _AGENTVAULT_AVAILABLE else None

# Import config for this pipeline (defines local ConfigurationError)
from .config import EtlPipelineConfig, get_pipeline_config, ConfigurationError

logger = logging.getLogger(__name__)

class AgentProcessingError(Exception): pass

ETL_AGENT_HRIS = [
    "local-poc/etl-data-extractor", "local-poc/etl-data-transformer",
    "local-poc/etl-data-validator", "local-poc/etl-data-loader"
]
AGENT_PORT_MAP = {
    "8040": "data-extractor-agent", "8041": "data-transformer-agent",
    "8042": "data-validator-agent", "8043": "data-loader-agent"
}
RETRYABLE_EXCEPTIONS = (A2AConnectionError, A2ATimeoutError)
retry_strategy = retry(
    stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS), before_sleep=before_sleep_log(logger, logging.WARNING)
)

class A2AClientWrapper:
    """Wraps AgentVaultClient for the ETL pipeline."""
    def __init__(self, config: Optional[EtlPipelineConfig] = None):
        if not _AGENTVAULT_AVAILABLE: raise ConfigurationError("AgentVault library required.")
        self.config = config or get_pipeline_config()
        self.registry_url = self.config.orchestration.registry_url
        self.client = AgentVaultClient()
        self.key_manager = KeyManager()
        self.agent_cards: Dict[str, AgentCard] = {}
        self._is_initialized = False
        logger.info(f"A2AClientWrapper initialized for ETL Pipeline. Registry: {self.registry_url}")

    async def initialize(self):
        if self._is_initialized: return
        logger.info(f"Initializing A2AClientWrapper: Discovering ETL agents from registry at {self.registry_url}...")
        self.agent_cards = {}
        discovered_count = 0
        required_hris = [
            self.config.extractor_agent.hri, self.config.transformer_agent.hri,
            self.config.validator_agent.hri, self.config.loader_agent.hri
        ]
        async with httpx.AsyncClient() as http_client:
            for agent_hri in required_hris:
                logger.debug(f"Discovering agent: {agent_hri}")
                encoded_hri = urllib.parse.quote(agent_hri, safe='')
                lookup_url = f"{self.registry_url.rstrip('/')}/api/v1/agent-cards/id/{encoded_hri}"
                try:
                    response = await http_client.get(lookup_url, follow_redirects=True, timeout=15.0)
                    if response.status_code == 404: logger.error(f"Agent card '{agent_hri}' not found at {lookup_url}."); continue
                    response.raise_for_status()
                    card_full_data = response.json()
                    card_data_dict = card_full_data.get("card_data")
                    if not card_data_dict: raise AgentCardFetchError(f"Registry response for {agent_hri} missing 'card_data'.")
                    agent_card = AgentCard.model_validate(card_data_dict)
                    url_str = str(agent_card.url); original_url_str = url_str
                    for port, service_name in AGENT_PORT_MAP.items():
                        if f"localhost:{port}" in url_str:
                            new_url = url_str.replace(f"localhost:{port}", f"{service_name}:{port}")
                            agent_card.url = new_url; logger.info(f"Replaced URL for HRI {agent_hri}: {original_url_str} -> {new_url}"); break
                    self.agent_cards[agent_hri] = agent_card; logger.info(f"Discovered card for agent: {agent_hri} at {agent_card.url}"); discovered_count += 1
                except Exception as e: logger.error(f"Error discovering agent '{agent_hri}': {e}", exc_info=True)
        missing = set(required_hris) - set(self.agent_cards.keys())
        if missing: raise ConfigurationError(f"Could not discover all ETL agents. Missing: {missing}") # Use local ConfigurationError
        self._is_initialized = True; logger.info(f"A2AClientWrapper init complete. Discovered {discovered_count} cards.")
        logger.info("--- AGENT CARD MAPPING ---"); [logger.info(f"HRI: {hri} -> URL: {str(card.url)}") for hri, card in self.agent_cards.items()]; logger.info("-------------------------")

    async def close(self): logger.info("A2AClientWrapper closed.")

    @retry_strategy
    async def _initiate_task_with_retry(self, agent_card: AgentCard, message: Message) -> str:
        return await self.client.initiate_task(agent_card, message, self.key_manager)

    @retry_strategy
    async def _get_task_status_with_retry(self, agent_card: AgentCard, task_id: str) -> Task:
        return await self.client.get_task_status(agent_card, task_id, self.key_manager)

    async def _try_sse_subscription(self, agent_card: AgentCard, task_id: str, key_manager: KeyManager, max_attempts: int = 3, retry_delay: float = 5.0) -> AsyncGenerator[A2AEvent, None]:
        event_method = getattr(self.client, "receive_messages", None)
        if not event_method: raise AttributeError("'receive_messages' method not found")
        attempt = 0; last_error = None
        while attempt < max_attempts:
            attempt += 1
            try:
                async for event in event_method(agent_card, task_id, key_manager): yield event
                return
            except Exception as e:
                last_error = e; error_text = str(e).lower()
                if "task not found" in error_text:
                    if attempt < max_attempts: await asyncio.sleep(retry_delay)
                    else: raise
                else: raise
        raise last_error # type: ignore

    async def run_a2a_task(self, agent_hri: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Runs task, waits for completion, returns agent's RESULT message content."""
        if not self._is_initialized: await self.initialize()
        if agent_hri not in self.agent_cards: raise ConfigurationError(f"Agent card '{agent_hri}' not loaded.")
        agent_card = self.agent_cards[agent_hri]
        logger.info(f"Running task on agent: {agent_hri} ({agent_card.name})")
        try: initial_message = Message(role="user", parts=[DataPart(content=input_payload)])
        except Exception as e: raise AgentProcessingError(f"Cannot create initial message for {agent_hri}") from e

        task_id: Optional[str] = None
        try: task_id = await self._initiate_task_with_retry(agent_card, initial_message); logger.info(f"Task {task_id} initiated on {agent_hri}.")
        except A2AError as e: raise AgentProcessingError(f"A2A Error initiating task on {agent_hri}: {e}") from e
        except Exception as e: raise AgentProcessingError(f"Unexpected error initiating task on {agent_hri}: {e}") from e

        final_state_val: Optional[Any] = None # Use Any for state if enum not available
        final_result_content: Optional[Dict[str, Any]] = None; final_message_text: Optional[str] = None; sse_error = None

        try: # SSE Stream processing
            logger.info(f"Starting SSE streaming for task {task_id} on {agent_hri}...")
            async for event in self._try_sse_subscription(agent_card, task_id, self.key_manager):
                logger.debug(f"SSE Event ({agent_hri}/{task_id}): Type={type(event).__name__}")
                if isinstance(event, TaskStatusUpdateEvent):
                    final_state_val = event.state; final_message_text = event.message; logger.info(f"Task {task_id} status update: {final_state_val}")
                    # Check against terminal states (handle both Enum and string)
                    is_terminal = False
                    if TaskStateEnum: is_terminal = final_state_val in [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
                    elif isinstance(final_state_val, str): is_terminal = final_state_val in ["COMPLETED", "FAILED", "CANCELED"]
                    if is_terminal: break
                elif isinstance(event, TaskMessageEvent):
                     if event.message.role == "assistant" and event.message.parts:
                         part = event.message.parts[0]
                         if isinstance(part, DataPart) and isinstance(part.content, dict): final_result_content = part.content; logger.info(f"Received result data via SSE for task {task_id}")
                         elif isinstance(part, TextPart): logger.debug(f"Task {task_id} text message: {part.content[:100]}...")
        except Exception as sse_err: logger.error(f"SSE stream error task {task_id}: {sse_err}"); sse_error = sse_err; final_state_val = None

        # Fallback polling if needed
        is_terminal_poll = False
        if TaskStateEnum: is_terminal_poll = final_state_val in [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
        elif isinstance(final_state_val, str): is_terminal_poll = final_state_val in ["COMPLETED", "FAILED", "CANCELED"]

        if not is_terminal_poll:
            logger.warning(f"SSE ended unexpectedly/failed (Error: {sse_error}). Polling task {task_id}...");
            max_polls = 60; wait_base = 5; wait_max = 30; retries = 0
            while not is_terminal_poll:
                wait = min(wait_base + (retries // 5), wait_max); await asyncio.sleep(wait)
                try:
                    status = await self._get_task_status_with_retry(agent_card, task_id)
                    final_state_val = status.state; logger.info(f"Task {task_id} polled status: {final_state_val}")
                    # Re-check terminal state after polling
                    if TaskStateEnum: is_terminal_poll = final_state_val in [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
                    elif isinstance(final_state_val, str): is_terminal_poll = final_state_val in ["COMPLETED", "FAILED", "CANCELED"]

                    if final_state_val == (TaskStateEnum.COMPLETED if TaskStateEnum else "COMPLETED"):
                        if not final_result_content and status.messages:
                             assistant_msgs = [m for m in status.messages if m.role == 'assistant' and m.parts]
                             if assistant_msgs:
                                 last_part = assistant_msgs[-1].parts[0]
                                 if isinstance(last_part, DataPart) and isinstance(last_part.content, dict): final_result_content = last_part.content; logger.info(f"Extracted result data from final polled status for task {task_id}.")
                    elif final_state_val == (TaskStateEnum.FAILED if TaskStateEnum else "FAILED"): final_message_text = getattr(status, 'message', None) or getattr(status, 'status_message', 'Task failed')
                except A2AError as poll_err: raise AgentProcessingError(f"A2A Error polling task {task_id}: {poll_err}") from poll_err
                retries += 1;
                if retries >= max_polls: raise AgentProcessingError(f"Polling timeout task {task_id} on {agent_hri}")

        # Final check on completion status
        is_complete = False
        if TaskStateEnum: is_complete = final_state_val == TaskStateEnum.COMPLETED
        elif isinstance(final_state_val, str): is_complete = final_state_val == "COMPLETED"

        if not is_complete:
            error_msg = f"Task {task_id} on {agent_hri} failed. State: {final_state_val}. Msg: {final_message_text}"; logger.error(error_msg); raise AgentProcessingError(error_msg)
        if not final_result_content: logger.warning(f"Task {task_id} ({agent_hri}) completed but no result data found."); return {}

        logger.info(f"Task {task_id} ({agent_hri}) completed successfully. Returning result data.")
        return final_result_content
