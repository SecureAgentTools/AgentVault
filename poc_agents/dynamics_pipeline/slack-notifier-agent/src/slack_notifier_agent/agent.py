import logging
import asyncio
import json
import os
import datetime
from typing import Dict, Any, Union, Optional, List, AsyncGenerator
import uuid

from fastapi import BackgroundTasks # Keep this import

# Set up logger first before any usage
logger = logging.getLogger(__name__)

# Import base class and SDK components
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import TaskState as SdkTaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Import models from this agent's models.py
from .models import SendNotificationInput, SendNotificationOutput

# --- Direct Import of Core Models ---
from agentvault.models import (
    Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent,
    TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent # Import specific event types
)

# --- TaskStateEnum assignment ---
TaskStateEnum = TaskState
AGENT_ID = "local-poc/slack-notifier"

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


class SlackNotifierAgent(BaseA2AAgent):
    """Agent to mock sending Slack notifications by logging."""
    def __init__(self):
        super().__init__(agent_metadata={"name": "Slack Notifier Agent (Mock)"})
        self.task_store: Optional[Any] = None
        self.logger = logger # Assign logger
        logger.info("Slack Notifier Agent initialized.")

    async def _mock_send_notification(self, input_data: SendNotificationInput) -> SendNotificationOutput:
        """Simulates sending the notification by logging."""
        output = SendNotificationOutput(success=False, message="Mock notification failed.")
        try:
            # The core "work" is just logging
            self.logger.info(f"MOCK SLACK: Sending to target '{input_data.target}' message: '{input_data.message_text}'")
            output.success = True
            output.message = "Mock Slack notification logged successfully."
        except Exception as e:
            self.logger.exception(f"Unexpected error during mock Slack notification logging: {e}")
            output.message = f"Unexpected error during mock notification: {e}"
        return output

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: Optional[BackgroundTasks] = None) -> str:
        # (Standard implementation)
        if task_id: raise AgentProcessingError(f"Slack notifier agent does not support continuing task {task_id}")
        new_task_id = f"slack-notify-{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Task {new_task_id}: Received Slack notification request.")
        if not self.task_store: raise ConfigurationError("Task store not initialized.")
        await self.task_store.create_task(new_task_id)
        input_content = None
        if message.parts:
            for part in message.parts:
                if isinstance(part, DataPart): input_content = part.content; break
        if not isinstance(input_content, dict):
             await self.task_store.update_task_state(new_task_id, TaskStateEnum.FAILED, "Invalid input: Expected DataPart dict.")
             raise AgentProcessingError("Invalid input: Expected DataPart dict.")

        await asyncio.sleep(0.5) # Allow SSE connection time

        self.logger.info(f"Task {new_task_id}: Scheduling process_task via asyncio.create_task.")
        asyncio.create_task(self.process_task(new_task_id, input_content))
        return new_task_id

    async def process_task(self, task_id: str, content: Dict[str, Any]):
        # (Standard implementation, adapted for notification)
        if not self.task_store:
            self.logger.error(f"Task {task_id}: Task store missing.")
            return

        await self.task_store.update_task_state(task_id, TaskStateEnum.WORKING)
        self.logger.info(f"Task {task_id}: Background processing started for Slack notification.")
        final_state = TaskStateEnum.FAILED
        error_message = "Failed mock Slack notification."
        output_data: Optional[SendNotificationOutput] = None

        try:
            try:
                input_data = SendNotificationInput.model_validate(content)
            except Exception as val_err:
                raise AgentProcessingError(f"Invalid input for Slack notification: {val_err}")

            target = input_data.target
            self.logger.info(f"Task {task_id}: Processing mock Slack notification for target '{target}'.")

            # Perform the mock operation
            output_data = await self._mock_send_notification(input_data)

            if output_data.success:
                final_state = TaskStateEnum.COMPLETED
                error_message = None
                self.logger.info(f"Task {task_id}: Mock Slack notification processed successfully.")
            else:
                final_state = TaskStateEnum.FAILED # Keep FAILED if mock operation failed internally
                error_message = output_data.message
                self.logger.error(f"Task {task_id}: Mock Slack notification processing failed: {output_data.message}")

            # Send the result message
            response_msg = Message(role="assistant", parts=[DataPart(content=output_data.model_dump())])

            try:
                await self.task_store.notify_message_event(task_id, response_msg)
                await asyncio.sleep(0.1)
            except Exception as msg_err:
                self.logger.error(f"Task {task_id}: Error sending result message event: {msg_err}")

        except AgentProcessingError as e:
            self.logger.error(f"Task {task_id}: Processing error: {e}")
            error_message = str(e); final_state = TaskStateEnum.FAILED
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error during Slack notification process: {e}")
            error_message = f"Unexpected error: {e}"; final_state = TaskStateEnum.FAILED
        finally:
            self.logger.info(f"Task {task_id}: Setting final state to {final_state}")
            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            await asyncio.sleep(0.1)
            self.logger.info(f"Task {task_id}: Background processing finished.")

    async def handle_task_get(self, task_id: str) -> Task:
        # (Standard implementation)
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        messages = await self.task_store.get_messages(task_id) or []; artifacts = await self.task_store.get_artifacts(task_id) or []
        return Task(id=task_id, state=context.current_state, createdAt=context.created_at, updatedAt=context.updated_at, messages=messages, artifacts=artifacts) # type: ignore

    async def handle_task_cancel(self, task_id: str) -> bool:
        # (Standard implementation)
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
        if context.current_state not in terminal:
            await self.task_store.update_task_state(task_id, TaskStateEnum.CANCELED, "Cancelled by request.")
            return True
        return False

    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        # (Standard implementation)
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
            try: yield status_event; await asyncio.sleep(0.05)
            except Exception as e: self.logger.error(f"Task {task_id}: Error yielding initial state: {e}")

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
                        self.logger.error(f"Task {task_id}: Error during yield: {yield_err}", exc_info=True); break

                except Exception as loop_err:
                    self.logger.error(f"Task {task_id}: Error in main event processing loop: {loop_err}", exc_info=True); break

                context = await self.task_store.get_task(task_id)
                terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
                if context and context.current_state in terminal:
                    self.logger.info(f"Task {task_id}: Terminal state ({context.current_state}) detected after event processing. Breaking."); break
        except asyncio.CancelledError:
            self.logger.info(f"Task {task_id}: SSE stream cancelled (client disconnected?)."); raise
        except Exception as loop_err:
            self.logger.error(f"Task {task_id}: Error in SSE generator outer loop: {loop_err}", exc_info=True)
        finally:
            self.logger.info(f"Task {task_id}: Removing SSE listener in finally block.")
            await self.task_store.remove_listener(task_id, q)
            self.logger.info(f"Task {task_id}: SSE listener removed. Total events yielded: {event_count}. Exiting handle_subscribe_request.")

    async def close(self):
        # (Standard implementation - no external resources like DB pool)
        self.logger.info("Slack Notifier Agent closed.")
