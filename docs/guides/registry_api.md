# Developer Guide: Registry API (`agentvault_registry`)

The AgentVault Registry provides a central RESTful API service and Web UI for discovering and managing Agent Cards. Developers interact with it programmatically or via the UI to publish their agents, while clients (like the `agentvault_cli` or other applications) use it to find agents.

*   **Public Registry & UI:** [`https://agentvault-registry-api.onrender.com`](https://agentvault-registry-api.onrender.com)
*   **Public Discovery UI:** [`/ui`](https://agentvault-registry-api.onrender.com/ui)
*   **Developer Portal UI:** [`/ui/developer`](https://agentvault-registry-api.onrender.com/ui/developer)
*   **API Base Path:** `/api/v1`

*(Note: The public instance runs on a free tier and may experience cold starts taking up to 60 seconds for the first request after inactivity.)*

## Authentication & Developer Registration

Interacting with the registry requires different levels of authentication:

1.  **Public Access:** Discovering agents (`GET /api/v1/agent-cards/`, `GET /api/v1/agent-cards/{card_id}`, `GET /api/v1/agent-cards/id/{human_readable_id}`) and validating card data (`POST /api/v1/utils/validate-card`) are generally public and do not require authentication.
2.  **Developer Account Authentication (JWT):** Managing your own agent cards (create, update, deactivate), managing programmatic API keys, and using the agent builder requires you to be logged in as a registered developer. This uses **email/password authentication** via the `/auth/login` endpoint, which returns a **JSON Web Token (JWT)**. Subsequent requests to protected developer endpoints must include this JWT in the `Authorization: Bearer <token>` HTTP header.
3.  **Programmatic API Key Authentication:** For automated scripts or CI/CD pipelines interacting with the registry API (e.g., to update an agent card automatically), developers can generate **programmatic API keys**. These keys are sent in the `X-Api-Key` header for specific authenticated endpoints (primarily intended for agent card management, though JWT is preferred for user-driven actions).

**Registration Workflow:**

*   **Self-Registration:** Developers can register via the `/ui/register` page or the `POST /auth/register` API endpoint.
*   **Required Information:** Name, Email, Password.
*   **Verification:** Upon registration, a verification email is sent to the provided address. The developer must click the link in the email to activate their account (`GET /auth/verify-email`). Unverified accounts cannot log in.
*   **Recovery Keys:** During registration, a set of **single-use recovery keys** are generated and displayed **only once**. These keys are essential for regaining account access if the password is lost and email reset is unavailable. **Store these keys securely offline.**
*   **Password Reset:** A password reset can be requested via email (if email sending is configured on the registry instance) using the `/ui/forgot-password` page or `POST /auth/request-password-reset` endpoint. Alternatively, account access can be regained using a recovery key via the `/ui/recover-with-key` page or `POST /auth/recover-account` endpoint, which provides a temporary token to set a new password via `/ui/set-new-password` or `POST /auth/set-new-password`. Using a recovery key invalidates it.

## API Endpoints

*(Refer to the OpenAPI documentation at `/docs` or `/redoc` on the running registry instance for full details, request/response schemas, and interactive testing.)*

### Authentication (`/auth`)

Handles developer registration, login, email verification, and password/account recovery.

*   **`POST /register`**: Creates a new developer account. Requires name, email, password. Returns a success message and **one-time recovery keys**. Triggers verification email.
*   **`POST /login`**: Authenticates using email/password (sent as form data). Returns a JWT `access_token` (`schemas.Token`). Requires verified email.
*   **`GET /verify-email`**: Endpoint visited via the link in the verification email. Activates the developer account. Redirects user to success/failure UI pages.
*   **`POST /request-password-reset`**: (Placeholder/Future) Sends a password reset link to the developer's email.
*   **`POST /reset-password`**: (Placeholder/Future) Sets a new password using a token from the reset email.
*   **`POST /recover-account`**: Verifies email and a recovery key. Returns a short-lived JWT (`schemas.Token`) specifically for setting a new password.
*   **`POST /set-new-password`**: Sets a new password using the temporary token from `/recover-account`. Requires `Authorization: Bearer <temp_token>` header and `{"new_password": "..."}` body. Invalidates the used recovery key hash.

### Developers (`/developers`)

Endpoints for managing the authenticated developer's own account and resources. **Requires JWT authentication (`Authorization: Bearer <token>`).**

*   **`GET /me`**: Returns the profile information (`schemas.DeveloperRead`) for the currently authenticated developer.
*   **`POST /me/apikeys`**: Generates a new programmatic API key (prefixed `avreg_`) associated with the developer. Optionally takes a `description` in the request body. Returns the **plain text key once** along with key metadata (`schemas.NewApiKeyResponse`).
*   **`GET /me/apikeys`**: Lists metadata (`schemas.ApiKeyRead`) for all *active* programmatic API keys belonging to the developer.
*   **`DELETE /me/apikeys/{key_id}`**: Deactivates (soft deletes) a specific programmatic API key by its integer `key_id`. Returns `204 No Content` on success.

### Agent Cards (`/api/v1/agent-cards`)

Endpoints for managing and discovering Agent Cards.

*   **`POST /`**:
    *   **Summary:** Submit a new Agent Card.
    *   **Auth:** Requires JWT authentication.
    *   **Request Body:** `schemas.AgentCardCreate` (contains the `card_data` dictionary).
    *   **Response:** `schemas.AgentCardRead` (includes generated UUID, timestamps, `developer_is_verified` status).
    *   **Notes:** Validates `card_data`. Extracts `name`/`description` for indexing.
*   **`GET /`**:
    *   **Summary:** List Agent Cards (Summaries).
    *   **Auth:** Public, *unless* `owned_only=true` is used (requires JWT).
    *   **Query Params:** `skip`, `limit`, `active_only`, `search`, `tags`, `has_tee`, `tee_type`, `owned_only`.
    *   **Response:** `schemas.AgentCardListResponse` (contains `items: List[AgentCardSummary]` and `pagination: PaginationInfo`).
*   **`GET /{card_id}`**:
    *   **Summary:** Get Agent Card by UUID.
    *   **Auth:** Public.
    *   **Response:** `schemas.AgentCardRead` (full card details, including `developer_is_verified`).
*   **`GET /id/{human_readable_id:path}`**:
    *   **Summary:** Get Agent Card by Human-Readable ID.
    *   **Auth:** Public.
    *   **Path Param:** `human_readable_id` (e.g., `my-org/my-agent`). The `:path` allows slashes.
    *   **Response:** `schemas.AgentCardRead`.
*   **`GET /by-hri`**:
    *   **Summary:** Get Agent Card by Human-Readable ID (Query Parameter).
    *   **Auth:** Public.
    *   **Query Param:** `hri` (e.g., `my-org/my-agent`). Use this if the HRI contains characters problematic for path parameters.
    *   **Response:** `schemas.AgentCardRead`.
*   **`PUT /{card_id}`**:
    *   **Summary:** Update an Agent Card.
    *   **Auth:** Requires JWT authentication; developer must own the card.
    *   **Request Body:** `schemas.AgentCardUpdate` (can contain `card_data` and/or `is_active`). If `card_data` is present, it replaces the existing card data after validation.
    *   **Response:** `schemas.AgentCardRead` (updated card details).
*   **`DELETE /{card_id}`**:
    *   **Summary:** Deactivate an Agent Card (Soft Delete).
    *   **Auth:** Requires JWT authentication; developer must own the card.
    *   **Response:** `204 No Content`.

### Agent Builder (`/agent-builder`)

Endpoint for generating agent boilerplate code.

*   **`POST /generate`**:
    *   **Summary:** Generate Agent Package.
    *   **Auth:** Requires JWT authentication.
    *   **Request Body:** `schemas.AgentBuildConfig` (specifies agent name, description, type, backend details, etc.).
    *   **Response:** `200 OK` with `Content-Type: application/zip`. The response body is a downloadable ZIP archive containing the generated agent project structure (source code, Dockerfile, config files).
    *   **Errors:** 422 (invalid build config), 500 (generation error).

### Utilities (`/api/v1/utils`)

Helper endpoints.

*   **`POST /validate-card`**:
    *   **Summary:** Validate Agent Card Data.
    *   **Auth:** Public.
    *   **Request Body:** `schemas.AgentCardValidationRequest`.
    *   **Response:** `schemas.AgentCardValidationResponse` (indicates validity and provides details on errors).

## Technology Stack

*   **Framework:** FastAPI
*   **Database:** PostgreSQL (using SQLAlchemy ORM and asyncpg driver)
*   **Migrations:** Alembic
*   **Authentication:** JWT (python-jose), Passlib (bcrypt hashing)
*   **Validation:** Pydantic
*   **Configuration:** Pydantic-Settings, python-dotenv
*   **Rate Limiting:** SlowAPI
*   **Email:** fastapi-mail (if configured)
*   **Server:** Uvicorn

## Deployment

*   **Prerequisites:** Python 3.10+, PostgreSQL Database.
*   **Configuration:** Uses environment variables and/or a `.env` file (see `.env.example`). Key variables include `DATABASE_URL` and `API_KEY_SECRET`. Optional email configuration (`MAIL_...`).
*   **Database Setup:** Run `alembic upgrade head` to apply migrations.
*   **Running:** Use `uvicorn agentvault_registry.main:app --host 0.0.0.0 --port 8000`. For production, run behind a reverse proxy (like Nginx) handling HTTPS and use multiple Uvicorn workers or a process manager.
*   **Docker:** A `Dockerfile` and `docker-compose.yml` are provided for containerized deployment, including a PostgreSQL service. See `DOCKER_README.md`.
