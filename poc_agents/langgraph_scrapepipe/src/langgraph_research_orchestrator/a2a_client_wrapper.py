import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, AsyncGenerator, List

import httpx
import pydantic
# --- ADDED: Import tenacity ---
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
# --- END ADDED ---


# Import necessary components from the AgentVault library
try:
    from agentvault import AgentVaultClient, KeyManager
    from agentvault.models import (
        Message, TextPart, DataPart, Artifact, AgentCard, TaskState, A2AEvent, Task, # Added Task
        TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent
    )
    from agentvault.exceptions import (
        AgentVaultError, A2AError, A2AConnectionError, A2ARemoteAgentError,
        A2ATimeoutError, A2AMessageError, ConfigurationError, AgentCardFetchError
    )
    _AGENTVAULT_AVAILABLE = True
except ImportError as e:
    logging.getLogger(__name__).critical(f"Failed to import core 'agentvault' library: {e}. A2AClientWrapper cannot function.")
    # Define placeholders if needed for type hinting, but raise error on init
    class AgentVaultClient: pass # type: ignore
    class KeyManager: pass # type: ignore
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
    class ConfigurationError(AgentVaultError): pass # type: ignore
    class AgentCardFetchError(AgentVaultError): pass # type: ignore
    _AGENTVAULT_AVAILABLE = False

# Import state for type hinting
from .state import ResearchState

logger = logging.getLogger(__name__)

# Define custom exception for agent processing errors within the orchestrator context
class AgentProcessingError(Exception):
    """Raised when an error occurs during agent task processing within the orchestrator."""
    pass

# Agent HRIs list (copied from direct_load_pipeline for consistency)
AGENT_HRIS = [
    "local-poc/topic-research",
    "local-poc/content-crawler",
    "local-poc/information-extraction",
    "local-poc/fact-verification",
    "local-poc/content-synthesis",
    "local-poc/editor",
    "local-poc/visualization"
]

# Calculate default agent card directory path
WRAPPER_FILE_PATH = Path(__file__).resolve()
DEFAULT_AGENT_CARD_DIR = WRAPPER_FILE_PATH.parent.parent.parent.parent / "research_pipeline" / "agent_cards"

# --- ADDED: Retry Configuration ---
# Define which exceptions trigger a retry
RETRYABLE_EXCEPTIONS = (
    A2AConnectionError,
    A2ATimeoutError,
    # Optionally retry on specific transient server errors
    # A2ARemoteAgentError, # Be careful retrying this - check status code inside if needed
)

# Configure the retry decorator
# Wait 2^x * 1 second between each retry starting with 2 seconds (wait=2, multiplier=1), up to 30 seconds, stop after 4 attempts.
retry_strategy = retry(
    stop=stop_after_attempt(4), # Retry 3 times after the initial failure (total 4 attempts)
    wait=wait_exponential(multiplier=1, min=2, max=30), # Exponential backoff: 2s, 4s, 8s
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING) # Log before sleeping on retry
)
# --- END ADDED ---


class A2AClientWrapper:
    """
    Wraps the AgentVaultClient to provide a simplified interface for running tasks
    on pipeline agents, handling card loading, A2A calls, and event processing.
    Includes basic retry logic for network-related A2A errors.
    """
    def __init__(self, agent_card_dir: Path = DEFAULT_AGENT_CARD_DIR):
        if not _AGENTVAULT_AVAILABLE:
            raise ConfigurationError("AgentVault library is required but not available.")

        self.agent_card_dir = agent_card_dir.resolve()
        self.client = AgentVaultClient()
        self.key_manager = KeyManager()
        self.agent_cards: Dict[str, AgentCard] = {}
        self._is_initialized = False
        logger.info(f"A2AClientWrapper initialized. Agent card directory: {self.agent_card_dir}")

    async def initialize(self):
        """Load agent cards from local files."""
        if self._is_initialized:
            logger.debug("A2AClientWrapper already initialized.")
            return
        # ... (rest of initialize method remains the same) ...
        logger.info("Initializing A2AClientWrapper: Loading agent cards from local files...")
        self.agent_cards = {}
        discovered_count = 0

        if not self.agent_card_dir.is_dir():
            logger.error(f"Resolved agent cards directory does not exist or is not a directory: {self.agent_card_dir}")
            raise ConfigurationError(f"Agent cards directory not found: {self.agent_card_dir}")

        for agent_hri in AGENT_HRIS:
            logger.debug(f"Loading agent card for: {agent_hri}")
            agent_type = agent_hri.split('/')[-1].replace('-', '_')
            card_path = self.agent_card_dir / agent_type / "agent-card.json"

            if not card_path.exists():
                logger.error(f"Agent card file not found: {card_path}")
                continue
            try:
                with open(card_path, 'r', encoding='utf-8') as f:
                    card_data = json.load(f)
                agent_card = AgentCard.model_validate(card_data)
                agent_card.url = str(agent_card.url) # Store URL as string
                self.agent_cards[agent_hri] = agent_card
                logger.info(f"Successfully loaded card for agent: {agent_hri} at {agent_card.url}")
                discovered_count += 1
            except (json.JSONDecodeError, pydantic.ValidationError) as e:
                logger.error(f"Failed to load/validate agent card from {card_path}: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error loading agent card from {card_path}: {e}", exc_info=True)
                continue

        if len(self.agent_cards) != len(AGENT_HRIS):
            missing = set(AGENT_HRIS) - set(self.agent_cards.keys())
            logger.error(f"Failed to load all required agents. Missing: {missing}")
            raise ConfigurationError(f"Could not load all pipeline agents from {self.agent_card_dir}. Missing: {missing}")

        self._is_initialized = True
        logger.info(f"A2AClientWrapper initialization complete. Loaded {discovered_count} agent cards.")


    async def close(self):
        """Closes the underlying AgentVaultClient."""
        await self.client.close()
        logger.info("A2AClientWrapper closed.")

    # --- ADDED: Apply retry decorator to internal A2A call methods ---
    @retry_strategy
    async def _initiate_task_with_retry(self, agent_card: AgentCard, message: Message) -> str:
        """Internal helper to initiate task with retry logic."""
        return await self.client.initiate_task(agent_card, message, self.key_manager)

    @retry_strategy
    async def _get_task_status_with_retry(self, agent_card: AgentCard, task_id: str) -> Task:
        """Internal helper to get task status with retry logic."""
        return await self.client.get_task_status(agent_card, task_id, self.key_manager)
    # --- END ADDED ---

    # Add a new retry helper specifically for SSE subscriptions
    async def _try_sse_subscription(self, agent_card: AgentCard, task_id: str, key_manager: KeyManager, 
                               max_attempts: int = 3, retry_delay: float = 5.0) -> AsyncGenerator[A2AEvent, None]:
        """
        Try to subscribe to SSE events with retries for local LLM environments.
        
        This helper specifically handles the "Task not found" errors that can occur
        when trying to subscribe to SSE events for a task that was just created
        and is still being processed by a local LLM.
        """
        event_method = getattr(self.client, "subscribe_to_events", None)
        if not event_method:
            raise AttributeError("'subscribe_to_events' method not found in AgentVaultClient")
        
        attempt = 0
        last_error = None
        
        while attempt < max_attempts:
            attempt += 1
            try:
                logger.info(f"SSE subscription attempt {attempt}/{max_attempts} for task {task_id}")
                async for event in event_method(agent_card, task_id, key_manager):
                    yield event
                # If we get here without exception, the generator completed successfully
                return
            except Exception as e:
                last_error = e
                error_text = str(e)
                
                # If it's a "Task not found" error, we'll retry
                if "Task not found" in error_text or "task not found" in error_text.lower():
                    if attempt < max_attempts:
                        logger.warning(f"Task not found error on SSE attempt {attempt}, retrying in {retry_delay} seconds: {e}")
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(f"Failed to subscribe to SSE after {max_attempts} attempts: {e}")
                        raise
                else:
                    # For other errors, don't retry
                    logger.error(f"Non-retriable error on SSE subscription: {e}")
                    raise
        
        # If we get here, we've exhausted all retries
        raise last_error

    async def run_a2a_task(self, agent_hri: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs a task on the specified agent and waits for completion, returning aggregated artifacts.
        Includes retry logic for task initiation and status polling.
        """
        if not self._is_initialized:
            await self.initialize()

        if agent_hri not in self.agent_cards:
            raise ConfigurationError(f"Agent card for '{agent_hri}' not loaded.")

        agent_card = self.agent_cards[agent_hri]
        logger.info(f"Running task on agent: {agent_hri} ({agent_card.name})")

        # 1. Prepare Input Message
        try:
            initial_message = Message(role="user", parts=[DataPart(content=input_payload)])
        except Exception as e:
            logger.error(f"Failed to create initial message for agent {agent_hri}: {e}", exc_info=True)
            raise AgentProcessingError(f"Cannot create initial message for {agent_hri}") from e

        # 2. Initiate Task (with retry)
        task_id: Optional[str] = None
        try:
            # --- MODIFIED: Call internal retry helper ---
            task_id = await self._initiate_task_with_retry(agent_card, initial_message)
            # --- END MODIFIED ---
            logger.info(f"Task {task_id} initiated on agent {agent_hri}.")
            
            # Add a longer delay before subscribing to events to ensure the task is processed by the LLM
            logger.info(f"Waiting for LLM to process task {task_id}...")
            await asyncio.sleep(10.0)  # 10 second delay for local LLM processing
        except A2AError as e: # Catch errors after retries are exhausted
            logger.error(f"A2A Error initiating task on {agent_hri} after retries: {e}", exc_info=True)
            raise AgentProcessingError(f"Failed to initiate task on {agent_hri} after retries: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error initiating task on {agent_hri}")
            raise AgentProcessingError(f"Unexpected error initiating task on {agent_hri}: {e}") from e

        # 3. Process Events / Poll Status
        task_artifacts: Dict[str, Artifact] = {}
        final_state: Optional[TaskState] = None
        final_message: Optional[str] = None
        max_polling_retries = 120
        polling_wait_base = 2
        polling_wait_max = 20
        goto_polling = False  # Use SSE streaming by default

        try:
            # Use "subscribe_to_events" which is the correct method name in the AgentVault client
            event_method = getattr(self.client, "subscribe_to_events", None)

            if event_method and not goto_polling:
                # ... (SSE streaming logic remains the same) ...
                logger.info(f"Starting SSE streaming for task {task_id} on {agent_hri}...")
                
                # Extra safeguard: poll once to verify task exists and has started processing
                max_verify_attempts = 3
                verify_attempt = 0
                task_verified = False
                
                while not task_verified and verify_attempt < max_verify_attempts:
                    try:
                        verify_attempt += 1
                        status = await self._get_task_status_with_retry(agent_card, task_id)
                        logger.info(f"Verified task {task_id} exists with state: {status.state}")
                        task_verified = True
                    except Exception as verify_err:
                        if verify_attempt >= max_verify_attempts:
                            logger.warning(f"Could not verify task status after {verify_attempt} attempts: {verify_err}")
                            # Continue anyway and try SSE
                        else:
                            logger.info(f"Task verification attempt {verify_attempt} failed: {verify_err}. Retrying in 5 seconds...")
                            await asyncio.sleep(5.0)
                
                # Use our robust SSE subscription method with retries
                sse_error = None
                try:
                    async for event in self._try_sse_subscription(agent_card, task_id, self.key_manager, max_attempts=3, retry_delay=5.0):
                        logger.debug(f"SSE Event ({agent_hri} / {task_id}): Type={event.event_type}")
                        if event.event_type == "task_status":
                            final_state = event.data.state
                            final_message = event.data.message
                            logger.info(f"Task {task_id} status update: {final_state}")
                            if final_state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]:
                                break
                        elif event.event_type == "task_message":
                            if event.data.message.role == "assistant" and event.data.message.parts:
                                logger.debug(f"Task {task_id} message: {event.data.message.parts[0].content[:100]}...")
                        elif event.event_type == "task_artifact":
                            artifact = event.data.artifact
                            task_artifacts[artifact.type] = artifact
                            logger.info(f"Received artifact '{artifact.type}' via SSE for task {task_id}")
                except Exception as sse_err:
                    logger.error(f"Error in SSE stream for task {task_id}: {sse_err}")
                    logger.info(f"Falling back to polling after SSE error for task {task_id}")
                    # Store error details for logging
                    sse_error = sse_err
                    # Continue with polling as fallback
                    final_state = None  # Reset since we'll poll instead
                    goto_polling = True
                    
                # Log detailed information about SSE results    
                if goto_polling:
                    if sse_error:
                        logger.warning(f"SSE streaming failed with error: {type(sse_error).__name__}: {sse_error}")
                    logger.info(f"Will use polling as fallback for task {task_id}")
                elif not final_state:
                    logger.warning(f"SSE streaming completed but no final state received. Will use polling as fallback for task {task_id}")
                    goto_polling = True
                else:
                    logger.info(f"SSE streaming completed successfully for task {task_id} with state: {final_state}")
            if goto_polling or not event_method:
                # --- Robust Polling Fallback (with retry on get_task_status) ---
                logger.warning(f"Falling back to polling for task {task_id} on {agent_hri}")
                retry_count = 0
                while final_state not in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]:
                    wait_time = min(polling_wait_base + (retry_count // 10), polling_wait_max)
                    logger.debug(f"Polling task {task_id} (attempt {retry_count+1}/{max_polling_retries}), waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)

                    # --- MODIFIED: Call internal retry helper for status check ---
                    try:
                        status = await self._get_task_status_with_retry(agent_card, task_id)
                    except A2AError as poll_err: # Catch errors after status retries exhausted
                         logger.error(f"A2A Error polling status for task {task_id} after retries: {poll_err}", exc_info=True)
                         raise AgentProcessingError(f"Failed to get status for task {task_id} after retries: {poll_err}") from poll_err
                    # --- END MODIFIED ---

                    final_state = status.state
                    logger.info(f"Task {task_id} polled status: {final_state}")

                    if final_state == TaskState.COMPLETED:
                        logger.info(f"Polling detected completion for task {task_id}. Extracting artifacts.")
                        for artifact in status.artifacts:
                            task_artifacts[artifact.type] = artifact
                            logger.info(f"Extracted artifact '{artifact.type}' from final status object for task {task_id}")
                        if status.messages:
                            assistant_msgs = [m for m in status.messages if m.role == 'assistant' and m.parts]
                            if assistant_msgs: final_message = assistant_msgs[-1].parts[0].content
                    elif final_state == TaskState.FAILED:
                        if hasattr(status, 'message') and status.message: final_message = status.message
                        elif hasattr(status, 'status_message') and status.status_message: final_message = status.status_message
                        else: final_message = 'Task failed without specific message.'

                    retry_count += 1
                    if retry_count >= max_polling_retries:
                        logger.error(f"Polling timeout after {max_polling_retries} attempts for task {task_id} on {agent_hri}.")
                        raise AgentProcessingError(f"Polling timeout for task {task_id} on {agent_hri}")

        except A2AError as e:
            logger.error(f"A2A Error processing task {task_id} on {agent_hri}: {e}", exc_info=True)
            raise AgentProcessingError(f"A2A Error with {agent_hri}: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error processing task {task_id} on {agent_hri}")
            raise AgentProcessingError(f"Unexpected error with {agent_hri}: {e}") from e

        # 4. Check Final State and Return Results
        if final_state != TaskState.COMPLETED:
            error_msg = f"Task {task_id} on agent {agent_hri} did not complete successfully. Final state: {final_state}."
            if final_message: error_msg += f" Message: {final_message}"
            logger.error(error_msg)
            raise AgentProcessingError(error_msg)

        logger.info(f"Task {task_id} ({agent_hri}) completed. Returning {len(task_artifacts)} artifact types.")
        result_data = {atype: artifact.content for atype, artifact in task_artifacts.items() if artifact.content is not None}
        return result_data
