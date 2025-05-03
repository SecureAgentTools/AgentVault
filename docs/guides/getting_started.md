# Getting Started Guide

This guide provides a quick start for users and developers looking to use the core AgentVault tools (CLI and Client Library) to find and interact with A2A agents.

## Prerequisites

*   **Python:** Version 3.10 or 3.11.
*   **pip:** Python's package installer.
*   **(Optional but Recommended) OS Keyring Backend:** For secure credential storage (`keyring` library extras might be needed depending on your OS - see [Keyring documentation](https://keyring.readthedocs.io/)).

## 1. Install AgentVault Tools

Install the command-line interface (CLI), which also includes the core client library:

```bash
# Basic installation
pip install agentvault-cli

# Recommended: Install with OS Keyring support
pip install "agentvault-cli[os_keyring]"
```

Verify the installation:

```bash
agentvault_cli --version
# Expected output: agentvault-cli, version X.Y.Z
```

## 2. Discover Agents

The AgentVault Registry acts as a phonebook for agents. You can search it using the CLI. By default, the CLI uses the public registry hosted at `https://agentvault-registry-api.onrender.com`.

*(Note: The public registry runs on a free tier and may take **up to 60 seconds** to respond to the first request after inactivity. You can visit `https://agentvault-registry-api.onrender.com/health` in your browser to wake it up.)*

```bash
# List the first few registered agents
agentvault_cli discover --limit 5

# Search for agents related to "weather"
agentvault_cli discover weather

# Search for agents with specific tags
agentvault_cli discover --tags translation --tags french

# Search for agents declaring TEE support
agentvault_cli discover --has-tee true

# Use a different registry (e.g., a local one)
# agentvault_cli discover --registry http://localhost:8000 weather
```

Take note of the **Agent ID** (e.g., `examples/simple-agent`, `your-org/your-agent`) or the **Agent Card URL** of the agent you want to interact with.

## 3. Configure Credentials (If Required)

Many agents require authentication (like an API key) to use them. The agent's `AgentCard` specifies the required `authSchemes` and often a `service_identifier`. You need to configure the corresponding credential locally using the `agentvault_cli config set` command.

**Example:** Imagine you want to use an agent with ID `some-org/fancy-translator` which requires an API key, and its Agent Card specifies `service_identifier: "fancy_translate_service"`.

1.  **Obtain the API key** from the agent provider (this happens outside AgentVault).
2.  **Store the key securely** using the CLI, associating it with the `service_identifier`:
    ```bash
    # Use the service_identifier from the Agent Card
    agentvault_cli config set fancy_translate_service --keyring

    # The CLI will securely prompt for the key:
    # --> Enter API key for 'fancy_translate_service': ********************
    # --> Confirm API key: ********************
    # SUCCESS: API key for 'fancy_translate_service' stored successfully in keyring.
    ```

*   For agents requiring **OAuth2 Client Credentials**, use the `--oauth-configure` flag instead:
    ```bash
    agentvault_cli config set some-oauth-service --oauth-configure
    # --> Enter OAuth Client ID...
    # --> Enter OAuth Client Secret...
    # --> Confirm OAuth Client Secret...
    ```
*   Always use the **OS Keyring (`--keyring`, `--oauth-configure`)** whenever possible for maximum security.
*   Refer to the [KeyManager Guide](key_manager.md) for details on sources and priority.

## 4. Run a Task

Now you can interact with the agent using the `agentvault_cli run` command.

```bash
# --- Using an Agent ID (fetches card from registry) ---

# Agent requires NO authentication
agentvault_cli run --agent examples/simple-agent --input "Hello there!"

# Agent requires API Key (assuming key for 'fancy_translate_service' was configured above)
agentvault_cli run --agent some-org/fancy-translator --input "Translate 'hello' to French."

# Agent requires API Key, but card didn't specify service_identifier OR
# you stored the key under a different local name (e.g., 'my_fancy_key')
# agentvault_cli run --agent some-org/fancy-translator --input "Translate..." --key-service my_fancy_key

# --- Using a direct Agent Card URL ---
# (Authentication still handled via KeyManager based on card's authSchemes)
agentvault_cli run --agent http://localhost:8000/agent-card.json --input "Ping!"

# --- Using a local Agent Card file ---
agentvault_cli run --agent ./path/to/local-agent-card.json --input "Local test."

# --- Reading input from a file ---
echo "This is my input text." > input.txt
agentvault_cli run --agent some-org/fancy-translator --input @input.txt

# --- Saving Artifacts ---
# (If the agent produces artifacts like files)
mkdir agent_output
agentvault_cli run --agent some-org/file-generator --input "Create report" --output-artifacts ./agent_output
```

The CLI will:

1.  Fetch the Agent Card (if an ID is provided).
2.  Determine the required authentication using the card's `authSchemes`.
3.  Use `KeyManager` to retrieve the necessary credentials (using `service_identifier` from the card or the `--key-service` flag).
4.  Connect to the agent's A2A endpoint (`url` from the card).
5.  Initiate the task (`tasks/send`).
6.  Stream results (status updates, messages, artifacts) back to your terminal using Server-Sent Events (SSE).

## Next Steps

*   **Explore CLI Commands:** Use `agentvault_cli [command] --help` for detailed options.
*   **Manage Credentials:** Learn more about `agentvault_cli config` in the [KeyManager Guide](key_manager.md).
*   **Use the Library:** Integrate agent interactions into your Python applications using the [Client Library Guide](client_library.md).
*   **Build Your Own Agent:** Refer to the [Server SDK Guide](server_sdk.md).
*   **Discover More Agents:** Use `agentvault_cli discover` or browse the [Public Registry UI](https://agentvault-registry-api.onrender.com/ui).
