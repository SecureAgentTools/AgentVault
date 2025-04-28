
# AgentVault Project Roadmap

This document outlines the planned development phases and features for the AgentVault ecosystem. Our goal is to create a secure, interoperable, and easy-to-use platform for AI agent communication based on open standards like A2A and MCP concepts.

*Disclaimer: This roadmap represents our current plans and priorities. It is subject to change based on development progress, community feedback, and the evolution of underlying standards.*

## Current Status (April 2025 - Phase 2.5 Underway)

The AgentVault project has established a functional baseline across its core components and is actively refining the ecosystem based on initial implementation and usability testing.

*   **`agentvault` Library:** Core client implemented (A2A JSON-RPC/SSE, Auth Schemes, KeyManager, Models, Utils). Published.
*   **`agentvault_registry` API & UI:** Operational API (Card CRUD, Validation, Discovery Filters incl. TEE/Tags). **New:** Developer authentication via email/password (JWT), email verification, recovery keys, programmatic API key management (`/developers/me/apikeys`), Agent Builder endpoint (`/agent-builder/generate`). Web UI for public discovery (`/ui`) and developer portal (`/ui/developer`) with login/register/recovery flows implemented. Uses PostgreSQL/Alembic. Rate limiting/CORS active. *(Note: Email sending depends on deployment configuration).*
*   **`agentvault_cli`:** Functional CLI (`config`, `discover`, `run`). Supports KeyManager (keyring, oauth config), SSE streaming, artifact saving.
*   **`agentvault_server_sdk`:** Foundational SDK (`BaseA2AAgent`, FastAPI integration, `@a2a_method`, `InMemoryTaskStore` with notifications), packaging tool (`agentvault-sdk package`). Published.
*   **`agentvault_testing_utils`:** Shared utilities (`MockAgentVaultClient`, `mock_a2a_server` fixture, factory, `EchoAgent`, assertions).
*   **Examples:** Basic Server, LangChain Tool, OAuth Agent, Stateful Agent, Library Usage examples available.
*   **Documentation:** Structure established, core concepts/architecture/security documented, component guides drafted, A2A/TEE profiles documented, examples included. Deployed via GitHub Pages.
*   **CI/CD:** Dependency audit and docs deployment workflows functional.

## Next Steps: Phase 2.6 - Automation, Robustness & Polish

**Objective:** Complete automation scripts, improve robustness (testing, error handling, scalability), and polish the developer/user experience.

**Key Tasks:**

1.  **Automation Scripts:**
    *   **TODO:** Finalize and test `automation_scripts/` (`av_create_package_agent`, `av_deploy_register_agent`, `av_find_run_task`). Ensure they work reliably with the latest components.
    *   **TODO:** Refine agent template generation (e.g., better `.env` setup based on selected options).
3.  **Registry Enhancements:**
    *   **TODO:** Investigate and potentially optimize developer programmatic API key lookup performance if needed for scale.
    *   **TODO:** Implement email-based password reset flow (currently placeholder).
    *   **TODO:** Further UI/UX improvements for the Developer Portal (e.g., easier card editing interface, clearer API key management).
4.  **SDK & Error Handling:**
    *   **TODO:** Provide examples or interfaces for persistent `BaseTaskStore` implementations (e.g., Redis, SQL).
    *   **TODO:** Review and standardize error handling and logging across all components for consistency.
5.  **Documentation Polish:**
    *   **TODO:** Add more diagrams where helpful (e.g., auth flows).
    *   **TODO:** Review all guides for clarity and accuracy against latest code.

## Future Considerations (Phase 3 & Beyond)

**Objective:** Expand AgentVault into a comprehensive, enterprise-ready platform for secure, scalable, and truly intelligent multi-agent collaboration across diverse environments.

**Key Areas:**

1.  **Federated Registry & Discovery:**
    *   Design and implement protocols for secure, policy-based discovery between independent AgentVault Registry instances (private enterprise, partner, public).
    *   Develop mechanisms for establishing and managing trust relationships between registries.
    *   Enhance Agent Cards to support federation metadata and cross-domain policies.
2.  **AgentVault Identity Fabric (Zero Trust IAM for Agents):**
    *   **Goal:** Implement a robust, fine-grained Identity and Access Management system specifically for agents, complementing existing user IAM (like Entra ID).
    *   **Agent Identity (SPIFFE/SPIRE):** Integrate SPIFFE/SPIRE for issuing verifiable, short-lived cryptographic identities (SVIDs) to agent workloads, enabling strong mTLS authentication for A2A.
    *   **Capability-Based Authorization (OAuth2 Scopes/Token Exchange):** Define granular permission scopes based on agent capabilities (from Agent Cards). Implement OAuth 2.0 Token Exchange flows to issue delegated, capability-scoped tokens for agent interactions, enforcing the Principle of Least Privilege.
    *   **Policy Engine Integration (OPA):** Integrate Open Policy Agent (OPA) for decoupled, dynamic authorization decisions based on agent identity, user context, requested capabilities, and custom enterprise policies (Rego).
    *   **Secure Context Propagation:** Define standardized methods for securely passing necessary user and call-chain context between agents.
    *   **Synergy:** This Identity Fabric provides the necessary security primitives for secure and scalable Federated Registry interactions.
3.  **Enhanced A2A/MCP Capabilities:**
    *   **Multimodality (WebRTC):** Integrate `aiortc` or similar libraries for optional real-time audio/video streaming capabilities within the A2A framework.
    *   **Deeper MCP Integration:** Fully align with finalized Model Context Protocol specifications, providing robust SDK helpers for standardized tool use and context passing.
4.  **Advanced Security & Trust:**
    *   **TEE Attestation Verification:** Implement client-side cryptographic verification of Trusted Execution Environment attestations declared in Agent Cards.
    *   **Key Rotation & Management:** Enhanced features for managing registry API keys and potentially agent-level credentials.
    *   **Formal Security Audits:** Engage third-party experts for comprehensive security reviews of the core framework and protocols.
5.  **Ecosystem & Usability:**
    *   **Persistent Task Stores:** Provide robust, production-ready `BaseTaskStore` implementations (e.g., Redis, SQL database).
    *   **UI Enhancements:** Improve Agent Builder capabilities, add registry analytics/monitoring dashboards.
    *   **Other Language SDKs/Libraries:** Explore SDKs for other popular languages like Node.js, Go, etc., based on community demand.
    *   **Community Features:** Implement features like agent reviews/ratings within the registry.

## Contributing

We welcome community contributions! Please see our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
