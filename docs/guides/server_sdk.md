# Developer Guide: Server SDK (`agentvault-server-sdk`)

The `agentvault-server-sdk` provides tools and abstractions to simplify the development of A2A-compliant agent servers in Python, particularly when using the FastAPI web framework. It helps you focus on your agent's core logic while the SDK handles much of the A2A protocol boilerplate.

## Installation

Install the SDK from PyPI:

```bash
pip install agentvault-server-sdk
```
*(Note: This automatically installs the `agentvault` client library as a dependency).*

See the main [Installation Guide](../installation.md) for more details, including setting up a development environment to run from source.

## Core Concepts

The SDK revolves around implementing an agent logic class (inheriting from `BaseA2AAgent`) and integrating it with a web framework (currently FastAPI).

### 1. `BaseA2AAgent` (`agent.py`)

This is the abstract base class your agent logic should inherit from.

*   **Purpose:** Defines the standard interface the A2A protocol expects an agent server to fulfill.
*   **Required Methods:** If you are *not* using the `@a2a_method` decorator for all standard methods, you *must* implement these `async` methods in your subclass:
    *   `handle_task_send(task_id: Optional[str], message: Message) -> str`: Processes incoming messages (`tasks/send` JSON-RPC method). Should handle task creation or updates and return the task ID.
    *   `handle_task_get(task_id: str) -> Task`: Retrieves the full state (`Task` model) of a specific task (`tasks/get` JSON-RPC method).
    *   `handle_task_cancel(task_id: str) -> bool`: Attempts to cancel a task (`tasks/cancel` JSON-RPC method), returning `True` if the request is accepted.
    *   `handle_subscribe_request(task_id: str) -> AsyncGenerator[A2AEvent, None]`: Returns an async generator yielding `A2AEvent` objects for SSE streaming (`tasks/sendSubscribe` JSON-RPC method). The SDK router consumes this generator.
*   **Alternative (`@a2a_method`):** For agents handling only specific or custom methods, or if you prefer a decorator-based approach, you can use the `@a2a_method` decorator on individual methods instead of implementing all `handle_...` methods (see below).

### 2. Task State Management (`state.py`)

Handling asynchronous tasks requires managing their state (Submitted, Working, Completed, etc.) and potentially associated data (messages, artifacts). The SDK provides tools for this.

*   **`TaskContext`:** A basic dataclass holding `task_id`, `current_state`, `created_at`, `updated_at`. You can subclass this to store agent-specific task data.
    ```python
    # Example of extending TaskContext
    from dataclasses import dataclass, field
    from typing import List
    from agentvault.models import Message, Artifact
    from agentvault_server_sdk.state import TaskContext

    @dataclass
    class MyAgentTaskContext(TaskContext):
        conversation_history: List[Message] = field(default_factory=list)
        generated_artifacts: List[Artifact] = field(default_factory=list)
        # Add other fields your agent needs to track per task
    ```
*   **`BaseTaskStore`:** An abstract base class defining the interface for storing, retrieving, updating, and deleting `TaskContext` objects (e.g., `create_task`, `get_task`, `update_task_state`, `delete_task`). It also defines the interface for managing SSE event listeners (`add_listener`, `remove_listener`) and notifying them (`notify_status_update`, `notify_message_event`, `notify_artifact_event`).
*   **`InMemoryTaskStore`:** A simple, **non-persistent** dictionary-based implementation of `BaseTaskStore`. **Suitable only for development or single-instance agents where task state loss on restart is acceptable.** Production agents typically require implementing a custom `BaseTaskStore` backed by a persistent database (SQL, NoSQL) or a distributed cache (Redis).
*   **Notification Helpers:** When using a `BaseTaskStore` implementation (like `InMemoryTaskStore` or your own), your agent logic (e.g., background processing tasks) should call methods like `task_store.notify_status_update(...)`, `task_store.notify_message_event(...)`, `task_store.notify_artifact_event(...)` whenever a relevant event occurs (e.g., state change, message generation, artifact creation). The `create_a2a_router` integration uses these notifications to automatically format and send the correct SSE events to subscribed clients via the `handle_subscribe_request` stream.

### 3. FastAPI Integration (`fastapi_integration.py`)

The `create_a2a_router` function bridges your agent logic (either a `BaseA2AAgent` subclass or a class using `@a2a_method`) with the FastAPI web framework.

*   **Purpose:** Creates a FastAPI `APIRouter` that automatically exposes the standard A2A JSON-RPC methods (`tasks/send`, `tasks/get`, `tasks/cancel`, `tasks/sendSubscribe`) and routes them to your agent implementation's corresponding `handle_...` methods or decorated methods. It also handles JSON-RPC request parsing, basic validation, and SSE stream setup.
*   **Authentication:** Note that authentication (e.g., checking `X-Api-Key` or `Authorization` headers) is typically handled *before* the request reaches the A2A router, usually via FastAPI Dependencies applied to the router or the main app. The SDK router itself does not perform authentication checks.
*   **Usage:**
    1.  **Instantiate Agent and Task Store:**
        ```python
        from fastapi import FastAPI
        from agentvault_server_sdk import BaseA2AAgent
        from agentvault_server_sdk.state import InMemoryTaskStore # Or your custom store
        # Import your agent class
        from my_agent_logic import MyAgent

        task_store = InMemoryTaskStore()
        my_agent_instance = MyAgent(task_store_ref=task_store) # Pass store if needed
        ```
    2.  **Create the A2A Router:** Pass the agent instance and the task store. Optionally pass `dependencies` (a list of FastAPI `Depends()` calls) to apply authentication/other checks to all A2A routes.
        ```python
        from agentvault_server_sdk import create_a2a_router
        from fastapi import Depends # If adding dependencies

        # Example: Add a dependency (replace with your actual auth logic)
        # async def verify_api_key(x_api_key: str = Header(...)): ...
        # router_deps = [Depends(verify_api_key)]

        a2a_router = create_a2a_router(
            agent=my_agent_instance,
            task_store=task_store, # Required for SSE notifications
            dependencies=[] # Or pass router_deps if needed
        )
        ```
    3.  **Create FastAPI App and Include Router:** Mount the router, typically at `/a2a`.
        ```python
        app = FastAPI(title="My A2A Agent")
        app.include_router(a2a_router, prefix="/a2a") # Standard path
        ```
    4.  **Add Exception Handlers (CRITICAL):** Add the SDK's exception handlers to your main FastAPI `app`. This ensures correct JSON-RPC error formatting.
        ```python
        # (Imports assumed from fastapi_integration.py)
        app.add_exception_handler(TaskNotFoundError, task_not_found_handler)
        app.add_exception_handler(ValueError, validation_exception_handler)
        app.add_exception_handler(TypeError, validation_exception_handler)
        app.add_exception_handler(PydanticValidationError, validation_exception_handler)
        app.add_exception_handler(AgentServerError, agent_server_error_handler)
        app.add_exception_handler(Exception, generic_exception_handler) # Catch-all LAST
        ```

### 4. A2A Method Decorator (`@a2a_method`)

An alternative or supplement to implementing the full `BaseA2AAgent` interface.

*   **Purpose:** Expose individual `async def` methods as specific JSON-RPC methods. Useful for simpler agents or custom methods.
*   **Usage:**
    ```python
    from agentvault_server_sdk import BaseA2AAgent, a2a_method, BaseTaskStore
    from agentvault.models import Task # Example import

    class DecoratedAgent(BaseA2AAgent): # Still inherit for structure

        def __init__(self, task_store: BaseTaskStore):
            self.task_store = task_store # Inject store if needed

        @a2a_method("custom/ping")
        async def ping_handler(self) -> str:
            return "pong"

        @a2a_method("tasks/get") # Override standard method
        # Add BaseTaskStore dependency if method needs it
        async def custom_get_task(self, task_id: str, task_store: BaseTaskStore) -> Task:
            # Params validated from type hints
            task_context = await task_store.get_task(task_id)
            if not task_context: raise TaskNotFoundError(task_id)
            # ... build Task object ...
            return Task(...) # Return value validated

        # No need to implement handle_task_get if decorated method exists
    ```
*   **Validation:** `create_a2a_router` validates incoming `params` against the function's type hints (using Pydantic). Return values are also validated. Standard FastAPI dependencies (like `Header`, `Query`, `Depends`) can be used within decorated methods.

### 5. Packaging Tool (`agentvault-sdk package`) (`packager/cli.py`)

A CLI tool to help prepare your agent project for deployment, typically via Docker.

*   **Command:** `agentvault-sdk package [OPTIONS]`
*   **Functionality:** Generates a standard multi-stage `Dockerfile`, a `.dockerignore` file, and copies `requirements.txt` and optionally `agent-card.json` to a specified output directory.
*   **Key Options:** `--output-dir`, `--entrypoint`, `--python`, `--suffix`, `--port`, `--requirements`, `--agent-card`.
*   **Example:**
    ```bash
    # Assuming FastAPI app is src/my_agent/main.py::app
    agentvault-sdk package -o ./build -e my_agent.main:app -r requirements.txt -c agent-card.json
    # Then build: docker build -t my-agent:latest -f ./build/Dockerfile .
    ```

## Building a Basic Agent (Summary)

1.  **Define Agent Logic:** Subclass `BaseA2AAgent` or use `@a2a_method`.
2.  **Implement Handlers/Methods:** Implement `async handle_...` or decorate methods.
3.  **Manage State:** Choose/implement `BaseTaskStore` (e.g., `InMemoryTaskStore`). Call `notify_...` methods from background tasks.
4.  **Create FastAPI App:** Standard `main.py`.
5.  **Instantiate & Integrate:** Create agent/store instances, use `create_a2a_router`, include in app.
6.  **Add Exception Handlers:** Add SDK handlers to the main `app`.
7.  **Create Agent Card:** Write `agent-card.json` pointing to the `/a2a` endpoint.
8.  **Run/Package:** Use `uvicorn` or `agentvault-sdk package` + `docker build`.

Refer to the [Basic A2A Server Example](../examples/basic_a2a_server.md) and [Stateful Agent Example](../examples/stateful_agent_example.md) for complete implementations.
