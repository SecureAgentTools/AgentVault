# AgentVault: Secure & Interoperable AI Agent Communication

<figure markdown="span">
  ![AgentVault Conceptual Vision](assets/images/AVconceptArt2.png){ width="800" }
  <figcaption>Figure 1: An artistic vision representing the potential of the AgentVault ecosystem.</figcaption>
</figure>

**The AI agent revolution is here, but agents often exist in isolated silos.** How can diverse AI agents discover each other, communicate securely, and collaborate effectively to solve complex problems?

**AgentVault provides the open-source (Apache 2.0) foundational infrastructure layer.** We build the secure, standardized "plumbing" – protocols, tools, and services – enabling a truly interconnected and interoperable multi-agent future.

---

## Unlock Collaborative AI Potential

AgentVault empowers developers and organizations to move beyond isolated AI tools towards sophisticated, collaborative systems.

*   **Problem:** Integrating disparate agents requires custom, brittle code; secure communication and discovery are challenging.
*   **Solution:** AgentVault provides the **standardized rails** for secure discovery ([Registry](developer_guide/registry.md)), communication ([A2A Protocol](architecture/a2a_protocol.md)), and credential management ([KeyManager](guides/key_manager.md)).

---

**➡️ Live Public Registry & UI**

Explore registered agents or manage your own:
*   **Discover Agents (UI):** [`https://agentvault-registry-api.onrender.com/ui`](https://agentvault-registry-api.onrender.com/ui)

*   **Developer Portal (UI):** [`https://agentvault-registry-api.onrender.com/ui/developer`](https://agentvault-registry-api.onrender.com/ui/developer) (Login/Register Here)

*   **Registry API Base:** `https://agentvault-registry-api.onrender.com/api/v1`
*   *(**Note:** Free tier hosting - may take up to 60s to wake up on first request after inactivity. Visit `/health` or the UI first.)*

---

## Why AgentVault? The Infrastructure Layer

AgentVault focuses specifically on providing the essential, secure foundation, complementing higher-level orchestration frameworks.

*   ✨ **Security-First:** From the ground up, with secure local credential management (`KeyManager`), standard authentication protocols, and TEE awareness.
*   🌐 **Interoperable:** Built on open standards (JSON-RPC, SSE) and clear schemas ([Agent Cards](concepts.md#agent-card), [A2A Profile v0.2](architecture/a2a_protocol.md)).
*   🔧 **Integrated Toolkit:** A cohesive set of tools designed for the specific needs of A2A interaction:
    *   **Registry API & UI:** For discovery and developer management.
    *   **Client Library (`agentvault`):** For programmatic interaction.
    *   **Server SDK:** To easily build compliant agents in Python/FastAPI.
    *   **CLI (`agentvault_cli`):** For user and developer command-line access.
*   🔓 **Open Source (Apache 2.0):** Ensuring transparency, flexibility, and no vendor lock-in.

## Core Components (v1.0.0)

*   **[Client Library (`agentvault`)](developer_guide/library.md):** Interact with agents (A2A/MCP), manage keys (`KeyManager`), handle Agent Cards.
*   **[CLI (`agentvault_cli`)](user_guide/cli.md):** Manage credentials, discover agents, run tasks.
*   **[Registry API (`agentvault_registry`)](developer_guide/registry.md):** Central API & Web UI for discovery and developer management.
*   **[Server SDK (`agentvault-server-sdk`)](developer_guide/server_sdk.md):** Build A2A-compliant agents with FastAPI.
*   **[Protocols & Profiles](protocols/):** Definitions for [A2A](architecture/a2a_protocol.md), [MCP (Concept)](architecture/mcp_support.md), and [TEE](tee_profile.md).

## Get Started

*   **New Users:** Check the [Installation Guide](guides/installation.md) and learn the [CLI Commands](user_guide/cli.md).
*   **Developers:** Explore the [Developer Guides](developer_guide/), [Examples](examples.md), and start building with the [Server SDK](developer_guide/server_sdk.md).

## Join the Community

AgentVault is built by the community. We welcome your contributions, feedback, and ideas!

*   **[GitHub Repository](https://github.com/SecureAgentTools/AgentVault)**
*   **[Contributing Guide](CONTRIBUTING.md)**

## License

AgentVault is licensed under the Apache License, Version 2.0. See the [LICENSE](../LICENSE) file in the project root for details.
