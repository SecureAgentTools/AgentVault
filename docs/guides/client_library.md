# Developer Guide: Client Library (`agentvault`)

The `agentvault` library is the core Python package for interacting with the AgentVault ecosystem from the client-side. It enables applications, scripts, or even other agents to discover A2A agents, manage credentials securely, and communicate using the A2A protocol.

## Installation

Install the library from PyPI:

```bash
pip install agentvault
```

For optional OS Keyring support (recommended for secure credential storage):

```bash
pip install "agentvault[os_keyring]"
```

See the main [Installation Guide](../installation.md) for more details, including setting up a development environment.

## Key Components

### `KeyManager` (`key_manager.py`)

Handles secure loading, storage, and retrieval of credentials (API keys, OAuth 2.0 Client ID/Secret) needed for agent authentication.

*   **Purpose:** Abstracts credential sources so your client code doesn't need to handle each case explicitly. Provides a consistent interface (`get_key`, `get_oauth_client_id`, etc.) regardless of where the credential is stored.
*   **Initialization:**
    ```python
    from agentvault import KeyManager
    import pathlib

    # Recommended: Load from environment variables AND OS keyring (if available)
    # Keyring is checked only if the key isn't found in env vars first.
    km_env_keyring = KeyManager(use_keyring=True)

    # Load ONLY from a specific .env file (disable env vars and keyring)
    # key_file_path = pathlib.Path("path/to/your/keys.env")
    # km_file_only = KeyManager(key_file_path=key_file_path, use_env_vars=False, use_keyring=False)

    # Load from file AND environment (file takes priority over env)
    # key_file_path = pathlib.Path("path/to/your/keys.json")
    # km_file_env = KeyManager(key_file_path=key_file_path, use_env_vars=True, use_keyring=False)
    ```
*   **Priority Order:** File Cache -> Environment Variable Cache -> OS Keyring (on demand).
*   **Service Identifier (`service_id`):** The local alias used to look up credentials (e.g., "openai", "my-custom-agent"). Often corresponds to `AgentCard.authSchemes[].service_identifier`.
*   **Storage Conventions:** See the [KeyManager Guide](key_manager.md) for details on environment variable patterns, file formats (`.env`, `.json`), and keyring service names.
*   **Retrieving Credentials:**
    ```python
    km = KeyManager(use_keyring=True) # Example instance

    # Get API Key (returns None if not found)
    api_key = km.get_key("openai")
    if api_key:
        source = km.get_key_source("openai") # 'env', 'file', 'keyring', or None
        print(f"Found OpenAI API Key (Source: {source})")

    # Get OAuth Credentials (return None if not found or incomplete)
    client_id = km.get_oauth_client_id("google-oauth-agent")
    client_secret = km.get_oauth_client_secret("google-oauth-agent")
    if client_id and client_secret:
        status = km.get_oauth_config_status("google-oauth-agent")
        print(f"Found Google OAuth Credentials ({status})")
        print(f"  Client ID: {client_id}")
        # Note: AgentVaultClient uses these to automatically fetch the Bearer token.
    ```
*   **Storing Credentials (Primarily for CLI/Setup):** Use `km.set_key_in_keyring(...)` or `km.set_oauth_creds_in_keyring(...)`. Requires `use_keyring=True`.

*(See [KeyManager Guide](key_manager.md) for full details)*

### `AgentVaultClient` (`client.py`)

The primary class for making asynchronous A2A calls to remote agents.

*   **Purpose:** Handles HTTP requests (using `httpx`), authentication logic (including OAuth2 Client Credentials token fetching/caching), JSON-RPC formatting, SSE streaming, and response parsing according to the [A2A Profile v0.2](../architecture/a2a_protocol.md).
*   **Usage:** Best used as an async context manager (`async with`) to ensure the underlying HTTP client is properly closed. Requires an `AgentCard` instance (loaded via `agent_card_utils`) and a `KeyManager` instance for authentication.

*   **Key Methods:**
    *   **`initiate_task(...)`**: Starts a new task.
        *   `agent_card`: Target `AgentCard` object.
        *   `initial_message`: `Message` object with initial input.
        *   `key_manager`: `KeyManager` instance.
        *   `mcp_context` (Optional): Dictionary for Model Context Protocol data.
        *   `webhook_url` (Optional): URL for push notifications (if agent supports).
        *   **Returns:** `str` (the unique Task ID).
    *   **`send_message(...)`**: Sends a follow-up message to an existing task.
        *   `agent_card`, `task_id`, `message`, `key_manager`, `mcp_context` (Optional).
        *   **Returns:** `bool` (True on acknowledgement, raises error otherwise).
    *   **`get_task_status(...)`**: Retrieves the full state of a task.
        *   `agent_card`, `task_id`, `key_manager`.
        *   **Returns:** `Task` object.
    *   **`terminate_task(...)`**: Requests cancellation of a task.
        *   `agent_card`, `task_id`, `key_manager`.
        *   **Returns:** `bool` (True if request acknowledged).
    *   **`receive_messages(...)`**: Subscribes to and yields Server-Sent Events (SSE) for a task.
        *   `agent_card`, `task_id`, `key_manager`.
        *   **Returns:** `AsyncGenerator[A2AEvent, None]` (yields `TaskStatusUpdateEvent`, `TaskMessageEvent`, `TaskArtifactUpdateEvent`, or potentially error dicts).

*   **Example:**
    ```python
    import asyncio
    import logging
    from agentvault import (
        AgentVaultClient, KeyManager, Message, TextPart,
        agent_card_utils, exceptions as av_exceptions, models as av_models
    )

    logging.basicConfig(level=logging.INFO)

    async def run_agent_task(agent_ref: str, input_text: str):
        key_manager = KeyManager(use_keyring=True)
        agent_card = None
        task_id = None

        try:
            # --- 1. Load Agent Card (Use appropriate util) ---
            agent_card = await agent_card_utils.fetch_agent_card_from_url(agent_ref)
            if not agent_card: raise ValueError("Card not found")

            # --- 2. Prepare Initial Message ---
            initial_message = Message(role="user", parts=[TextPart(content=input_text)])

            # --- 3. Interact using AgentVaultClient ---
            async with AgentVaultClient() as client:
                print("Initiating task...")
                task_id = await client.initiate_task(
                    agent_card=agent_card, initial_message=initial_message, key_manager=key_manager
                )
                print(f"Task initiated: {task_id}")

                print("Streaming events...")
                async for event in client.receive_messages(
                    agent_card=agent_card, task_id=task_id, key_manager=key_manager
                ):
                    # Process different event types
                    if isinstance(event, av_models.TaskStatusUpdateEvent):
                        print(f"  Status: {event.state}")
                        if event.state.is_terminal(): break
                    elif isinstance(event, av_models.TaskMessageEvent):
                        if event.message.role == "assistant":
                            for part in event.message.parts:
                                if isinstance(part, TextPart): print(f"  Assistant: {part.content}")
                    # Add handling for TaskArtifactUpdateEvent, errors etc.
                    else:
                        print(f"  Other Event: {type(event)}")

                print("Stream finished.")

        except av_exceptions.AgentVaultError as e: # Catch base AgentVault errors
            print(f"AgentVault Error: {e}")
        except Exception as e:
            print(f"Unexpected Error: {e}")

    # Example: asyncio.run(run_agent_task("http://localhost:8000/agent-card.json", "Hello"))
    ```

### Models (`agentvault.models`)

Pydantic models defining the data structures for Agent Cards (`AgentCard`, `AgentProvider`, etc.) and the A2A protocol (`Message`, `Part`, `Task`, `TaskState`, `A2AEvent`, etc.). Refer to the source code docstrings or the [A2A Profile v0.2](../architecture/a2a_protocol.md) for details.

### Exceptions (`agentvault.exceptions`)

Custom exceptions provide granular error handling. Catching these allows for more robust client applications. Key exceptions include:

*   `AgentCardError`, `AgentCardValidationError`, `AgentCardFetchError`
*   `A2AError`, `A2AConnectionError`, `A2AAuthenticationError`, `A2ARemoteAgentError`, `A2ATimeoutError`, `A2AMessageError`
*   `KeyManagementError`

See the `AgentVaultClient` example above and the `exceptions.py` source for details.

### Utilities (`agentvault.agent_card_utils`, `agentvault.mcp_utils`)

*   **`agent_card_utils`**: Functions (`load_agent_card_from_file`, `fetch_agent_card_from_url`, `parse_agent_card_from_dict`) to obtain and validate `AgentCard` objects.
*   **`mcp_utils`**: Helpers for handling Model Context Protocol data.
    *   `format_mcp_context`: Validates and formats a dictionary for embedding into `message.metadata["mcp_context"]`.
    *   `get_mcp_context`: Safely extracts the `mcp_context` dictionary from a received `Message`.
