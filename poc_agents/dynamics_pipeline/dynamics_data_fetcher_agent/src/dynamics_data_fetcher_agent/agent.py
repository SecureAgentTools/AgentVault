import logging
import asyncio
import json
import os
import datetime
from typing import Dict, Any, Union, Optional, List, AsyncGenerator
import uuid

import asyncpg
from fastapi import BackgroundTasks # Keep this import

# Set up logger first before any usage
logger = logging.getLogger(__name__)

# Import base class and SDK components
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import TaskState as SdkTaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Import models from this agent's models.py
from .models import FetchInput, FetchOutput, DynamicsDataPayload, AccountData, ContactData, OpportunityData, CaseData

# --- Direct Import of Core Models ---
from agentvault.models import (
    Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent,
    TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent # Import specific event types
)

# --- TaskStateEnum assignment ---
TaskStateEnum = TaskState
AGENT_ID = "local-poc/dynamics-data-fetcher"
DB_HOST = os.environ.get("DATABASE_HOST", "d365-db"); DB_PORT = os.environ.get("DATABASE_PORT", 5432)
DB_USER = os.environ.get("DATABASE_USER", "d365_user"); DB_PASSWORD = os.environ.get("DATABASE_PASSWORD", "d365_password"); DB_NAME = os.environ.get("DATABASE_NAME", "d365_poc_db")
db_config_valid = all([DB_USER, DB_PASSWORD, DB_NAME])
if not db_config_valid: logger.error("DB connection details missing.")
logger.info(f"Database configuration - HOST: {DB_HOST}, PORT: {DB_PORT}, USER: {DB_USER}, DB: {DB_NAME}, Valid: {db_config_valid}")

# --- Helper function for SSE Formatting ---
def _agent_format_sse_event_bytes(event: A2AEvent) -> Optional[bytes]:
    """Helper within the agent to format an A2AEvent into SSE message bytes."""
    event_type: Optional[str] = None
    if isinstance(event, TaskStatusUpdateEvent): event_type = "task_status"
    elif isinstance(event, TaskMessageEvent): event_type = "task_message"
    elif isinstance(event, TaskArtifactUpdateEvent): event_type = "task_artifact"

    if event_type is None:
        logging.getLogger(__name__).warning(f"Cannot format unknown event type: {type(event)}")
        return None
    try:
        if hasattr(event, 'model_dump_json'):
             json_data = event.model_dump_json(by_alias=True)
        elif hasattr(event, 'dict'):
             json_data = json.dumps(event.dict(by_alias=True))
        elif isinstance(event, dict):
             json_data = json.dumps(event)
        else:
             json_data = json.dumps(str(event))
        sse_message = f"event: {event_type}\ndata: {json_data}\n\n"
        return sse_message.encode("utf-8")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to serialize or format SSE event (type: {event_type}): {e}", exc_info=True)
        return None
# --- End Helper ---


class DynamicsDataFetcherAgent(BaseA2AAgent):
    def __init__(self):
        super().__init__(agent_metadata={"name": "Dynamics Data Fetcher Agent (Mock DB)"})
        self.db_pool: Optional[asyncpg.Pool] = None
        self.db_config_valid = db_config_valid
        self.task_store: Optional[Any] = None
        self.logger = logger # Assign logger
        logger.info(f"Dynamics Data Fetcher Agent initialized. DB Config Valid: {self.db_config_valid}")

    async def _get_db_pool(self) -> asyncpg.Pool:
        if not self.db_config_valid: raise ConfigurationError("DB not configured.")
        if self.db_pool is None:
            self.logger.info(f"Creating DB pool for {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
            try:
                self.db_pool = await asyncpg.create_pool(user=DB_USER, password=DB_PASSWORD, database=DB_NAME, host=DB_HOST, port=DB_PORT, min_size=1, max_size=5)
                self.logger.info("DB pool created.")
            except Exception as e: self.logger.exception(f"Failed to create DB pool: {e}"); raise ConfigurationError(f"DB connection failed: {e}") from e
        return self.db_pool # type: ignore

    async def _fetch_data_from_db(self, account_id: str) -> DynamicsDataPayload:
        pool = await self._get_db_pool(); payload = DynamicsDataPayload()
        async with pool.acquire() as conn:
            account_rec = await conn.fetchrow("SELECT * FROM mock_accounts WHERE account_id = $1", account_id)
            if account_rec:
                payload.account = AccountData(**dict(account_rec))
                # If website exists but doesn't have a protocol, add https:// prefix
                if payload.account.website and not payload.account.website.startswith(('http://', 'https://')):
                    payload.account.website = f"https://{payload.account.website}"
                self.logger.info(f"Fetched account data for {account_id}")
                contacts_recs = await conn.fetch("SELECT * FROM mock_contacts WHERE account_id = $1", account_id)
                payload.contacts = [ContactData(**dict(rec)) for rec in contacts_recs]; self.logger.info(f"Fetched {len(payload.contacts)} contacts for {account_id}")
                opp_recs = await conn.fetch("SELECT * FROM mock_opportunities WHERE account_id = $1", account_id)
                payload.opportunities = [OpportunityData(**dict(rec)) for rec in opp_recs]; self.logger.info(f"Fetched {len(payload.opportunities)} opportunities for {account_id}")
                case_recs = await conn.fetch("SELECT * FROM mock_cases WHERE account_id = $1", account_id)
                payload.cases = [CaseData(**dict(rec)) for rec in case_recs]; self.logger.info(f"Fetched {len(payload.cases)} cases for {account_id}")
            else:
                self.logger.warning(f"Account ID {account_id} not found in mock_accounts table.")
                # Return an empty payload if account not found, orchestrator expects this possibility
                payload = DynamicsDataPayload(account=None) # Ensure it returns the main structure
                self.logger.info(f"Returning empty dynamics data for {account_id}")
        return payload

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: Optional[BackgroundTasks] = None) -> str:
        if task_id: raise AgentProcessingError(f"Fetcher agent does not support continuing task {task_id}")
        new_task_id = f"d365-fetch-{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Task {new_task_id}: Received data fetch request.")
        if not self.task_store: raise ConfigurationError("Task store not initialized.")
        await self.task_store.create_task(new_task_id)
        input_content = None
        # Use direct import now
        if message.parts:
            for part in message.parts:
                if isinstance(part, DataPart): input_content = part.content; break
        if not isinstance(input_content, dict):
             await self.task_store.update_task_state(new_task_id, TaskStateEnum.FAILED, "Invalid input: Expected DataPart dict.")
             raise AgentProcessingError("Invalid input: Expected DataPart dict.")

        # Give clients time to establish SSE connections before starting processing
        await asyncio.sleep(0.5)

        # Use asyncio.create_task for concurrency
        self.logger.info(f"Task {new_task_id}: Scheduling process_task via asyncio.create_task (Ignoring BackgroundTasks).")
        asyncio.create_task(self.process_task(new_task_id, input_content))
        return new_task_id

    async def process_task(self, task_id: str, content: Dict[str, Any]):
        if not self.task_store:
            self.logger.error(f"Task {task_id}: Task store missing.")
            return

        await self.task_store.update_task_state(task_id, TaskStateEnum.WORKING)
        self.logger.info(f"Task {task_id}: Background processing started.")
        final_state = TaskStateEnum.FAILED
        error_message = "Failed data fetch."
        completion_message = error_message
        output_data = None

        try:
            if not self.db_config_valid:
                raise ConfigurationError("DB not configured.")
            try:
                input_data = FetchInput.model_validate(content)
            except Exception as val_err:
                raise AgentProcessingError(f"Invalid input: {val_err}")

            account_id = input_data.account_id
            self.logger.info(f"Task {task_id}: Fetching data for account ID '{account_id}'.")
            dynamics_payload = await self._fetch_data_from_db(account_id)
            output_data = FetchOutput(dynamics_data=dynamics_payload)
            completion_message = f"Successfully fetched mock Dynamics data for account '{account_id}'."

            # Use direct import now
            response_msg = Message(role="assistant", parts=[DataPart(content=output_data.model_dump())])

            try:
                self.logger.info(f"Task {task_id}: Sending message event notification")
                await self.task_store.notify_message_event(task_id, response_msg)
                self.logger.info(f"Task {task_id}: Message notification sent")
                # Give a short sleep AFTER sending message event
                await asyncio.sleep(0.1) # <<< ENSURE SLEEP HERE
            except Exception as msg_err:
                self.logger.error(f"Task {task_id}: Error sending message event: {msg_err}")

            final_state = TaskStateEnum.COMPLETED
            error_message = None

        except AgentProcessingError as e:
            self.logger.error(f"Task {task_id}: Processing error: {e}")
            error_message = str(e)
        except ConfigurationError as e:
            self.logger.error(f"Task {task_id}: Config error: {e}")
            error_message = str(e)
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error: {e}")
            error_message = f"Unexpected error: {e}"
        finally:
            self.logger.info(f"Task {task_id}: Setting final state to {final_state}")
            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            # Give a short sleep AFTER sending final state event
            await asyncio.sleep(0.1) # <<< ENSURE SLEEP HERE
            self.logger.info(f"Task {task_id}: Background processing finished.")

    async def handle_task_get(self, task_id: str) -> Task:
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        # Use direct import now
        messages = await self.task_store.get_messages(task_id) or []; artifacts = await self.task_store.get_artifacts(task_id) or []
        return Task(id=task_id, state=context.current_state, createdAt=context.created_at, updatedAt=context.updated_at, messages=messages, artifacts=artifacts) # type: ignore

    async def handle_task_cancel(self, task_id: str) -> bool:
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
        # Use direct import now (TaskStateEnum is TaskState)
        if context.current_state not in terminal:
            await self.task_store.update_task_state(task_id, TaskStateEnum.CANCELED, "Cancelled by request.")
            return True
        return False

    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        self.logger.info(f"Task {task_id}: Entered handle_subscribe_request.")
        if not self.task_store: raise ConfigurationError("Task store missing.")

        # Create and register the queue
        q = asyncio.Queue()
        await self.task_store.add_listener(task_id, q)
        self.logger.info(f"Task {task_id}: Listener queue added.")

        # Get the current task state - may already have updates
        context = await self.task_store.get_task(task_id)
        if context:
            # If task already has a state, create and yield a status event
            self.logger.info(f"Task {task_id}: Current state is {context.current_state}")
            now = datetime.datetime.now(datetime.timezone.utc)
            # Only create event if SDK models are available
            status_event = TaskStatusUpdateEvent(taskId=task_id, state=context.current_state, timestamp=now)
            self.logger.info(f"Task {task_id}: Yielding initial state event.")
            try:
                yield status_event
                await asyncio.sleep(0.05)  # Ensure client has time to process
            except Exception as e:
                self.logger.error(f"Task {task_id}: Error yielding initial state: {e}")

        try:
            event_count = 0
            while True:
                try:
                    self.logger.debug(f"Task {task_id}: Waiting for event on queue...")
                    # Use a timeout to periodically check terminal state
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=2.0)
                        event_count += 1
                        self.logger.info(f"Task {task_id}: Retrieved event #{event_count} from queue: type={type(event).__name__}")
                    except asyncio.TimeoutError:
                        # No event received within timeout, check terminal state
                        context = await self.task_store.get_task(task_id)
                        if context and context.current_state in [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]:
                            self.logger.info(f"Task {task_id}: Terminal state detected during wait timeout. Breaking.")
                            break
                        self.logger.debug(f"Task {task_id}: No event received in the last 2 seconds, continuing to wait...")
                        continue

                    # Simply yield the event directly
                    try:
                        self.logger.debug(f"Task {task_id}: Yielding event: {type(event).__name__}")
                        yield event
                        self.logger.debug(f"Task {task_id}: Yield successful.")
                        # Give control back to event loop
                        await asyncio.sleep(0.05)
                    except Exception as yield_err:
                        self.logger.error(f"Task {task_id}: Error during yield: {yield_err}", exc_info=True)
                        break  # Stop on yield error

                except Exception as loop_err:
                    self.logger.error(f"Task {task_id}: Error in main event processing loop: {loop_err}", exc_info=True)
                    break

                # Check for terminal state after processing event
                context = await self.task_store.get_task(task_id)
                terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
                if context and context.current_state in terminal:
                    self.logger.info(f"Task {task_id}: Terminal state ({context.current_state}) detected after event processing. Breaking.")
                    break
        except asyncio.CancelledError:
            self.logger.info(f"Task {task_id}: SSE stream cancelled (client disconnected?).")
            raise  # Re-raise cancellation
        except Exception as loop_err:
            self.logger.error(f"Task {task_id}: Error in SSE generator outer loop: {loop_err}", exc_info=True)
        finally:
            self.logger.info(f"Task {task_id}: Removing SSE listener in finally block.")
            await self.task_store.remove_listener(task_id, q)
            self.logger.info(f"Task {task_id}: SSE listener removed. Total events yielded: {event_count}. Exiting handle_subscribe_request.")

    async def close(self):
        if self.db_pool: self.logger.info("Closing DB pool..."); await self.db_pool.close(); self.logger.info("DB pool closed.")
        self.logger.info("Dynamics Data Fetcher Agent closed.")
