# AgentVault Architecture Overview

AgentVault is designed as a modular ecosystem to provide the foundational infrastructure for secure and interoperable Agent-to-Agent (A2A) communication. It focuses on discovery, standardized communication protocols, and secure credential management, acting as the "plumbing" layer upon which complex multi-agent systems can be built.

## Core Components

The ecosystem consists of several distinct but interconnected Python packages and services:

1.  **`agentvault_library` (Core Client Library):**
    *   **Purpose:** The foundation for any client-side interaction (CLI, custom apps, other agents).
    *   **Contains:** `AgentVaultClient` (A2A/SSE/Auth logic), `KeyManager` (secure local credential storage), Pydantic models (`AgentCard`, `Message`, `Task`, etc.), `agent_card_utils`, `mcp_utils`.
    *   **Key Feature:** Abstracts the complexities of A2A communication and authentication.

2.  **`agentvault_cli` (Command Line Interface):**
    *   **Purpose:** Primary user/developer tool for terminal interaction.
    *   **Contains:** Commands wrapping library functions (`config`, `discover`, `run`).
    *   **Key Feature:** Provides easy access to discovery, task execution, and secure credential configuration via `KeyManager`.

3.  **`agentvault_registry` (Registry API & UI):**
    *   **Purpose:** The central discovery hub. Stores and serves standardized `AgentCard` metadata. **It does not execute agents.**
    *   **Contains:** FastAPI backend, PostgreSQL database (via SQLAlchemy/asyncpg), Alembic migrations, Public REST API (`/api/v1`), Developer Portal UI (`/ui/developer`), Public Discovery UI (`/ui`).
    *   **Key Features:** Agent Card validation, developer authentication (JWT for UI/API, Programmatic API Keys), search/filtering capabilities (including tags, TEE), email verification, rate limiting.

4.  **`agentvault_server_sdk` (Server SDK):**
    *   **Purpose:** Toolkit for developers *building* A2A-compliant agents.
    *   **Contains:** `BaseA2AAgent` abstract class, FastAPI integration helpers (`create_a2a_router`, `@a2a_method`), task state management abstractions (`BaseTaskStore`, `InMemoryTaskStore`), packaging utility (`agentvault-sdk package`).
    *   **Key Feature:** Simplifies adherence to the A2A protocol and integration with FastAPI.

5.  **`agentvault_testing_utils` (Internal Testing Utilities):**
    *   **Purpose:** Shared mocks (`MockAgentVaultClient`), pytest fixtures (`mock_a2a_server`), factories, and helpers for internal testing across the monorepo.
    *   **Contains:** Tools to simulate A2A interactions and agent behavior during tests.
    *   **Key Feature:** Ensures consistent and efficient testing of interconnected components.

## High-Level Interaction Flow

```mermaid
graph LR
    subgraph UserClient [User / Client Application]
        User[User] -->|Uses| CLI(agentvault_cli);
        CLI -->|Uses| Lib(agentvault_library);
        User -->|Can Use Directly| Lib;
        Lib -->|Manages Keys| KeyStore[(Local Credential Store\nEnv/File/Keyring)];
    end

    subgraph DeveloperSide [Agent Developer]
        Dev[Developer] -->|Uses| SDK(agentvault_server_sdk);
        SDK -.->|Builds| AgentServer(A2A Agent Server);
        Dev -->|Registers & Manages via UI/API| RegistryAPI(Registry API /api/v1);
        RegistryAPI -->|Requires Dev Auth (JWT / API Key)| DevLogin(Developer Login);
    end

    subgraph CentralRegistry [Central Registry Service]
        RegistryAPI -->|Stores/Retrieves| DB[(Registry DB\nCards & Dev Hashes)];
        RegistryAPI -->|Serves UI| RegistryUI(Registry Web UI /ui /ui/developer);
        User -->|Browses Discovery| RegistryUI;
        Dev -->|Uses Developer Portal| RegistryUI;
    end

    subgraph CommunicationFlow [Communication Paths]
        Lib -->|1. Discover Agent\n(Public API)| RegistryAPI;
        Lib -->|2. Get AgentCard\n(Public API)| RegistryAPI;
        Lib -->|3. Run Task\n(A2A Protocol via HTTPS)| AgentServer;
        AgentServer -->|Optional: Uses SDK/External Services| ExternalService[External APIs];
    end

    style KeyStore stroke-dasharray: 5 5;
    style DevLogin stroke-dasharray: 5 5;
```

**Flow Explanation:**

1.  **Discovery:** A Client (using the Library or CLI) queries the **Registry API**'s public endpoints or browses the public **Web UI** to find suitable agents based on search criteria, tags, or capabilities like TEE support.
2.  **Card Retrieval:** The Client retrieves the **Agent Card** for the desired agent from the **Registry API** (public endpoint).
3.  **Interaction:**
    *   The Client uses the `url` and `authSchemes` from the Agent Card.
    *   The **Library**'s `KeyManager` loads the necessary local credentials based on the `service_identifier` (or other logic).
    *   The **Library**'s `AgentVaultClient` sends A2A requests (HTTPS POST with JSON-RPC) directly to the **Agent Server**, automatically handling authentication (e.g., adding `X-Api-Key` or fetching/adding `Authorization: Bearer` token).
    *   If subscribing (`tasks/sendSubscribe`), the `AgentVaultClient` handles the SSE connection.
4.  **Agent Server Processing:** The **Agent Server** (likely built with the **SDK**) receives the request, validates authentication (if required), processes the task (potentially interacting with external services), manages state, and sends responses/SSE events back to the client.
5.  **Developer Management:** The **Developer** uses the **Developer Portal UI** or **Registry API** (authenticating via JWT or programmatic API Key) to submit, update, or deactivate their Agent Cards and manage their API keys. The Registry validates cards and stores them in the **Registry DB** along with hashed developer credentials/keys.

## Architectural Positioning

AgentVault provides the foundational **infrastructure layer** for secure A2A communication and discovery. It is designed to:

*   **Complement Orchestration Frameworks:** Tools like LangGraph, CrewAI, Autogen can leverage AgentVault's client library to securely interact with diverse, discoverable external agents using a standard protocol, rather than implementing custom integrations for each agent.
*   **Prioritize Security & Interoperability:** Focuses on secure credential handling (`KeyManager`, hashed storage, standard auth schemes) and standardized communication (A2A Profile, Agent Cards) as first-class concerns.
*   **Be Open and Flexible:** The Apache 2.0 license and modular design prevent vendor lock-in and allow integration into various architectures.
*   **Serve the Python Ecosystem:** Provides native Python tools for both client-side interaction and server-side agent development.

It is *not* intended to be an all-in-one agent platform but rather the reliable, secure plumbing that enables such platforms and more complex multi-agent systems to flourish.
