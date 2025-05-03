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
from .models import CreateTaskInput, CreateTaskOutput

# --- Direct Import of Core Models ---
from agentvault.models import (
    Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent,
    TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent # Import specific event types
)

# --- TaskStateEnum assignment ---
TaskStateEnum = TaskState
AGENT_ID = "local-poc/dynamics-task-creator"
DB_HOST = os.environ.get("DATABASE_HOST", "d365-db"); DB_PORT = os.environ.get("DATABASE_PORT", 5432)
DB_USER = os.environ.get("DATABASE_USER", "d365_user"); DB_PASSWORD = os.environ.get("DATABASE_PASSWORD", "d365_password"); DB_NAME = os.environ.get("DATABASE_NAME", "d365_poc_db")
db_config_valid = all([DB_USER, DB_PASSWORD, DB_NAME])
if not db_config_valid: logger.error("DB connection details missing.")
logger.info(f"Database configuration - HOST: {DB_HOST}, PORT: {DB_PORT}, USER: {DB_USER}, DB: {DB_NAME}, Valid: {db_config_valid}")

# --- Helper function for SSE Formatting ---
# (Copied from fetcher agent - standard utility)
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


class DynamicsTaskCreatorAgent(BaseA2AAgent):
    """Agent to create task records in the mock Dynamics database."""
    def __init__(self):
        super().__init__(agent_metadata={"name": "Dynamics Task Creator Agent (Mock DB)"})
        self.db_pool: Optional[asyncpg.Pool] = None
        self.db_config_valid = db_config_valid
        self.task_store: Optional[Any] = None
        self.logger = logger # Assign logger
        logger.info(f"Dynamics Task Creator Agent initialized. DB Config Valid: {self.db_config_valid}")

    async def _get_db_pool(self) -> asyncpg.Pool:
        # (Copied from fetcher agent)
        if not self.db_config_valid: raise ConfigurationError("DB not configured.")
        if self.db_pool is None:
            self.logger.info(f"Creating DB pool for {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
            try:
                self.db_pool = await asyncpg.create_pool(user=DB_USER, password=DB_PASSWORD, database=DB_NAME, host=DB_HOST, port=DB_PORT, min_size=1, max_size=5)
                self.logger.info("DB pool created.")
            except Exception as e: self.logger.exception(f"Failed to create DB pool: {e}"); raise ConfigurationError(f"DB connection failed: {e}") from e
        return self.db_pool # type: ignore

    async def _create_task_in_db(self, input_data: CreateTaskInput) -> CreateTaskOutput:
        """Handles the database INSERT operation."""
        pool = await self._get_db_pool()
        output = CreateTaskOutput(success=False, message="Task creation failed.", created_task_id=None)
        sql = """
            INSERT INTO mock_tasks (account_id, subject, priority, related_record_id, status)
            VALUES ($1, $2, $3, $4, 'Open')
            RETURNING task_id;
        """
        try:
            async with pool.acquire() as conn:
                # Execute the insert and get the returned task_id
                new_task_id = await conn.fetchval(
                    sql,
                    input_data.account_id,
                    input_data.task_subject,
                    input_data.priority,
                    input_data.related_record_id
                )
                if new_task_id:
                    output.success = True
                    output.message = f"Task created successfully with ID {new_task_id}."
                    output.created_task_id = new_task_id
                    self.logger.info(f"Successfully inserted task for account {input_data.account_id}. New task ID: {new_task_id}")
                else:
                    self.logger.error(f"Database insert for task (account: {input_data.account_id}) did not return a task_id.")
                    output.message = "Database insert succeeded but did not return a task ID."

        except asyncpg.exceptions.ForeignKeyViolationError as fk_err:
             self.logger.error(f"Database foreign key violation creating task for account {input_data.account_id}: {fk_err}")
             output.message = f"Failed to create task: Account ID '{input_data.account_id}' not found."
        except asyncpg.exceptions.UniqueViolationError as uv_err:
             self.logger.error(f"Database unique constraint violation creating task: {uv_err}")
             output.message = f"Failed to create task: Unique constraint violation ({uv_err.constraint_name})."
        except asyncpg.PostgresError as db_err:
            self.logger.exception(f"Database error creating task for account {input_data.account_id}: {db_err}")
            output.message = f"Database error during task creation: {db_err}"
        except Exception as e:
            self.logger.exception(f"Unexpected error creating task in DB for account {input_data.account_id}: {e}")
            output.message = f"Unexpected error during task creation: {e}"

        return output

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: Optional[BackgroundTasks] = None) -> str:
        # (Standard implementation - copied from fetcher agent)
        if task_id: raise AgentProcessingError(f"Task creator agent does not support continuing task {task_id}")
        new_task_id = f"d365-task-create-{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Task {new_task_id}: Received task creation request.")
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
        # (Standard implementation - copied from fetcher agent, adapted for task creation)
        if not self.task_store:
            self.logger.error(f"Task {task_id}: Task store missing.")
            return

        await self.task_store.update_task_state(task_id, TaskStateEnum.WORKING)
        self.logger.info(f"Task {task_id}: Background processing started for task creation.")
        final_state = TaskStateEnum.FAILED
        error_message = "Failed task creation."
        output_data: Optional[CreateTaskOutput] = None

        try:
            if not self.db_config_valid:
                raise ConfigurationError("DB not configured.")
            try:
                input_data = CreateTaskInput.model_validate(content)
            except Exception as val_err:
                raise AgentProcessingError(f"Invalid input for task creation: {val_err}")

            account_id = input_data.account_id
            self.logger.info(f"Task {task_id}: Attempting to create task in DB for account ID '{account_id}'.")

            # Perform the database operation
            output_data = await self._create_task_in_db(input_data)

            if output_data.success:
                final_state = TaskStateEnum.COMPLETED
                error_message = None
                self.logger.info(f"Task {task_id}: DB operation successful. {output_data.message}")
            else:
                final_state = TaskStateEnum.FAILED # Keep FAILED if DB operation failed
                error_message = output_data.message
                self.logger.error(f"Task {task_id}: DB operation failed. {output_data.message}")

            # Send the result message regardless of DB success/failure
            response_msg = Message(role="assistant", parts=[DataPart(content=output_data.model_dump())])

            try:
                self.logger.info(f"Task {task_id}: Sending result message event notification")
                await self.task_store.notify_message_event(task_id, response_msg)
                self.logger.info(f"Task {task_id}: Result message notification sent")
                await asyncio.sleep(0.1) # Allow event propagation
            except Exception as msg_err:
                self.logger.error(f"Task {task_id}: Error sending result message event: {msg_err}")
                # Don't override the primary error state if message sending fails

        except AgentProcessingError as e:
            self.logger.error(f"Task {task_id}: Processing error: {e}")
            error_message = str(e)
            final_state = TaskStateEnum.FAILED
        except ConfigurationError as e:
            self.logger.error(f"Task {task_id}: Config error: {e}")
            error_message = str(e)
            final_state = TaskStateEnum.FAILED
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error during task creation process: {e}")
            error_message = f"Unexpected error: {e}"
            final_state = TaskStateEnum.FAILED
        finally:
            self.logger.info(f"Task {task_id}: Setting final state to {final_state}")
            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            await asyncio.sleep(0.1) # Allow event propagation
            self.logger.info(f"Task {task_id}: Background processing finished.")

    async def handle_task_get(self, task_id: str) -> Task:
        # (Standard implementation - copied from fetcher agent)
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        messages = await self.task_store.get_messages(task_id) or []; artifacts = await self.task_store.get_artifacts(task_id) or []
        return Task(id=task_id, state=context.current_state, createdAt=context.created_at, updatedAt=context.updated_at, messages=messages, artifacts=artifacts) # type: ignore

    async def handle_task_cancel(self, task_id: str) -> bool:
        # (Standard implementation - copied from fetcher agent)
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
        if context.current_state not in terminal:
            await self.task_store.update_task_state(task_id, TaskStateEnum.CANCELED, "Cancelled by request.")
            return True
        return False

    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        # (Standard implementation - copied from fetcher agent)
        self.logger.info(f"Task {task_id}: Entered handle_subscribe_request.")
        if not self.task_store: raise ConfigurationError("Task store missing.")

        q = asyncio.Queue()
        await self.task_store.add_listener(task_id, q)
        self.logger.info(f"Task {task_id}: Listener queue added.")

        context = await self.task_store.get_task(task_id)
        if context:
            self.logger.info(f"Task {task_id}: Current state is {context.current_state}")
            now = datetime.datetime.now(datetime.timezone.utc)
            status_event = TaskStatusUpdateEvent(taskId=task_id, state=context.current_state, timestamp=now)
            self.logger.info(f"Task {task_id}: Yielding initial state event.")
            try:
                yield status_event
                await asyncio.sleep(0.05)
            except Exception as e:
                self.logger.error(f"Task {task_id}: Error yielding initial state: {e}")

        try:
            event_count = 0
            while True:
                try:
                    self.logger.debug(f"Task {task_id}: Waiting for event on queue...")
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=2.0)
                        event_count += 1
                        self.logger.info(f"Task {task_id}: Retrieved event #{event_count} from queue: type={type(event).__name__}")
                    except asyncio.TimeoutError:
                        context = await self.task_store.get_task(task_id)
                        if context and context.current_state in [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]:
                            self.logger.info(f"Task {task_id}: Terminal state detected during wait timeout. Breaking.")
                            break
                        self.logger.debug(f"Task {task_id}: No event received in the last 2 seconds, continuing to wait...")
                        continue

                    try:
                        self.logger.debug(f"Task {task_id}: Yielding event: {type(event).__name__}")
                        yield event
                        self.logger.debug(f"Task {task_id}: Yield successful.")
                        await asyncio.sleep(0.05)
                    except Exception as yield_err:
                        self.logger.error(f"Task {task_id}: Error during yield: {yield_err}", exc_info=True)
                        break

                except Exception as loop_err:
                    self.logger.error(f"Task {task_id}: Error in main event processing loop: {loop_err}", exc_info=True)
                    break

                context = await self.task_store.get_task(task_id)
                terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
                if context and context.current_state in terminal:
                    self.logger.info(f"Task {task_id}: Terminal state ({context.current_state}) detected after event processing. Breaking.")
                    break
        except asyncio.CancelledError:
            self.logger.info(f"Task {task_id}: SSE stream cancelled (client disconnected?).")
            raise
        except Exception as loop_err:
            self.logger.error(f"Task {task_id}: Error in SSE generator outer loop: {loop_err}", exc_info=True)
        finally:
            self.logger.info(f"Task {task_id}: Removing SSE listener in finally block.")
            await self.task_store.remove_listener(task_id, q)
            self.logger.info(f"Task {task_id}: SSE listener removed. Total events yielded: {event_count}. Exiting handle_subscribe_request.")

    async def close(self):
        # (Standard implementation - copied from fetcher agent)
        if self.db_pool: self.logger.info("Closing DB pool..."); await self.db_pool.close(); self.logger.info("DB pool closed.")
        self.logger.info("Dynamics Task Creator Agent closed.")
