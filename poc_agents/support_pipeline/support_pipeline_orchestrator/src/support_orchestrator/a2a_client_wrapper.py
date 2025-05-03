# Adapting A2AClientWrapper from e-commerce example for the Support Pipeline
# REQ-SUP-ORCH-001, REQ-SUP-ORCH-006

import asyncio
import json
import logging
import time
import uuid
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, AsyncGenerator, List, Union

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
        A2ATimeoutError, A2AMessageError, ConfigurationError as AgentVaultConfigurationError, # Alias to avoid clash
        AgentCardFetchError, KeyManagementError
    )
    _AGENTVAULT_AVAILABLE = True
except ImportError as e:
    logging.getLogger(__name__).critical(f"Failed to import core 'agentvault' library: {e}. A2AClientWrapper cannot function.")
    # Define placeholders
    class AgentVaultClient: pass # type: ignore
    class KeyManager: pass # type: ignore
    class agent_card_utils: pass # type: ignore
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class DataPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class AgentCard: pass # type: ignore
    class TaskState: pass # type: ignore
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
    class AgentVaultConfigurationError(AgentVaultError): pass # type: ignore
    class AgentCardFetchError(AgentVaultError): pass # type: ignore
    class KeyManagementError(AgentVaultError): pass # type: ignore
    _AGENTVAULT_AVAILABLE = False

# Import config for this pipeline
from .config import SupportPipelineConfig, get_pipeline_config, ConfigurationError # Use local ConfigurationError

logger = logging.getLogger(__name__)

class AgentProcessingError(Exception):
    """Raised when an error occurs during agent task processing within the orchestrator."""
    pass

# Define expected HRIs for this pipeline (REQ-SUP-ORCH-002)
SUPPORT_AGENT_HRIS = [
    "local-poc/support-ticket-analyzer",
    "local-poc/support-kb-search",
    "local-poc/support-customer-history",
    "local-poc/support-response-suggester"
]

# Define expected ports for URL replacement (REQ-SUP-ANA-003, REQ-SUP-KBS-003, etc.)
AGENT_PORT_MAP = {
    "8030": "ticket-analyzer-agent", # Assuming Port 8030 for Analyzer
    "8031": "kb-search-agent",       # Assuming Port 8031 for KB Search
    "8032": "customer-history-agent",# Assuming Port 8032 for History
    "8033": "response-suggester-agent" # Assuming Port 8033 for Suggester
}

RETRYABLE_EXCEPTIONS = (A2AConnectionError, A2ATimeoutError)
retry_strategy = retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)

class A2AClientWrapper:
    """
    Wraps the AgentVaultClient for the Support Ticket pipeline,
    using registry lookup for agent discovery.
    """
    def __init__(self, config: Optional[SupportPipelineConfig] = None):
        if not _AGENTVAULT_AVAILABLE:
            raise ConfigurationError("AgentVault library is required but not available.")

        self.config = config or get_pipeline_config() # Loads SupportPipelineConfig
        self.registry_url = self.config.orchestration.registry_url
        self.client = AgentVaultClient()
        self.key_manager = KeyManager() # Assuming no auth needed for PoC agents
        self.agent_cards: Dict[str, AgentCard] = {}
        self._is_initialized = False
        logger.info(f"A2AClientWrapper initialized for Support Pipeline. Registry: {self.registry_url}")

    async def initialize(self):
        """
        Load agent cards by querying the configured registry using HRIs.
        """
        if self._is_initialized:
            logger.debug("A2AClientWrapper already initialized.")
            return

        logger.info(f"Initializing A2AClientWrapper: Discovering support agents from registry at {self.registry_url}...")
        self.agent_cards = {}
        discovered_count = 0
        # Get required HRIs from the loaded config (REQ-SUP-ORCH-002)
        required_hris = [
            self.config.ticket_analyzer_agent.hri,
            self.config.kb_search_agent.hri,
            self.config.customer_history_agent.hri,
            self.config.response_suggester_agent.hri
        ]

        async with httpx.AsyncClient() as http_client:
            for agent_hri in required_hris:
                logger.debug(f"Discovering agent: {agent_hri}")
                encoded_hri = urllib.parse.quote(agent_hri, safe='')
                lookup_url = f"{self.registry_url.rstrip('/')}/api/v1/agent-cards/id/{encoded_hri}"
                logger.info(f"Registry lookup URL: {lookup_url}")

                try:
                    response = await http_client.get(lookup_url, follow_redirects=True, timeout=15.0)
                    if response.status_code == 404:
                        logger.error(f"Agent card for HRI '{agent_hri}' not found in registry at {lookup_url}.")
                        continue
                    response.raise_for_status()

                    card_full_data = response.json()
                    card_data_dict = card_full_data.get("card_data") if isinstance(card_full_data, dict) else None
                    if not card_data_dict:
                        raise AgentCardFetchError(f"Registry response for {agent_hri} missing 'card_data'. Response: {card_full_data!r}")

                    agent_card = AgentCard.model_validate(card_data_dict)

                    # Replace localhost URLs with Docker service names based on expected ports
                    url_str = str(agent_card.url)
                    original_url_str = url_str # Keep original for logging
                    for port, service_name in AGENT_PORT_MAP.items():
                        if f"localhost:{port}" in url_str:
                            new_url = url_str.replace(f"localhost:{port}", f"{service_name}:{port}")
                            agent_card.url = new_url # Pydantic will re-validate
                            logger.info(f"Replaced URL for HRI {agent_hri}: {original_url_str} -> {new_url}")
                            break # Assume only one match per card

                    self.agent_cards[agent_hri] = agent_card
                    logger.info(f"Successfully discovered and cached card for agent: {agent_hri} at {agent_card.url}")
                    discovered_count += 1
                except httpx.RequestError as e:
                    logger.error(f"Network error discovering agent '{agent_hri}' from registry {self.registry_url}: {e}")
                except AgentCardFetchError as e:
                    logger.error(f"Failed to fetch/parse agent card for '{agent_hri}' from registry: {e}")
                except httpx.HTTPStatusError as e:
                     logger.error(f"HTTP error discovering agent '{agent_hri}' from registry: Status {e.response.status_code} for URL {lookup_url}", exc_info=True)
                except Exception as e:
                    logger.exception(f"Unexpected error discovering agent '{agent_hri}': {e}")

        missing = set(required_hris) - set(self.agent_cards.keys())
        if missing:
            logger.error(f"Failed to discover all required support agents from registry {self.registry_url}. Missing: {missing}")
            raise ConfigurationError(f"Could not discover all pipeline agents from registry. Missing: {missing}")

        self._is_initialized = True
        logger.info(f"A2AClientWrapper initialization complete. Discovered {discovered_count} agent cards.")
        logger.info("--- AGENT CARD MAPPING ---")
        for hri, card in self.agent_cards.items(): logger.info(f"HRI: {hri} -> URL: {str(card.url)}")
        logger.info("-------------------------")

    async def close(self):
        """Closes the underlying AgentVaultClient."""
        # Current AgentVaultClient doesn't require explicit close
        logger.info("A2AClientWrapper closed.")

    # --- Retry Helpers (identical to e-commerce example) ---
    @retry_strategy
    async def _initiate_task_with_retry(self, agent_card: AgentCard, message: Message) -> str:
        return await self.client.initiate_task(agent_card, message, self.key_manager)

    @retry_strategy
    async def _get_task_status_with_retry(self, agent_card: AgentCard, task_id: str) -> Task:
        return await self.client.get_task_status(agent_card, task_id, self.key_manager)

    async def _try_sse_subscription(self, agent_card: AgentCard, task_id: str, key_manager: KeyManager,
                               max_attempts: int = 3, retry_delay: float = 5.0) -> AsyncGenerator[A2AEvent, None]:
        event_method = getattr(self.client, "receive_messages", None)
        if not event_method: raise AttributeError("'receive_messages' method not found in AgentVaultClient")
        attempt = 0; last_error = None
        while attempt < max_attempts:
            attempt += 1
            try:
                logger.info(f"SSE subscription attempt {attempt}/{max_attempts} for task {task_id}")
                async for event in event_method(agent_card, task_id, key_manager): yield event
                return
            except Exception as e:
                last_error = e; error_text = str(e).lower()
                if "task not found" in error_text or "not found" in error_text:
                    if attempt < max_attempts: logger.warning(f"Task not found error on SSE attempt {attempt}, retrying in {retry_delay} seconds: {e}"); await asyncio.sleep(retry_delay)
                    else: logger.error(f"Failed to subscribe to SSE after {max_attempts} attempts: {e}"); raise
                else: logger.error(f"Non-retriable error on SSE subscription: {e}"); raise
        raise last_error # type: ignore

    async def run_a2a_task(self, agent_hri: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs a task on the specified agent (looked up by HRI) and waits for completion.
        Returns a dictionary mapping artifact types to their content.
        """
        if not self._is_initialized: await self.initialize()
        if agent_hri not in self.agent_cards: raise ConfigurationError(f"Agent card for '{agent_hri}' not loaded or discovered.")

        agent_card = self.agent_cards[agent_hri]
        logger.info(f"Running task on agent: {agent_hri} ({agent_card.name}) via registry lookup")

        try: initial_message = Message(role="user", parts=[DataPart(content=input_payload)])
        except Exception as e: logger.error(f"Failed to create initial message for agent {agent_hri}: {e}", exc_info=True); raise AgentProcessingError(f"Cannot create initial message for {agent_hri}") from e

        task_id: Optional[str] = None
        try: task_id = await self._initiate_task_with_retry(agent_card, initial_message); logger.info(f"Task {task_id} initiated on agent {agent_hri}.")
        except A2AError as e: logger.error(f"A2A Error initiating task on {agent_hri} after retries: {e}", exc_info=True); raise AgentProcessingError(f"Failed to initiate task on {agent_hri} after retries: {e}") from e
        except Exception as e: logger.exception(f"Unexpected error initiating task on {agent_hri}"); raise AgentProcessingError(f"Unexpected error initiating task on {agent_hri}: {e}") from e

        task_artifacts: Dict[str, Artifact] = {}; final_state: Optional[TaskState] = None; final_message: Optional[str] = None; sse_error = None

        try:
            logger.info(f"Starting SSE streaming for task {task_id} on {agent_hri}...")
            async for event in self._try_sse_subscription(agent_card, task_id, self.key_manager):
                logger.debug(f"SSE Event ({agent_hri} / {task_id}): Type={type(event).__name__}")
                if isinstance(event, TaskStatusUpdateEvent):
                    final_state = event.state; final_message = event.message; logger.info(f"Task {task_id} status update: {final_state}")
                    if final_state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]: break
                elif isinstance(event, TaskMessageEvent):
                     if event.message.role == "assistant" and event.message.parts: logger.debug(f"Task {task_id} message: {event.message.parts[0].content[:100]}...")
                elif isinstance(event, TaskArtifactUpdateEvent):
                     artifact = event.artifact; task_artifacts[artifact.type] = artifact; logger.info(f"Received artifact '{artifact.type}' (ID: {artifact.id}) via SSE for task {task_id}")
        except Exception as sse_err:
             logger.error(f"Error in SSE stream for task {task_id}: {sse_err}"); sse_error = sse_err; logger.warning(f"Falling back to polling after SSE error for task {task_id}"); final_state = None

        if final_state not in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]:
            logger.warning(f"SSE stream ended unexpectedly or failed (Error: {sse_error}). Polling for final status...")
            max_polling_retries = 60; polling_wait_base = 5; polling_wait_max = 30; retry_count = 0
            while final_state not in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]:
                wait_time = min(polling_wait_base + (retry_count // 5), polling_wait_max)
                logger.debug(f"Polling task {task_id} (attempt {retry_count+1}/{max_polling_retries}), waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                try:
                    status = await self._get_task_status_with_retry(agent_card, task_id)
                    final_state = status.state; logger.info(f"Task {task_id} polled status: {final_state}")
                    if final_state == TaskState.COMPLETED:
                        logger.info(f"Polling detected completion for task {task_id}. Extracting artifacts.")
                        artifacts_list = status.artifacts if status.artifacts else []
                        for artifact in artifacts_list: task_artifacts[artifact.type] = artifact; logger.info(f"Extracted artifact '{artifact.type}' (ID: {artifact.id}) from final status object.")
                        if status.messages:
                             assistant_msgs = [m for m in status.messages if m.role == 'assistant' and m.parts]
                             if assistant_msgs: final_message = assistant_msgs[-1].parts[0].content
                    elif final_state == TaskState.FAILED: final_message = getattr(status, 'message', None) or getattr(status, 'status_message', 'Task failed without specific message.')
                except A2AError as poll_err: logger.error(f"A2A Error polling status for task {task_id} after retries: {poll_err}", exc_info=True); raise AgentProcessingError(f"Failed to get status for task {task_id} after retries: {poll_err}") from poll_err
                retry_count += 1
                if retry_count >= max_polling_retries: logger.error(f"Polling timeout after {max_polling_retries} attempts for task {task_id} on {agent_hri}."); raise AgentProcessingError(f"Polling timeout for task {task_id} on {agent_hri}")

        if final_state != TaskState.COMPLETED:
            error_msg = f"Task {task_id} on agent {agent_hri} did not complete successfully. Final state: {final_state}."
            if final_message: error_msg += f" Message: {final_message}"
            logger.error(error_msg); raise AgentProcessingError(error_msg)

        logger.info(f"Task {task_id} ({agent_hri}) completed. Returning {len(task_artifacts)} artifact types.")
        # Return the content of the artifacts
        result_data = {atype: artifact.content for atype, artifact in task_artifacts.items() if artifact.content is not None}
        return result_data
