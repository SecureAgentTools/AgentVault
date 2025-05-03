import asyncio
import logging
import uuid
import json
# --- MODIFIED: Added List ---
from typing import Dict, Any, Optional, Union, AsyncGenerator, List
# --- END MODIFIED ---

# Import SDK components
from agentvault_server_sdk import BaseA2AAgent
# --- MODIFIED: Import BackgroundTasks ---
from agentvault_server_sdk.state import BaseTaskStore, InMemoryTaskStore, TaskContext
from agentvault_server_sdk.exceptions import AgentProcessingError, TaskNotFoundError
# --- ADDED: Import BackgroundTasks ---
from fastapi import BackgroundTasks # Import BackgroundTasks here
# --- END ADDED ---
# --- END MODIFIED ---

# Import core library models with fallback
try:
    from agentvault.models import Message, Task, TaskState, A2AEvent, Artifact, TextPart, TaskStatusUpdateEvent
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in base_agent. Using placeholders.")
    class Message: pass # type: ignore
    class Task: pass # type: ignore
    class TaskState: SUBMITTED = "SUBMITTED"; WORKING = "WORKING"; COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELED = "CANCELED" # type: ignore
    class A2AEvent: pass # type: ignore
    class Artifact: pass # type: ignore
    class TextPart: pass # type: ignore
    class TaskStatusUpdateEvent: pass # type: ignore
    _MODELS_AVAILABLE = False

logger_base = logging.getLogger(__name__)

class ResearchAgent(BaseA2AAgent):
    """
    Base class for agents in the research pipeline, providing common structure.
    Uses an InMemoryTaskStore by default.
    """
    def __init__(self, agent_id: str, agent_metadata: Optional[Dict[str, Any]] = None):
        super().__init__(agent_metadata=agent_metadata)
        self.agent_id = agent_id
        self.task_store: BaseTaskStore = InMemoryTaskStore()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        # --- REMOVED: _background_tasks no longer needed here ---
        # self._background_tasks: Dict[str, asyncio.Task] = {}
        # --- END REMOVED ---
        self.logger.info(f"Initialized ResearchAgent: {self.__class__.__name__} (ID: {self.agent_id})")

    # --- MODIFIED: Inject BackgroundTasks, use add_task ---
    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: Optional[BackgroundTasks] = None) -> str: # Made background_tasks optional
        """
        Handles incoming task requests, scheduling background processing using FastAPI BackgroundTasks if available.
        """
        if task_id:
            self.logger.warning(f"Received message for existing task '{task_id}'. This base agent only handles new task initiation.")
            raise AgentProcessingError(f"This agent only supports initiating new tasks, not continuing existing ones (task_id='{task_id}').")

        input_content: Union[str, Dict[str, Any]]
        try:
            # ... (input parsing logic remains the same) ...
            if not message.parts:
                 raise ValueError("Input message has no parts.")

            first_part_content = message.parts[0].content

            if isinstance(first_part_content, str):
                if first_part_content.startswith('\ufeff'):
                    self.logger.debug("Detected and removing BOM from input string.")
                    cleaned_content = first_part_content.lstrip('\ufeff')
                else:
                    cleaned_content = first_part_content

                if cleaned_content.strip().startswith(("{", "[")):
                    try:
                        input_content = json.loads(cleaned_content)
                        self.logger.debug("Successfully parsed input string as JSON.")
                    except json.JSONDecodeError as json_err:
                        self.logger.error(f"Input looked like JSON but failed to parse: {json_err}. Content: {cleaned_content[:200]}...")
                        raise ValueError("Input content looks like JSON but is invalid.") from json_err
                elif cleaned_content:
                    input_content = cleaned_content
                    self.logger.debug("Input is a non-JSON string.")
                else:
                    raise ValueError("First message part content is empty.")

            elif isinstance(first_part_content, (dict, list)):
                input_content = first_part_content
                self.logger.debug("Input is already a dict/list.")
            elif first_part_content is not None:
                 input_content = str(first_part_content)
                 self.logger.debug(f"Input converted to string: {input_content[:100]}...")
            else:
                raise ValueError("First message part has empty or None content.")

        except (AttributeError, IndexError, json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Failed to extract valid input content from message: {message!r}. Error: {e}")
            raise AgentProcessingError("Invalid input message format. Could not extract content.") from e

        new_task_id = f"{self.agent_id}-task-{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Creating new task: {new_task_id}")
        # Create the initial task record in the store
        await self.task_store.create_task(new_task_id)
        self.logger.info(f"Task {new_task_id} created in store.")

        # Schedule the actual processing using BackgroundTasks if provided, else asyncio.create_task
        self.logger.info(f"Task {new_task_id}: Scheduling background task.")
        try:
            if background_tasks:
                self.logger.info(f"Task {new_task_id}: Using provided BackgroundTasks.")
                background_tasks.add_task(self.process_task, new_task_id, input_content)
                self.logger.info(f"Task {new_task_id}: Task added to BackgroundTasks successfully.")
            else:
                self.logger.info(f"Task {new_task_id}: BackgroundTasks not provided, using asyncio.create_task.")
                # Store the asyncio task reference if needed for cancellation later (though cancellation via handle_task_cancel might be complex without BackgroundTasks)
                # self._background_tasks[new_task_id] = asyncio.create_task(self.process_task(new_task_id, input_content))
                asyncio.create_task(self.process_task(new_task_id, input_content)) # Fire and forget if no background_tasks
                self.logger.info(f"Task {new_task_id}: Task scheduled via asyncio.create_task.")
        except Exception as schedule_err:
            self.logger.error(f"Task {new_task_id}: Failed to schedule background task: {schedule_err}", exc_info=True)
            try:
                await self.task_store.update_task_state(new_task_id, TaskState.FAILED, message=f"Failed to schedule background task: {schedule_err}")
            except Exception as final_err:
                 self.logger.error(f"Task {new_task_id}: CRITICAL - Failed to set FAILED state after scheduling error: {final_err}")
            raise AgentProcessingError(f"Failed to schedule background processing for task {new_task_id}") from schedule_err

        self.logger.info(f"Task {new_task_id}: Returning task ID from handle_task_send.")
        return new_task_id
    # --- END MODIFIED ---

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Main processing logic for the agent. Override in subclasses.
        Now executed reliably by FastAPI's BackgroundTasks.
        """
        self.logger.info(f"Task {task_id}: ENTERING process_task (via BackgroundTasks/asyncio).") # Updated log
        try:
            # --- Ensure subclass overrides this ---
            # Default implementation marks as failed
            self.logger.warning(f"Base process_task called for task {task_id}. Subclass should override this.")
            await self.task_store.update_task_state(task_id, TaskState.WORKING) # Set to working first
            await asyncio.sleep(1) # Simulate work
            error_message = "Base agent process_task not implemented."
            await self.task_store.update_task_state(task_id, TaskState.FAILED, message=error_message)
            if _MODELS_AVAILABLE:
                error_msg_obj = Message(role="assistant", parts=[TextPart(content=error_message)])
                await self.task_store.notify_message_event(task_id, error_msg_obj)
            # --- End Ensure subclass overrides ---
        except Exception as e:
             self.logger.exception(f"Task {task_id}: Uncaught exception in process_task: {e}")
             try:
                 # Try to mark as failed with the specific error
                 await self.task_store.update_task_state(task_id, TaskState.FAILED, message=f"Uncaught exception in process_task: {e}")
             except Exception:
                 self.logger.error(f"Task {task_id}: Failed to set FAILED state after uncaught exception in process_task.")
        finally:
            self.logger.info(f"Task {task_id}: EXITING process_task.")

    async def handle_task_get(self, task_id: str) -> Task:
        """Retrieve task status from the store, including messages and artifacts.""" # Updated docstring
        self.logger.debug(f"Handling task get: task_id={task_id}")
        task_context = await self.task_store.get_task(task_id)
        if task_context is None:
            raise TaskNotFoundError(task_id=task_id)

        current_state_enum = task_context.current_state
        if _MODELS_AVAILABLE and isinstance(task_context.current_state, str):
            try:
                current_state_enum = TaskState(task_context.current_state)
            except ValueError:
                self.logger.warning(f"Task {task_id} has invalid stored state '{task_context.current_state}'. Returning as is.")

        # --- ADDED: Fetch messages and artifacts from store ---
        messages = []
        artifacts = []
        if hasattr(self.task_store, 'get_messages') and callable(self.task_store.get_messages):
            messages = await self.task_store.get_messages(task_id) or []
            self.logger.debug(f"Task {task_id}: Fetched {len(messages)} messages from store.")
        else:
            self.logger.warning(f"Task store {type(self.task_store)} does not have get_messages method.")

        if hasattr(self.task_store, 'get_artifacts') and callable(self.task_store.get_artifacts):
            artifacts = await self.task_store.get_artifacts(task_id) or []
            self.logger.debug(f"Task {task_id}: Fetched {len(artifacts)} artifacts from store.")
        else:
             self.logger.warning(f"Task store {type(self.task_store)} does not have get_artifacts method.")
        # --- END ADDED ---

        if _MODELS_AVAILABLE:
            return Task(
                id=task_context.task_id,
                state=current_state_enum,
                createdAt=task_context.created_at,
                updatedAt=task_context.updated_at,
                messages=messages, # Include fetched messages
                artifacts=artifacts, # Include fetched artifacts
                metadata={"agent_id": self.agent_id}
            )
        else:
            # Fallback for when models aren't available
            return { # type: ignore
                "id": task_context.task_id,
                "state": str(current_state_enum), # Ensure string representation
                "createdAt": task_context.created_at.isoformat(),
                "updatedAt": task_context.updated_at.isoformat(),
                "messages": messages, # Include fetched messages (might be Any)
                "artifacts": artifacts, # Include fetched artifacts (might be Any)
                "metadata": {"agent_id": self.agent_id}
            }


    async def handle_task_cancel(self, task_id: str) -> bool:
        """Cancel task (marks state, attempts to cancel background task)."""
        # NOTE: Cancelling tasks managed by FastAPI's BackgroundTasks is not directly supported
        #       via this mechanism. We can mark the state as CANCELED in our store,
        #       but the task itself might continue running in the background.
        #       A more robust cancellation would require inter-task communication (e.g., asyncio.Event).
        self.logger.info(f"Handling task cancel request: task_id={task_id}")
        task_context = await self.task_store.get_task(task_id)
        if task_context is None:
            raise TaskNotFoundError(task_id=task_id)

        terminal_states_str = {"COMPLETED", "FAILED", "CANCELED"}
        current_state_str = str(task_context.current_state.value if _MODELS_AVAILABLE and isinstance(task_context.current_state, TaskState) else task_context.current_state)

        if current_state_str not in terminal_states_str:
            self.logger.warning(f"Task {task_id}: Marking as CANCELED in store. Actual background execution may continue.")
            await self.task_store.update_task_state(task_id, TaskState.CANCELED if _MODELS_AVAILABLE else "CANCELED")
            # We don't have a direct reference to the BackgroundTasks task object here to cancel it.
            return True
        else:
            self.logger.warning(f"Task {task_id} already terminal ({current_state_str}). Cannot cancel.")
            return False

    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        """Handles SSE subscription request by streaming events from the task store's listener queue."""
        self.logger.info(f"Handling subscribe request: task_id={task_id}")
        # Add a small delay to potentially mitigate race condition with task creation
        # Although locking the TaskStore is the proper fix for this.
        await asyncio.sleep(0.1)
        self.logger.info(f"Task {task_id}: Delay before checking task for subscription finished.")

        task_context = await self.task_store.get_task(task_id)
        if task_context is None:
            self.logger.warning(f"Task {task_id} not found when trying to subscribe.")
            raise TaskNotFoundError(task_id=task_id)

        event_queue = asyncio.Queue()
        self.logger.info(f"Task {task_id}: Adding SSE listener.")
        await self.task_store.add_listener(task_id, event_queue)
        self.logger.info(f"Task {task_id}: SSE listener added.")

        try:
            terminal_states_str = {"COMPLETED", "FAILED", "CANCELED"}
            current_state_str = str(task_context.current_state.value if _MODELS_AVAILABLE and isinstance(task_context.current_state, TaskState) else task_context.current_state)

            while current_state_str not in terminal_states_str:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=60.0)
                    self.logger.debug(f"Yielding event for task {task_id}: {type(event).__name__}")
                    yield event

                    if _MODELS_AVAILABLE and isinstance(event, TaskStatusUpdateEvent):
                        current_state_str = str(event.state.value if isinstance(event.state, TaskState) else event.state)
                    elif isinstance(event, dict) and event.get("event_type") == "task_status":
                        current_state_str = str(event.get("data", {}).get("state"))

                except asyncio.TimeoutError:
                    task_context = await self.task_store.get_task(task_id)
                    if task_context:
                        current_state_str = str(task_context.current_state.value if _MODELS_AVAILABLE and isinstance(task_context.current_state, TaskState) else task_context.current_state)
                        if current_state_str in terminal_states_str:
                            self.logger.debug(f"Task {task_id} reached terminal state during SSE timeout check.")
                            break
                        else:
                            self.logger.debug(f"SSE timeout for task {task_id}, but task still active ({current_state_str}). Sending keep-alive comment.")
                            yield b': keep-alive\n\n' # Keep connection alive
                    else:
                        self.logger.warning(f"Task {task_id} disappeared during SSE timeout check.")
                        break
        finally:
            self.logger.info(f"Task {task_id}: Removing SSE listener.")
            await self.task_store.remove_listener(task_id, event_queue)
            self.logger.info(f"Subscription stream ending for task {task_id}")

    async def close(self):
        """Clean up resources."""
        # No background tasks dictionary to clear now
        self.logger.info(f"Agent {self.agent_id} closed.")
