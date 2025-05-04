# Installation

This guide covers how to install the different components of the AgentVault framework.

## Prerequisites

*   **Python:** Version 3.10 or higher is recommended.
*   **pip:** Python's package installer.
*   **Poetry (Recommended):** For development and managing dependencies within individual component repositories (`poetry install`).
*   **Docker & Docker Compose:** Required for running the AgentVault Registry and containerized agents/POC pipelines.
*   **Git:** For cloning the repository.
*   **(Optional) OS Keyring Backend:** If using the `KeyManager` with the OS keyring (`use_keyring=True`), ensure a supported backend is installed (e.g., `keyrings.cryptfile`, `keyrings.osx`, `keyrings.windows`).

## Core Library (`agentvault`)

This library provides the client (`AgentVaultClient`), models, key management (`KeyManager`), and utilities needed to interact with AgentVault agents and potentially the registry.

```bash
# Install from PyPI (once published)
# pip install agentvault

# Install locally from source (for development)
cd agentvault_library
poetry install
# Or using pip editable mode from the monorepo root:
# pip install -e agentvault_library
```

*   **Optional Keyring:** To enable storing credentials in the OS keyring:
    ```bash
    # When using pip:
    pip install agentvault[os_keyring]
    # When using poetry:
    poetry install --extras os_keyring
    ```

## Server SDK (`agentvault-server-sdk`)

This SDK helps you build your own A2A-compliant agents.

```bash
# Install from PyPI (once published)
# pip install agentvault-server-sdk

# Install locally from source (for development)
cd agentvault_server_sdk
poetry install
# Or using pip editable mode from the monorepo root:
# pip install -e agentvault_server_sdk
```

## Command Line Interface (`agentvault-cli`)

The CLI provides commands for discovering agents, running tasks, and managing local configuration.

```bash
# Install from PyPI (once published)
# pip install agentvault-cli

# Install locally from source (for development)
cd agentvault_cli
poetry install
# Or using pip editable mode from the monorepo root:
# pip install -e agentvault_cli

# Verify installation
agentvault --version
```

## AgentVault Registry (`agentvault_registry`)

The registry is a central service for agent discovery. It requires Docker and Docker Compose.

**Setup Instructions:**

Detailed instructions for building the Docker image, configuring the `.env` file (database connection, admin user, secrets), and running the registry service using `docker compose` can be found in the **[Registry Setup & API Guide](developer_guide/registry.md#running-with-docker-recommended)**.

## Testing Utilities (`agentvault-testing-utils`)

This package provides utilities for testing agents and components within the AgentVault ecosystem. It's typically installed as a development dependency.

```bash
# Install locally from source (for development)
cd agentvault_testing_utils
poetry install
# Or using pip editable mode from the monorepo root:
# pip install -e agentvault_testing_utils
```

## Proof-of-Concept (POC) Agents & Pipelines

The various POC pipelines (Research, Support, ETL, etc.) have their own setup instructions within their respective directories under `poc_agents/`. Generally, they involve:

1.  Navigating to the specific POC directory (e.g., `cd poc_agents/research_pipeline`).
2.  Configuring `.env` files for the agents and orchestrator within that POC.
3.  Using `docker compose build` and `docker compose up -d` (or specific build/run scripts provided within the POC directory).

Refer to the `README.md` or documentation within each POC directory for specific setup steps.
