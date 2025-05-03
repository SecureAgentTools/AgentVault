# Basic Agent Examples

This page covers several simpler agents designed to demonstrate fundamental concepts and specific features of the AgentVault libraries and SDK.

## Overview

These examples focus on:

*   Basic agent server setup.
*   Direct client library usage.
*   Authentication mechanisms.
*   State management within an agent.
*   Simple agent-to-agent communication.
*   Basic database interaction.
*   Local LLM integration.

## Examples

### 1. Basic A2A Server

*   **Location:** `docs/examples/basic_a2a_server.md` (links to code in `examples/basic_a2a_server`)
*   **Purpose:** Demonstrates the absolute minimal setup required to create an A2A-compliant agent server using FastAPI and the `agentvault-server-sdk`.
*   **Features:**
    *   Inherits from `BaseA2AAgent`.
    *   Implements basic handlers for `tasks/send`, `tasks/get`, `tasks/cancel`, and `tasks/sendSubscribe`.
    *   Uses `create_a2a_router` for automatic endpoint generation.
    *   Includes necessary FastAPI exception handlers.
    *   Serves a minimal `agent-card.json`.
*   **Key Takeaway:** Foundation for building any custom A2A agent.

### 2. Direct Library Usage

*   **Location:** `docs/examples/library_usage_example.md` (links to code in `examples/library_usage_example`)
*   **Purpose:** Shows how to use the `agentvault` client library (`AgentVaultClient`, `KeyManager`) directly in a Python script to interact with an A2A agent without the CLI.
*   **Features:**
    *   Loading an `AgentCard`.
    *   Instantiating `KeyManager` (for potential auth).
    *   Using `AgentVaultClient` within an `async with` block.
    *   Calling `initiate_task`.
    *   Streaming and processing events using `receive_messages`.
    *   Basic exception handling.
*   **Key Takeaway:** How to programmatically control agent interactions from Python code.

### 3. OAuth2 Authenticated Agent

*   **Location:** `docs/examples/oauth_agent_example.md` (links to code in `examples/oauth_agent_example`)
*   **Purpose:** Demonstrates building an agent server that requires OAuth2 Client Credentials authentication.
*   **Features:**
    *   `agent-card.json` specifying the `oauth2` scheme and `/token` endpoint.
    *   Custom `/token` endpoint implementation in FastAPI to validate mock credentials (loaded from `.env`).
    *   FastAPI dependency (`HTTPBearer`) to protect the A2A endpoint, ensuring requests have a valid Bearer token.
    *   Interaction flow showing how the `agentvault` client library automatically handles the OAuth2 token exchange when configured correctly using `agentvault config set ... --oauth-configure`.
*   **Key Takeaway:** Implementing and interacting with OAuth2-protected agents.

### 4. Stateful Agent

*   **Location:** `docs/examples/stateful_agent_example.md` (links to code in `examples/stateful_agent_example`)
*   **Purpose:** Shows how to build an agent that maintains state (like conversation history) across multiple interactions within the *same* task ID.
*   **Features:**
    *   Uses the SDK's `InMemoryTaskStore` (or a custom one) to store task-specific context (e.g., `ChatTaskContext`).
    *   `handle_task_send` logic differentiates between initiating a task (creating context) and continuing a task (updating existing context).
    *   Uses background processing (e.g., `asyncio.Event`, `asyncio.create_task`) to handle ongoing work for a task.
    *   Demonstrates interaction using the CLI with the `--task-id` flag to send subsequent messages.
*   **Key Takeaway:** Managing persistent state within a single agent task lifecycle.

### 5. Task Logger Agent

*   **Location:** `poc_agents/task_logger_agent/`
*   **Purpose:** A simple agent demonstrating database interaction. It receives text messages via A2A and logs them to a PostgreSQL database table (`agent_logs`).
*   **Features:**
    *   Uses `asyncpg` library for asynchronous PostgreSQL communication.
    *   Creates the necessary database table if it doesn't exist.
    *   Takes database connection details from environment variables (`.env` file).
    *   `process_task` method handles the database insertion logic.
*   **Key Takeaway:** Basic agent interaction with an external database.

### 6. Registry Query Agent (LLM Test Mode)

*   **Location:** `poc_agents/registry_query_agent/`
*   **Purpose:** Originally intended to query the AgentVault Registry, this agent was **temporarily modified** to demonstrate interaction with a local LLM (like LM Studio) using an OpenAI-compatible API endpoint. It takes text input and gets a response from the LLM.
*   **Features:**
    *   Uses `httpx` to make asynchronous calls to the configured LLM API endpoint (`LOCAL_API_BASE_URL`).
    *   Handles basic OpenAI-compatible request/response structure (`/chat/completions`).
    *   Takes LLM configuration (URL, model name, API key) from environment variables.
*   **Key Takeaway:** Integrating agents with local or external LLM APIs.

### 7. Simple Summary Agent

*   **Location:** `poc_agents/simple_summary_agent/`
*   **Purpose:** Similar to the modified Registry Query Agent, this agent focuses specifically on text summarization using a local LLM (configured via environment variables).
*   **Features:**
    *   Uses `httpx` for LLM calls.
    *   Includes a specific system prompt geared towards summarization.
    *   Demonstrates basic LLM interaction for a specific task.
*   **Key Takeaway:** Using LLMs within agents for specific NLP tasks.

### 8. Query and Log Agent (Orchestrator)

*   **Location:** `poc_agents/query_and_log_agent/`
*   **Purpose:** A very basic orchestrator agent that demonstrates agent-to-agent communication. It calls the Registry Query Agent (in LLM test mode) and then calls the Task Logger Agent to log the results.
*   **Features:**
    *   Uses `AgentVaultClient` to call other agents.
    *   Loads target agent URLs/IDs from environment variables.
    *   Manages a simple two-step workflow.
*   **Key Takeaway:** Fundamental concept of an agent calling other agents to perform a sequence of actions.

These basic examples provide building blocks and illustrate key techniques used in the more complex end-to-end pipeline POCs.
