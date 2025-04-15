import pytest
import asyncio
import datetime
from freezegun import freeze_time
from typing import Union, Any, List
# --- ADDED: Import patch ---
from unittest.mock import patch
# --- END ADDED ---


# Import components to test
from agentvault_server_sdk.state import TaskContext, InMemoryTaskStore
from agentvault_server_sdk.exceptions import InvalidStateTransitionError

# Import or define TaskState enum
try:
    from agentvault.models import (
        TaskState, TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent,
        Message, TextPart, Artifact, A2AEvent # Added A2AEvent
    )
    _MODELS_AVAILABLE = True
except ImportError:
    class TaskState: # type: ignore
        SUBMITTED = "SUBMITTED"; WORKING = "WORKING"; INPUT_REQUIRED = "INPUT_REQUIRED"; COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELED = "CANCELED" # type: ignore
    # Define placeholders for other models used in notification tests (even if skipped)
    A2AEvent = Any # type: ignore
    TaskStatusUpdateEvent = Any # type: ignore
    TaskMessageEvent = Any # type: ignore
    TaskArtifactUpdateEvent = Any # type: ignore
    Message = Any # type: ignore
    TextPart = Any # type: ignore
    Artifact = Any # type: ignore
    _MODELS_AVAILABLE = False

# Skip notification tests if models aren't available
pytestmark_notify = pytest.mark.skipif(not _MODELS_AVAILABLE, reason="Core agentvault models not available for notification tests")


# --- Fixtures ---
@pytest.fixture
def task_store() -> InMemoryTaskStore:
    """Provides a fresh InMemoryTaskStore for each test."""
    return InMemoryTaskStore()

@pytest.fixture
def initial_context() -> TaskContext:
    """Provides a TaskContext in the initial SUBMITTED state."""
    return TaskContext(task_id="test-task-1", current_state=TaskState.SUBMITTED)

# --- Tests for TaskContext.update_state ---
# (Existing tests remain unchanged)
@pytest.mark.parametrize("current_state, valid_next_state", [
    (TaskState.SUBMITTED, TaskState.WORKING),
    (TaskState.SUBMITTED, TaskState.CANCELED),
    (TaskState.WORKING, TaskState.INPUT_REQUIRED),
    (TaskState.WORKING, TaskState.COMPLETED),
    (TaskState.WORKING, TaskState.FAILED),
    (TaskState.WORKING, TaskState.CANCELED),
    (TaskState.INPUT_REQUIRED, TaskState.WORKING),
    (TaskState.INPUT_REQUIRED, TaskState.CANCELED),
])
def test_update_state_valid_transitions(initial_context: TaskContext, current_state: Union[TaskState, str], valid_next_state: Union[TaskState, str]):
    """Test allowed state transitions."""
    initial_context.current_state = current_state # Set the starting state
    initial_updated_at = initial_context.updated_at

    # Use freeze_time to check timestamp update
    with freeze_time() as freezer:
        freezer.tick(delta=datetime.timedelta(seconds=1)) # Move time forward
        initial_context.update_state(valid_next_state)
        assert initial_context.current_state == valid_next_state
        assert initial_context.updated_at > initial_updated_at

@pytest.mark.parametrize("current_state, invalid_next_state", [
    (TaskState.SUBMITTED, TaskState.COMPLETED),
    (TaskState.SUBMITTED, TaskState.FAILED),
    (TaskState.SUBMITTED, TaskState.INPUT_REQUIRED),
    (TaskState.WORKING, TaskState.SUBMITTED),
    (TaskState.INPUT_REQUIRED, TaskState.SUBMITTED),
    (TaskState.INPUT_REQUIRED, TaskState.COMPLETED),
    (TaskState.INPUT_REQUIRED, TaskState.FAILED),
    (TaskState.COMPLETED, TaskState.WORKING),
    (TaskState.FAILED, TaskState.WORKING),
    (TaskState.CANCELED, TaskState.WORKING),
])
def test_update_state_invalid_transitions(initial_context: TaskContext, current_state: Union[TaskState, str], invalid_next_state: Union[TaskState, str]):
    """Test disallowed state transitions raise InvalidStateTransitionError."""
    initial_context.current_state = current_state
    with pytest.raises(InvalidStateTransitionError):
        initial_context.update_state(invalid_next_state)
    # Ensure state didn't change
    assert initial_context.current_state == current_state

@pytest.mark.parametrize("terminal_state", [
    TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED
])
def test_update_state_from_terminal_state_fails(initial_context: TaskContext, terminal_state: Union[TaskState, str]):
    """Test transitions from terminal states fail if target is different."""
    initial_context.current_state = terminal_state
    # Attempt transition to a different state
    with pytest.raises(InvalidStateTransitionError):
        initial_context.update_state(TaskState.WORKING)
    assert initial_context.current_state == terminal_state

@pytest.mark.parametrize("state", [
    TaskState.SUBMITTED, TaskState.WORKING, TaskState.INPUT_REQUIRED,
    TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED
])
def test_update_state_to_same_state_succeeds(initial_context: TaskContext, state: Union[TaskState, str]):
    """Test transitioning to the same state is allowed and updates timestamp."""
    initial_context.current_state = state
    initial_updated_at = initial_context.updated_at

    with freeze_time() as freezer:
        freezer.tick(delta=datetime.timedelta(seconds=1))
        initial_context.update_state(state) # Update to the same state
        assert initial_context.current_state == state
        assert initial_context.updated_at > initial_updated_at

def test_update_state_invalid_value(initial_context: TaskContext):
    """Test providing an invalid string as the new state."""
    with pytest.raises(ValueError, match="Invalid target state value"):
        initial_context.update_state("INVALID_STATE_STRING")


# --- Tests for InMemoryTaskStore update_task_state integration ---
@pytest.mark.asyncio
async def test_store_update_task_state_valid_transition(task_store: InMemoryTaskStore):
    """Test store update succeeds with a valid transition."""
    task_id = "store-update-valid"
    await task_store.create_task(task_id) # Starts in SUBMITTED
    context = await task_store.update_task_state(task_id, TaskState.WORKING)
    assert context is not None
    assert context.current_state == TaskState.WORKING
    assert task_store._tasks[task_id].current_state == TaskState.WORKING

@pytest.mark.asyncio
async def test_store_update_task_state_invalid_transition(task_store: InMemoryTaskStore):
    """Test store update returns None for an invalid transition."""
    task_id = "store-update-invalid"
    await task_store.create_task(task_id) # Starts in SUBMITTED
    # Manually set to terminal state for test
    task_store._tasks[task_id].current_state = TaskState.COMPLETED

    # Attempt invalid transition
    context = await task_store.update_task_state(task_id, TaskState.WORKING)
    assert context is None # Should return None as InvalidStateTransitionError was caught
    # Verify state didn't change in the store
    assert task_store._tasks[task_id].current_state == TaskState.COMPLETED

# --- Tests for Listener Management ---
@pytest.mark.asyncio
async def test_listener_add_get_remove(task_store: InMemoryTaskStore):
    """Test adding, getting, and removing listeners."""
    task_id = "task-listener-1"
    q1 = asyncio.Queue()
    q2 = asyncio.Queue()

    # Task doesn't exist initially, listeners should be empty
    assert await task_store.get_listeners(task_id) == []
    assert task_id not in task_store._listeners # Internal check

    # Add first listener (task should be implicitly created if needed by store logic)
    await task_store.add_listener(task_id, q1)
    assert task_id in task_store._listeners # Check internal dict created
    listeners = await task_store.get_listeners(task_id)
    assert listeners == [q1]

    # Add second listener
    await task_store.add_listener(task_id, q2)
    listeners = await task_store.get_listeners(task_id)
    assert q1 in listeners
    assert q2 in listeners
    assert len(listeners) == 2

    # Add first listener again (should not duplicate)
    await task_store.add_listener(task_id, q1)
    listeners = await task_store.get_listeners(task_id)
    assert len(listeners) == 2

    # Remove first listener
    await task_store.remove_listener(task_id, q1)
    listeners = await task_store.get_listeners(task_id)
    assert listeners == [q2]

    # Remove second listener
    await task_store.remove_listener(task_id, q2)
    listeners = await task_store.get_listeners(task_id)
    assert listeners == []

    # Remove listener that doesn't exist
    await task_store.remove_listener(task_id, q1) # Should not raise error
    listeners = await task_store.get_listeners(task_id)
    assert listeners == []

@pytest.mark.asyncio
async def test_listener_management_multiple_tasks(task_store: InMemoryTaskStore):
    """Test listener isolation between different tasks."""
    task_id1 = "task-multi-listen-1"
    task_id2 = "task-multi-listen-2"
    q1 = asyncio.Queue()
    q2 = asyncio.Queue()
    q3 = asyncio.Queue()

    await task_store.add_listener(task_id1, q1)
    await task_store.add_listener(task_id1, q2)
    await task_store.add_listener(task_id2, q3)

    assert await task_store.get_listeners(task_id1) == [q1, q2]
    assert await task_store.get_listeners(task_id2) == [q3]

    await task_store.remove_listener(task_id1, q1)
    assert await task_store.get_listeners(task_id1) == [q2]
    assert await task_store.get_listeners(task_id2) == [q3] # Unchanged

    await task_store.delete_task(task_id1) # Deleting task should remove its listeners
    assert await task_store.get_listeners(task_id1) == []
    assert task_id1 not in task_store._listeners
    assert await task_store.get_listeners(task_id2) == [q3] # Unchanged

# --- Tests for Notification Methods ---

@pytestmark_notify
@pytest.mark.asyncio
async def test_notify_status_update_multiple_listeners(task_store: InMemoryTaskStore):
    """Test notify_status_update reaches multiple listeners."""
    task_id = "notify-status-multi"
    await task_store.create_task(task_id)
    q1 = asyncio.Queue()
    q2 = asyncio.Queue()
    await task_store.add_listener(task_id, q1)
    await task_store.add_listener(task_id, q2)

    # Notify
    new_state = TaskState.WORKING
    status_message = "Processing..."
    await task_store.notify_status_update(task_id, new_state, status_message)

    # Verify queues received the event
    event1 = await asyncio.wait_for(q1.get(), timeout=0.1)
    event2 = await asyncio.wait_for(q2.get(), timeout=0.1)

    assert isinstance(event1, TaskStatusUpdateEvent)
    assert event1.task_id == task_id
    assert event1.state == new_state
    assert event1.message == status_message
    assert isinstance(event1.timestamp, datetime.datetime)

    assert event1 == event2

@pytestmark_notify
@pytest.mark.asyncio
async def test_notify_message_event_success(task_store: InMemoryTaskStore):
    """Test notify_message_event."""
    task_id = "notify-msg-1"
    await task_store.create_task(task_id)
    q1 = asyncio.Queue()
    await task_store.add_listener(task_id, q1)
    test_message = Message(role="assistant", parts=[TextPart(content="Test response")])

    await task_store.notify_message_event(task_id, test_message)

    event = await asyncio.wait_for(q1.get(), timeout=0.1)
    assert isinstance(event, TaskMessageEvent)
    assert event.task_id == task_id
    assert event.message == test_message

@pytestmark_notify
@pytest.mark.asyncio
async def test_notify_artifact_event_success(task_store: InMemoryTaskStore):
    """Test notify_artifact_event."""
    task_id = "notify-art-1"
    await task_store.create_task(task_id)
    q1 = asyncio.Queue()
    await task_store.add_listener(task_id, q1)
    test_artifact = Artifact(id="art-test-1", type="result", content={"value": 123})

    await task_store.notify_artifact_event(task_id, test_artifact)

    event = await asyncio.wait_for(q1.get(), timeout=0.1)
    assert isinstance(event, TaskArtifactUpdateEvent)
    assert event.task_id == task_id
    assert event.artifact == test_artifact

@pytestmark_notify
@pytest.mark.asyncio
async def test_notify_no_listeners_does_nothing(task_store: InMemoryTaskStore):
    """Test that calling notify methods with no listeners is safe."""
    task_id = "notify-none-1"
    await task_store.create_task(task_id) # Task exists, but no listeners added

    # Call notify methods - should complete without error
    await task_store.notify_status_update(task_id, TaskState.FAILED, "Error occurred")
    await task_store.notify_message_event(task_id, Message(role="system", parts=[TextPart(content="Sys Msg")]))
    await task_store.notify_artifact_event(task_id, Artifact(id="art-none", type="log", content="Log"))
    # No assertion needed other than that no exception was raised

@pytestmark_notify
@pytest.mark.asyncio
async def test_notify_different_tasks(task_store: InMemoryTaskStore):
    """Test that notifications are isolated between tasks."""
    task_id1 = "notify-iso-1"
    task_id2 = "notify-iso-2"
    await task_store.create_task(task_id1)
    await task_store.create_task(task_id2)
    q1 = asyncio.Queue()
    q2 = asyncio.Queue()
    await task_store.add_listener(task_id1, q1)
    await task_store.add_listener(task_id2, q2)

    # Notify task 1
    await task_store.notify_status_update(task_id1, TaskState.WORKING)

    # Check task 1 queue received it, task 2 queue is empty
    event1 = await asyncio.wait_for(q1.get(), timeout=0.1)
    assert isinstance(event1, TaskStatusUpdateEvent)
    assert event1.task_id == task_id1
    assert q2.empty()

    # Notify task 2
    msg2 = Message(role="user", parts=[TextPart(content="Input for task 2")])
    await task_store.notify_message_event(task_id2, msg2)

    # Check task 2 queue received it, task 1 queue is empty
    event2 = await asyncio.wait_for(q2.get(), timeout=0.1)
    assert isinstance(event2, TaskMessageEvent)
    assert event2.task_id == task_id2
    assert q1.empty()

@pytestmark_notify
@pytest.mark.asyncio
async def test_update_task_state_triggers_notify(task_store: InMemoryTaskStore):
    """Verify update_task_state calls notify_status_update."""
    task_id = "update-triggers-notify"
    await task_store.create_task(task_id)
    q1 = asyncio.Queue()
    await task_store.add_listener(task_id, q1)

    # Patch the notify method to check it's called
    with patch.object(task_store, 'notify_status_update', wraps=task_store.notify_status_update) as mock_notify:
        await task_store.update_task_state(task_id, TaskState.WORKING)
        mock_notify.assert_awaited_once_with(task_id, TaskState.WORKING)

    # Check the queue still received the event via the wrapped call
    event = await asyncio.wait_for(q1.get(), timeout=0.1)
    assert isinstance(event, TaskStatusUpdateEvent)
    assert event.state == TaskState.WORKING
