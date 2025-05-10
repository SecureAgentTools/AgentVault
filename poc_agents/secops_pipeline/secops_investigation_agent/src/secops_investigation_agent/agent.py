import logging
import asyncio
import os
import uuid
import datetime
from typing import Dict, Any, Optional, AsyncGenerator, List
import json

# Import agentvault models and base agent class
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import BaseTaskStore, TERMINAL_STATES
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Import core models needed for A2A protocol
from agentvault.models import (
    Message, DataPart, Task, A2AEvent, TaskState,
    TaskStatusUpdateEvent, TaskMessageEvent
)

logger = logging.getLogger(__name__)

class SimpleInvestigationAgent(BaseA2AAgent):
    """
    Simplified investigation agent that implements the minimum required A2A protocol methods.
    This is a stripped-down version for troubleshooting.
    """
    
    def __init__(self, task_store: BaseTaskStore):
        """Initialize the agent with a task store."""
        super().__init__(agent_metadata={"name": "SecOps Investigation Agent"})
        self.task_store = task_store
        self.logger = logger
        logger.info("SimpleInvestigationAgent initialized.")
        
    def is_terminal(self, state):
        """
        Helper method to check if a state is terminal.
        Works with both enum members and string representations.
        """
        if hasattr(state, 'value'):
            # It's the enum version
            state_str = str(state.value)
        else:
            # It's already a string
            state_str = str(state)
            
        return state_str in TERMINAL_STATES
    
    async def handle_task_send(self, task_id: Optional[str], message: Message) -> str:
        """
        Handle a task/send request by creating a new task.
        This is the primary method called by the orchestrator.
        
        Args:
            task_id: Optional existing task ID (not supported in this agent)
            message: The message data from the orchestrator
            
        Returns:
            New task ID
        """
        # Don't allow continuation of existing tasks
        if task_id:
            raise AgentProcessingError("Investigation agent does not support continuing tasks")
        
        # Create a new task ID
        new_task_id = f"investigate-{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Task {new_task_id}: Received investigation request.")
        
        # Extract input data from message
        input_data = None
        if message.parts:
            for part in message.parts:
                if isinstance(part, DataPart) and isinstance(part.content, dict):
                    input_data = part.content
                    break
        
        # Validate input
        if not input_data:
            await self.task_store.create_task(new_task_id)
            await self.task_store.update_task_state(new_task_id, TaskState.FAILED, "Invalid input: Expected DataPart.")
            raise AgentProcessingError("Invalid input: Expected DataPart.")
        
        # Create the task and process it in the background
        await self.task_store.create_task(new_task_id)
        asyncio.create_task(self._process_task(new_task_id, input_data))
        
        return new_task_id
    
    async def _process_task(self, task_id: str, input_data: Dict[str, Any]):
        """
        Process the task in the background.
        This is a simplified version that just returns a hardcoded result.
        
        Args:
            task_id: The task ID
            input_data: The input data from the orchestrator
        """
        # Update task state to WORKING
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Background processing started.")
        
        try:
            # Extract alert data from input
            alert_data = input_data.get("alert", {})
            enrichment_data = input_data.get("enrichment", {})
            
            # Log what we received
            self.logger.info(f"Task {task_id}: Processing alert: {alert_data.get('name', 'Unknown alert')}") 
            
            # Create a simple findings object
            findings = {
                "summary": "Investigation completed with simplified agent.",
                "severity": "Medium",
                "confidence": 0.6,
                "details": {
                    "analysis_method": "simplified",
                    "alert_analyzed": alert_data.get("alert_id", "Unknown"),
                    "alert_name": alert_data.get("name", "Unknown"),
                    "source_ip": alert_data.get("source_ip", "Unknown")
                }
            }
            
            # Wait a moment to simulate processing (helps debugging by making the sequence clearer)
            await asyncio.sleep(1)
            
            # Create response message with findings
            result_message = Message(
                role="assistant", 
                parts=[DataPart(content=findings)]
            )
            
            # Send the message to the task store
            await self.task_store.notify_message_event(task_id, result_message)
            
            # Update task state to COMPLETED
            await self.task_store.update_task_state(task_id, TaskState.COMPLETED)
            self.logger.info(f"Task {task_id}: Processing completed successfully.")
            
        except Exception as e:
            # Handle any errors
            error_message = f"Error processing task: {str(e)}"
            self.logger.error(f"Task {task_id}: {error_message}", exc_info=True)
            
            # Update task state to FAILED
            await self.task_store.update_task_state(task_id, TaskState.FAILED, error_message)
    
    async def handle_task_get(self, task_id: str) -> Task:
        """
        Handle a task/get request.
        This method is called by the orchestrator to get the status of a task.
        
        Args:
            task_id: The task ID to get
            
        Returns:
            Task object with status and messages
        """
        # Check if task store is available
        if not self.task_store:
            raise ConfigurationError("Task store not initialized.")
        
        # Get the task from the store
        context = await self.task_store.get_task(task_id)
        if context is None:
            raise TaskNotFoundError(task_id=task_id)
        
        # Get messages and artifacts
        messages = await self.task_store.get_messages(task_id) or []
        artifacts = await self.task_store.get_artifacts(task_id) or []
        
        # Create and return task object
        return Task(
            id=context.task_id,
            state=context.current_state,
            createdAt=context.created_at,
            updatedAt=context.updated_at,
            messages=messages,
            artifacts=artifacts
        )
    
    async def handle_task_cancel(self, task_id: str) -> bool:
        """
        Handle a task/cancel request.
        This method is called by the orchestrator to cancel a task.
        
        Args:
            task_id: The task ID to cancel
            
        Returns:
            True if the task was canceled, False otherwise
        """
        # Check if task store is available
        if not self.task_store:
            raise ConfigurationError("Task store not initialized.")
        
        # Get the task from the store
        context = await self.task_store.get_task(task_id)
        if context is None:
            raise TaskNotFoundError(task_id=task_id)
        
        # Check if the task is in a terminal state
        terminal_states = [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]
        if context.current_state not in terminal_states:
            # If not, cancel it
            await self.task_store.update_task_state(task_id, TaskState.CANCELED, "Cancelled by client request.")
            self.logger.info(f"Task {task_id}: Cancellation requested and processed.")
            return True
        
        # Already in terminal state
        self.logger.warning(f"Task {task_id}: Cancellation requested but task already in terminal state {context.current_state}.")
        return False
    
    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        """
        Handle a subscribe request.
        This method is called by the orchestrator to subscribe to task events.
        
        Args:
            task_id: The task ID to subscribe to
            
        Yields:
            Task events
        """
        self.logger.info(f"Task {task_id}: SSE subscription requested.")
        
        # Check if task store is available
        if not self.task_store:
            raise ConfigurationError("Task store not initialized.")
        
        # Create a queue for events
        listener_queue = asyncio.Queue()
        await self.task_store.add_listener(task_id, listener_queue)
        
        try:
            # Send current state as first event
            context = await self.task_store.get_task(task_id)
            if context:
                now = datetime.datetime.now(datetime.timezone.utc)
                status_event = TaskStatusUpdateEvent(taskId=task_id, state=context.current_state, timestamp=now)
                yield status_event
                await asyncio.sleep(0.05)
            
            # Process events from the queue
            while True:
                try:
                    # Wait for an event with timeout
                    event = await asyncio.wait_for(listener_queue.get(), timeout=10.0)
                    
                    # Yield the event
                    yield event
                    await asyncio.sleep(0.05)
                    
                    # Check if it's a terminal state
                    if isinstance(event, TaskStatusUpdateEvent):
                        terminal_states = [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]
                        if event.state in terminal_states:
                            self.logger.info(f"Task {task_id}: Terminal state {event.state} received. Closing stream.")
                            break
                
                except asyncio.TimeoutError:
                    # Check if the task is in a terminal state on timeout
                    context = await self.task_store.get_task(task_id)
                    if not context:
                        self.logger.warning(f"Task {task_id}: Task not found during SSE timeout check.")
                        break
                    
                    terminal_states = [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]
                    if context.current_state in terminal_states:
                        self.logger.info(f"Task {task_id}: Task found in terminal state {context.current_state} during SSE timeout check. Closing stream.")
                        break
                
                except Exception as e:
                    self.logger.error(f"Task {task_id}: Error processing queue event: {e}", exc_info=True)
                    break
        
        except asyncio.CancelledError:
            self.logger.info(f"Task {task_id}: SSE stream cancelled by client or server shutdown.")
            raise
        
        except Exception as e:
            self.logger.error(f"Task {task_id}: Unexpected error in SSE handler: {e}", exc_info=True)
        
        finally:
            # Clean up
            self.logger.info(f"Task {task_id}: Cleaning up SSE listener queue.")
            await self.task_store.remove_listener(task_id, listener_queue)
