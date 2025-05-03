# AgentVault Concepts

This document outlines the core concepts behind the AgentVault framework.

## Vision

AgentVault aims to enable secure, auditable, and collaborative interactions between autonomous AI agents, specialized tools, and human operators. It focuses on:

1.  **Security:** Ensuring agents operate within defined boundaries and data is handled securely, potentially leveraging Trusted Execution Environments (TEEs).
2.  **Interoperability:** Defining standard protocols (A2A, MCP) for seamless communication between different agents and tools.
3.  **Orchestration:** Facilitating complex workflows involving multiple agents and tools.
4.  **Auditability:** Providing mechanisms for logging and reviewing agent interactions.
5.  **Discovery:** Allowing agents and users to find and understand the capabilities of available agents via a Registry.

## Key Components

1.  **Agent:** An autonomous entity capable of performing tasks, communicating via defined protocols, and potentially utilizing specialized tools or models. Agents advertise their capabilities via an **Agent Card**.
2.  **Agent Card:** A standardized metadata document (JSON format) describing an agent's identity, capabilities, endpoints, authentication requirements, provider information, and skills. It's the primary mechanism for agent discovery.
3.  **Agent-to-Agent (A2A) Protocol:** The primary communication protocol between AgentVault agents and clients/orchestrators. It uses JSON-RPC 2.0 over HTTP(S) and supports Server-Sent Events (SSE) for real-time, asynchronous updates (e.g., task status, messages, artifacts). Defines standard methods like `tasks/send`, `tasks/get`, `tasks/cancel`, `tasks/sendSubscribe`.
4.  **Model Context Protocol (MCP):** (Revised based on POC)
    *   **Definition:** The Model Context Protocol (MCP) provides a standardized interface for AgentVault components (orchestrators, agents) to discover and execute external **Tools**. It facilitates interaction with capabilities that might reside outside the core A2A agent network, such as code execution environments, filesystem access, or specialized APIs.
    *   **Mechanism:** MCP utilizes **JSON-RPC 2.0** over HTTP(S) as its communication layer. It defines conventions for:
        *   Tool Naming (e.g., `namespace.toolName` like `filesystem.readFile`).
        *   Request `params` structure for tool arguments.
        *   Response `result` structure, including standardized `content` arrays and an optional `isError` flag for tool-level errors.
    *   **Integration Pattern:** AgentVault currently recommends integrating MCP tools into an A2A workflow using a dedicated **MCP Tool Proxy Agent**. This A2A-compliant agent receives requests specifying the target tool and arguments, translates them into MCP JSON-RPC calls to the appropriate tool server, and relays the results back to the A2A caller.
    *   **Status & Example:** The protocol is defined and functional. The **[MCP Test Pipeline Example](./examples/poc_mcp_pipeline.md)** provides a working demonstration of this proxy pattern, interacting with custom Python-based MCP servers for filesystem operations and code execution. While direct client-side MCP support in the `agentvault` library may be enhanced in the future, the protocol itself and the proxy architecture are ready for use.
    *   **Goal:** Enable standardized, reusable access to a wide range of external capabilities within the AgentVault ecosystem.
5.  **Tool Server:** A separate service (potentially non-A2A compliant itself) that exposes specific capabilities (e.g., code execution, database query, filesystem access) via the **MCP protocol**.
6.  **AgentVault Registry:** A central service where agents can publish their Agent Cards, allowing users and other agents to discover them based on ID, capabilities, or tags.
7.  **Orchestrator:** A component (human script, LangGraph workflow, or another agent) responsible for coordinating tasks across multiple agents and tools to achieve a larger goal.
8.  **Client Library (`agentvault`):** Python library providing tools for interacting with agents (A2A), managing local keys (`KeyManager`), and potentially interacting with the Registry.
9.  **Server SDK (`agentvault-server-sdk`):** Python SDK to simplify the creation of A2A-compliant agent servers, often integrating with web frameworks like FastAPI.
10. **Trusted Execution Environment (TEE) Profile:** (Conceptual) A specification for how agents can leverage TEEs (like Intel SGX, AMD SEV) for enhanced security and verifiable computation, including attestation mechanisms.

## Core Interactions

*   **Discovery:** Client/Orchestrator queries the Registry to find an agent suitable for a task based on its Agent Card.
*   **A2A Task Initiation:** Client sends an initial message to the agent's A2A endpoint (`tasks/send`) to start a task.
*   **A2A Event Streaming:** Client subscribes (`tasks/sendSubscribe`) to the agent's SSE stream to receive real-time updates (status changes, messages, artifacts).
*   **A2A Tool Usage (via MCP Proxy):**
    1.  Orchestrator sends an A2A task to the MCP Tool Proxy Agent, specifying the target MCP server ID, tool name, and arguments.
    2.  Proxy Agent sends a standard MCP JSON-RPC request to the target Tool Server.
    3.  Tool Server executes the tool and returns an MCP JSON-RPC response.
    4.  Proxy Agent translates the MCP response into an A2A result/artifact and sends it back to the orchestrator.
*   **State Management:** Agents manage the state of their tasks internally (e.g., using the Server SDK's `TaskStore`). Orchestrators manage the overall pipeline state.

This framework provides a flexible and secure foundation for building complex, collaborative AI systems.
