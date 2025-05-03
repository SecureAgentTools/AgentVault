# AgentVault Security Concepts

> **Note:** For the official security policy and vulnerability reporting process, please see the [Security Policy](../security_policy.md) document.

Security is a core design principle of AgentVault. This document details the security mechanisms, considerations, and best practices implemented across the ecosystem to facilitate trustworthy interactions between agents and protect user/developer credentials.

## 1. Client-to-Agent Authentication (A2A)

The communication between an AgentVault client (like the CLI or library) and an A2A agent server must be properly authenticated if the agent requires it. Agents declare their supported authentication methods in the `authSchemes` array within their `AgentCard`.

**Supported Schemes (by `agentvault` library v0.2.x):**

*   **`none`:**
    *   **Mechanism:** No authentication headers are sent.
    *   **Use Case:** Suitable only for public agents handling non-sensitive data or actions where identity is irrelevant.
    *   **Security:** Offers no protection against unauthorized access.

*   **`apiKey`:**
    *   **Mechanism:** The client sends a pre-shared secret API key in the `X-Api-Key` HTTP header.
    *   **Client-Side:** The `agentvault` library uses `KeyManager` to retrieve the appropriate API key based on the `service_identifier` specified in the agent's card (or a user override). Secure storage via OS Keyring is recommended (`agentvault config set <service_id> --keyring`).
    *   **Server-Side:** The agent server (built potentially with `agentvault-server-sdk`) must implement logic (e.g., a FastAPI dependency) to receive the `X-Api-Key` header, validate the key against its securely stored keys/hashes, and authorize the request.
    *   **Security:** Relies on the secrecy of the API key. Keys should be treated as sensitive credentials.

*   **`oauth2` (Client Credentials Grant Flow):**
    *   **Mechanism:** Standard OAuth 2.0 flow where the client authenticates itself (not an end-user) to the agent's token endpoint to obtain a short-lived Bearer token.
    *   **Agent Card Requirements:** Must include `scheme: "oauth2"` and a valid `tokenUrl`. Can optionally include `scopes`.
    *   **Client-Side:**
        1.  `AgentVaultClient` identifies the `oauth2` scheme and `tokenUrl`.
        2.  It uses `KeyManager` to retrieve the *client's* Client ID and Client Secret associated with the agent's `service_identifier`. Secure storage via OS Keyring is recommended (`agentvault config set <service_id> --oauth-configure`).
        3.  The client POSTs `grant_type=client_credentials`, `client_id`, and `client_secret` (and optional `scope`) to the agent's `tokenUrl`.
        4.  It receives an `access_token` and caches it (respecting `expires_in` if provided).
        5.  For subsequent A2A requests to the agent's main `url`, the client includes the `Authorization: Bearer <access_token>` header.
    *   **Server-Side:**
        1.  The agent server must host the `/token` endpoint specified in its card. This endpoint validates the received `client_id` and `client_secret` and issues signed, short-lived JWT Bearer tokens.
        2.  The agent's main `/a2a` endpoint must include a dependency (like FastAPI's `HTTPBearer` or a custom one) to validate the incoming `Authorization: Bearer <token>` (checking signature, expiry, audience, scopes).
    *   **Security:** Considered more secure than static API keys for server-to-server communication as it uses short-lived tokens and standard flows. Relies on secure storage of Client ID/Secret on the client and secure token validation on the server.

*   **`bearer`:**
    *   **Mechanism:** The client sends a pre-existing Bearer token (obtained through means external to the AgentVault client library, e.g., a user login flow) in the `Authorization: Bearer <token>` header.
    *   **Client-Side:** The `AgentVaultClient` does *not* manage the lifecycle of these tokens. The calling application is responsible for obtaining and providing the token.
    *   **Server-Side:** The agent server must validate the Bearer token.
    *   **Security:** Security depends entirely on the external mechanism used to obtain and manage the token.

*(Refer to the [A2A Profile v0.2](a2a_protocol.md) for detailed protocol structure.)*

## 2. Developer-to-Registry Authentication

Developers need to authenticate with the AgentVault Registry API (`agentvault_registry`) to manage their registered agents and API keys.

*   **Account Creation & Login (Email/Password + JWT):**
    *   Developers register with an email and password. Passwords are **hashed using bcrypt** via `passlib`.
    *   Email verification is required to activate the account.
    *   Successful login (`POST /auth/login`) issues a short-lived **JWT access token**.
    *   This JWT must be sent in the `Authorization: Bearer <token>` header for protected API calls (e.g., `POST /api/v1/agent-cards/`) and interactions with the Developer Portal UI (`/ui/developer`).
    *   The registry validates the JWT signature (using `API_KEY_SECRET` from its config) and expiry on each request.

*   **Programmatic API Keys (`X-Api-Key`):**
    *   Developers can generate separate, long-lived API keys (prefixed `avreg_`) via the Developer Portal UI or API (`POST /developers/me/apikeys`).
    *   The registry stores the **hash** (bcrypt via `passlib`) of the full key and the non-secret **prefix** (`avreg_`). The plain key is shown only once upon generation.
    *   For programmatic access to manage agent cards, developers can use the `X-Api-Key` header containing the plain key.
    *   The registry API verifies the key by looking up potential matches based on the prefix and then comparing the hash of the provided key with stored hashes using `passlib.verify()`. It also checks if the key is active.

*   **Account Recovery (Recovery Keys):**
    *   Generated during registration, displayed once, **must be stored securely offline by the developer**.
    *   The registry stores a **hash** (bcrypt) of *one* representative recovery key.
    *   If a password is lost, the developer can use their email + *one* plain recovery key via `POST /auth/recover-account`.
    *   The server verifies the plain key against the stored hash. If valid, it issues a *very* short-lived JWT (with `purpose: password-set`) allowing the developer to call `POST /auth/set-new-password`.
    *   Using a recovery key invalidates its stored hash, preventing reuse.

## 3. Credential Management (`KeyManager` - Client Side)

The `agentvault.key_manager.KeyManager` class provides a crucial security abstraction on the client-side (e.g., within the CLI or custom applications using the library).

*   **Purpose:** Securely store and retrieve the secrets (API keys, OAuth Client IDs/Secrets) needed to authenticate with various *remote A2A agents*.
*   **Secure Storage:** **Strongly recommends using the OS Keyring** (`keyring` library integration) as the backend. This leverages native secure storage mechanisms (e.g., macOS Keychain, Windows Credential Manager, Linux Secret Service). Use `agentvault_cli config set <service_id> --keyring` or `--oauth-configure`.
*   **Alternative Sources:** Supports loading from environment variables (e.g., `AGENTVAULT_KEY_OPENAI`) or local files (`.env`, `.json`). **Users are responsible for securing these sources** (e.g., file permissions, secure environment variable management).
*   **Abstraction:** Client code interacts with `KeyManager.get_key()` or `get_oauth_client_id()`, etc., using a logical `service_id` (e.g., "openai", "my-custom-agent"). The KeyManager handles finding the credential from the highest-priority source (File > Env > Keyring).

## 4. Transport Security (HTTPS)

*   **Requirement:** **HTTPS is MANDATORY** for all A2A communication and all communication with the AgentVault Registry API, unless explicitly connecting to `localhost` during development.
*   **Rationale:** Prevents eavesdropping and man-in-the-middle attacks, ensuring the confidentiality and integrity of requests and responses (including authentication credentials like API keys or Bearer tokens).
*   **Enforcement:** Clients should verify TLS certificates. Agent implementations and registry deployments MUST be configured for HTTPS.

## 5. Data Validation

*   **Pydantic:** Used across all components (library models, registry API, server SDK) to rigorously validate data structures (Agent Cards, A2A messages, API request/response bodies) against defined schemas.
*   **Benefit:** Prevents injection attacks, malformed data processing errors, and ensures protocol adherence.

## 6. Rate Limiting (Registry)

*   **Mechanism:** The public AgentVault Registry API implements IP-based rate limiting using `slowapi` to mitigate denial-of-service (DoS) attacks and prevent abuse of public endpoints.
*   **Agent Responsibility:** Developers building A2A agents should implement their own rate limiting suitable for their agent's expected load and cost model.

## 7. Trusted Execution Environments (TEE)

*   **Support:** AgentVault v1.0.0 includes **declarative support** for TEEs. Agents can advertise their use of TEEs (like Intel SGX, AWS Nitro Enclaves) in their Agent Card via the `capabilities.teeDetails` field.
*   **Discovery:** The registry allows filtering agents based on whether they declare TEE support (`?has_tee=true/false`) or a specific TEE type (`?tee_type=...`).
*   **Verification:** **Client-side verification of TEE attestations is NOT yet implemented** in the core library. Clients needing high assurance must implement attestation verification specific to the agent's declared TEE type using the optional `attestationEndpoint` from the Agent Card.
*   **(See [TEE Profile](../tee_profile.md) for details).**

## 8. Dependency Security

*   **Auditing:** The project includes automated dependency vulnerability scanning using `pip-audit` via GitHub Actions.
*   **Maintenance:** Regularly updating dependencies is crucial to patch known vulnerabilities.

## Best Practices Summary

*   **Users/Clients:** Use the OS Keyring via `agentvault_cli config set --keyring` or `--oauth-configure` for storing agent credentials. Avoid placing secrets directly in scripts or unsecured files/environment variables. Always verify agent identity and trustworthiness before interacting, especially for sensitive tasks.
*   **Agent Developers:**
    *   Use HTTPS for your A2A endpoint.
    *   Choose appropriate `authSchemes` for your agent's sensitivity. Implement robust server-side validation for the chosen schemes.
    *   Securely store any credentials your agent needs (e.g., for backend services) using environment variables or dedicated secrets management solutions, *not* in code.
    *   Implement input validation and rate limiting.
    *   If handling sensitive data, consider deploying within a TEE and declare it in your Agent Card.
    *   Keep SDK and other dependencies updated.
*   **Registry Deployers:**
    *   Securely manage the `DATABASE_URL` and `API_KEY_SECRET`.
    *   Configure appropriate CORS policies (`ALLOWED_ORIGINS`).
    *   Set up robust monitoring, logging, and database backups.
    *   Deploy behind a reverse proxy handling HTTPS termination.
