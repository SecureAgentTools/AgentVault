# AgentVault A2A Protocol Profile v0.2

This document specifies the Agent-to-Agent (A2A) communication profile implemented by AgentVault components (as of v1.0.0 of the libraries/SDK). It defines how clients interact with A2A-compliant agent servers, aligning with concepts from emerging A2A standards like Google's A2A protocol.

*This document corresponds to the implementation in `agentvault` v0.2.x library and `agentvault-server-sdk` v0.1.x.*

## Overview

*   **Protocol:** JSON-RPC 2.0 Specification.
*   **Transport:** HTTP/1.1 or HTTP/2. **HTTPS is REQUIRED** for all communication except potentially during local development targeting `localhost`.
*   **Request Method:** `POST` for all JSON-RPC requests.
*   **Streaming:** Server-Sent Events (SSE) via the `tasks/sendSubscribe` method for real-time updates.
*   **Data Format:** JSON (UTF-8 encoding).
*   **Authentication:** Defined via `authSchemes` in the [Agent Card](../concepts.md#agent-card). Supported schemes include `none`, `apiKey`, and `oauth2` (Client Credentials Grant). See [Authentication](#authentication) section below.
*   **Models:** Data structures (AgentCard, Task, Message, etc.) are defined using Pydantic in the `agentvault.models` module of the core library.

## Transport Details

All JSON-RPC requests MUST be sent using the HTTP `POST` method to the agent's designated A2A endpoint URL (found in the `url` field of its Agent Card).

*   **Request Headers:**
    *   `Content-Type: application/json` is REQUIRED.
    *   `Accept: application/json` is RECOMMENDED for non-streaming requests.
    *   `Accept: text/event-stream` is REQUIRED for `tasks/sendSubscribe` requests.
    *   Authentication headers (e.g., `X-Api-Key` or `Authorization: Bearer <token>`) MUST be included if required by the agent's `authSchemes`.
*   **Request Body:** Contains the standard JSON-RPC 2.0 request object.
*   **Response Body (Non-Streaming):** Contains the standard JSON-RPC 2.0 response object (either `result` or `error`). The HTTP status code SHOULD be `200 OK` even for JSON-RPC errors, as per JSON-RPC spec recommendations.
*   **Response Body (Streaming via `tasks/sendSubscribe`):** The server responds with HTTP `200 OK` and `Content-Type: text/event-stream`. The HTTP response body then contains the SSE stream.

## Authentication

Agents declare their supported authentication methods in the `authSchemes` list within their Agent Card. The `agentvault` client library (`AgentVaultClient` using `KeyManager`) handles these schemes automatically:

*   **`none`**: No authentication headers are sent. Suitable only for public, non-sensitive agents.
*   **`apiKey`**:
    *   Client retrieves the API key associated with the `service_identifier` (from the Agent Card or user override) using `KeyManager`.
    *   Client sends the key in the `X-Api-Key` HTTP header.
    *   Server MUST validate the received key against its secure storage.
*   **`oauth2` (Client Credentials Grant Flow)**:
    *   Requires the `AgentAuthentication` object in the card to include `tokenUrl`. `scopes` are optional.
    *   Client retrieves its *own* Client ID and Secret associated with the `service_identifier` using `KeyManager`.
    *   Client POSTs `grant_type=client_credentials`, `client_id`, `client_secret` (and optionally `scope`) to the agent's `tokenUrl`.
    *   Agent's token endpoint validates credentials and returns a JSON response with `access_token` (required), `token_type` (must be "Bearer", case-insensitive check), and optionally `expires_in`.
    *   Client sends the received `access_token` in the `Authorization: Bearer <token>` header for subsequent A2A requests to the agent's main `url`.
    *   The `AgentVaultClient` automatically handles token fetching and caching (respecting `expires_in` if provided).
    *   Server's main A2A endpoint MUST validate the Bearer token (signature, expiry, audience, scopes if applicable).
*   **`bearer`**:
    *   Client assumes the user/application has already obtained a valid Bearer token through other means (e.g., user login flow separate from AgentVault).
    *   Client sends the token in the `Authorization: Bearer <token>` header.
    *   The `agentvault` library currently requires explicit configuration or extension to handle this scheme, as it doesn't manage the token lifecycle.
    *   Server MUST validate the received Bearer token.

Refer to the main [Security Concepts](security_concepts.md#1-client-to-agent-authentication-a2a) document for more details.

## JSON-RPC 2.0 Structure

All requests and responses adhere to the JSON-RPC 2.0 specification.

**Request Object:**

```json
{
  "jsonrpc": "2.0",
  "method": "method_name",
  "params": <parameters_object_or_array>,
  "id": <request_id_string_or_number_or_null>
}
```

*   `jsonrpc`: MUST be exactly "2.0".
*   `method`: A string containing the name of the method (e.g., "tasks/send").
*   `params`: An optional structured value (object or array). AgentVault methods use parameter objects (dictionaries).
*   `id`: An identifier established by the Client. If included, the response MUST include the same value. If omitted (notification), the server MUST NOT reply. AgentVault methods generally expect an ID.

**Response Object (Success):**

```json
{
  "jsonrpc": "2.0",
  "result": <result_value>,
  "id": <matching_request_id>
}
```

*   `result`: The value returned by the method invocation. Its structure depends on the method called (see method definitions below).
*   `id`: Must match the `id` from the Request Object.

**Response Object (Error):**

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": <integer>,
    "message": <string>,
    "data": <optional_any>
  },
  "id": <matching_request_id_or_null>
}
```

*   `error`: An object describing the error.
    *   `code`: A Number indicating the error type. See [Error Codes](#json-rpc-error-codes).
    *   `message`: A String providing a short description of the error.
    *   `data`: Optional. A Primitive or Structured value containing additional information.
*   `id`: Must match the `id` from the Request Object. If the error occurred before the ID could be determined (e.g., Parse Error), it SHOULD be `null`.

## Standard A2A Methods

These methods form the core of the AgentVault A2A interaction model, implemented by the `agentvault` client library and expected by servers built with the `agentvault-server-sdk`.

### `tasks/send`

Initiates a new task or sends a subsequent message to an existing task.

*   **Params:** `TaskSendParams` object (`agentvault.models.TaskSendParams`)
    *   `id` (Optional[str]): Task ID if continuing an existing task. Omit or null if initiating a new task.
    *   `message` (Message): The message object (`agentvault.models.Message`) to send.
    *   **(Optional)** `webhookUrl` (Optional[str]): URL for agent push notifications (if agent supports `supportsPushNotifications`). Client is responsible for handling POST requests to this URL from the agent. (*Note: Push notification handling is not fully implemented in client/SDK v1.0.0*).
*   **Result:** `TaskSendResult` object (`agentvault.models.TaskSendResult`)
    *   `id` (str): The ID of the task (newly created or existing).
*   **Example Request (Initiate):**
    ```json
    {
      "jsonrpc": "2.0",
      "method": "tasks/send",
      "params": {
        "message": {
          "role": "user",
          "parts": [{"type": "text", "content": "What is the weather in London?"}],
          "metadata": {
            "mcp_context": { "user_pref": "celsius" }
          }
        }
        {# Example including optional webhook: #}
        {# "webhookUrl": "https://my-client.example.com/webhook/task-updates" #}
      },
      "id": "req-1"
    }
    ```
*   **Example Response (Initiate):**
    ```json
    {
      "jsonrpc": "2.0",
      "result": {
        "id": "task-abc-123"
      },
      "id": "req-1"
    }
    ```
*   **Example Request (Continue):**
    ```json
    {
      "jsonrpc": "2.0",
      "method": "tasks/send",
      "params": {
        "id": "task-abc-123",
        "message": {
          "role": "user",
          "parts": [{"type": "text", "content": "What about tomorrow?"}]
        }
      },
      "id": "req-2"
    }
    ```
*   **Example Response (Continue):**
    ```json
    {
      "jsonrpc": "2.0",
      "result": {
        "id": "task-abc-123"
      },
      "id": "req-2"
    }
    ```

### `tasks/get`

Retrieve the current status and details of a specific task.

*   **Params:** `TaskGetParams` object (`agentvault.models.TaskGetParams`)
    *   `id` (str): The ID of the task to retrieve.
*   **Result:** `Task` object (`agentvault.models.Task`) representing the full task state.
*   **Example Request:**
    ```json
    {
      "jsonrpc": "2.0",
      "method": "tasks/get",
      "params": {
        "id": "task-abc-123"
      },
      "id": "req-3"
    }
    ```*   **Example Response:**
    ```json
    {
      "jsonrpc": "2.0",
      "result": {
        "id": "task-abc-123",
        "state": "WORKING",
        "createdAt": "2024-04-15T10:00:00Z",
        "updatedAt": "2024-04-15T10:05:30Z",
        "messages": [
          {"role": "user", "parts": [{"type": "text", "content": "What is the weather in London?"}], "metadata": null},
          {"role": "assistant", "parts": [{"type": "text", "content": "Fetching weather..."}], "metadata": null}
        ],
        "artifacts": [
          {"id": "artifact-1", "type": "log", "content": "API call made", "url": null, "mediaType": "text/plain", "metadata": null}
        ],
        "metadata": null
      },
      "id": "req-3"
    }
    ```

### `tasks/cancel`

Request the cancellation of an ongoing task.

*   **Params:** `TaskCancelParams` object (`agentvault.models.TaskCancelParams`)
    *   `id` (str): The ID of the task to cancel.
*   **Result:** `TaskCancelResult` object (`agentvault.models.TaskCancelResult`)
    *   `success` (bool): Indicates if the cancellation request was *accepted* by the agent (doesn't guarantee immediate cancellation).
    *   `message` (Optional[str]): Optional message from the agent regarding the cancellation request.
*   **Example Request:**
    ```json
    {
      "jsonrpc": "2.0",
      "method": "tasks/cancel",
      "params": {
        "id": "task-abc-123"
      },
      "id": "req-4"
    }
    ```
*   **Example Response:**
    ```json
    {
      "jsonrpc": "2.0",
      "result": {
        "success": true,
        "message": "Cancellation request received."
      },
      "id": "req-4"
    }
    ```

### `tasks/sendSubscribe`

Initiates a subscription to real-time updates for a task via Server-Sent Events (SSE).

*   **Params:** Object containing the task ID.
    *   `id` (str): The ID of the task to subscribe to.
*   **Response:** HTTP `200 OK` with `Content-Type: text/event-stream`. The HTTP response body contains the SSE stream. **No JSON-RPC `result` field is sent in the initial HTTP response body.**
*   **Example Request:**
    ```json
    {
      "jsonrpc": "2.0",
      "method": "tasks/sendSubscribe",
      "params": {
        "id": "task-abc-123"
      },
      "id": "req-5"
    }
    ```
*   **Example Response (HTTP Headers & Body Start):**
    ```http
    HTTP/1.1 200 OK
    Content-Type: text/event-stream
    Cache-Control: no-cache
    Connection: keep-alive

    event: task_status
    data: {"taskId": "task-abc-123", "state": "WORKING", "timestamp": "2024-04-15T10:05:00Z", "message": null}

    event: task_message
    data: {"taskId": "task-abc-123", "message": {"role": "assistant", "parts": [{"type": "text", "content": "Thinking..."}], "metadata": null}, "timestamp": "2024-04-15T10:05:05Z"}

    ... (more events) ...
    ```

## Task States (`TaskState` Enum)

The defined states for an A2A task lifecycle (`agentvault.models.TaskState`):

*   **`SUBMITTED`**: Task received, awaiting execution.
*   **`WORKING`**: Task actively being processed.
*   **`INPUT_REQUIRED`**: Task paused, awaiting further client input (advanced use case).
*   **`COMPLETED`**: Task finished successfully. (Terminal)
*   **`FAILED`**: Task terminated due to an error. (Terminal)
*   **`CANCELED`**: Task canceled by request. (Terminal)

## Server-Sent Events (SSE)

Used for the `tasks/sendSubscribe` stream.

*   **Format:** Standard SSE. Each event consists of `event:` and `data:` lines, terminated by `\n\n`. The `data:` field contains a **single line** JSON string representing the corresponding event payload.
    ```sse
    event: <event_type>
    data: <json_payload_string>

    event: <another_event_type>
    data: <another_json_payload_string>

    ```
*   **Event Types (`event:` field):**
    *   `task_status`: Task state change. `data` is JSON of `TaskStatusUpdateEvent`.
    *   `task_message`: New message added. `data` is JSON of `TaskMessageEvent`.
    *   `task_artifact`: Artifact created/updated. `data` is JSON of `TaskArtifactUpdateEvent`.
    *   `error`: Server-side error during streaming. `data` is a JSON object like `{"error": "code", "message": "desc"}`.
*   **Data Payload (`data:` field):** A JSON string representing the corresponding event model (`agentvault.models.TaskStatusUpdateEvent`, `TaskMessageEvent`, `TaskArtifactUpdateEvent`). The client library validates these payloads against the Pydantic models.

**Example SSE Stream:**

```sse
event: task_status
data: {"taskId": "task-abc-123", "state": "WORKING", "timestamp": "2024-04-15T10:05:00Z", "message": null}

event: task_message
data: {"taskId": "task-abc-123", "message": {"role": "assistant", "parts": [{"type": "text", "content": "Thinking..."}], "metadata": null}, "timestamp": "2024-04-15T10:05:05Z"}

event: task_artifact
data: {"taskId": "task-abc-123", "artifact": {"id": "log-1", "type": "debug_log", "content": "Processing step 1", "url": null, "mediaType": "text/plain", "metadata": null}, "timestamp": "2024-04-15T10:05:10Z"}

event: task_status
data: {"taskId": "task-abc-123", "state": "COMPLETED", "timestamp": "2024-04-15T10:05:15Z", "message": "Task finished successfully."}

```

## JSON-RPC Error Codes

Standard JSON-RPC codes MUST be used where applicable. AgentVault defines application-specific codes in the `-32000` to `-32099` range for agent-level errors.

| Code    | Message             | Meaning                                      | Standard/App |
| :------ | :------------------ | :------------------------------------------- | :----------- |
| -32700  | Parse error         | Invalid JSON received by the server.         | Standard     |
| -32600  | Invalid Request     | The JSON sent is not a valid Request object. | Standard     |
| -32601  | Method not found    | The method does not exist / is not available.| Standard     |
| -32602  | Invalid Params      | Invalid method parameter(s).                 | Standard     |
| -32603  | Internal error      | Internal JSON-RPC error on the server.       | Standard     |
| -32000  | Agent Server Error  | Generic application error on the agent.      | Application  |
| -32001  | Task Not Found      | Specified `task_id` does not exist.          | Application  |
| -32002  | Authentication Error| API Key / Token invalid or missing.          | Application  |
| -32003  | Authorization Error | Authenticated user cannot perform action.    | Application  |
| -32004  | Invalid State       | Operation not allowed in current task state. | Application  |
| *others*| *Implementation Defined* | Server may define other -320xx errors.   | Application  |

Servers SHOULD include meaningful information in the `message` and optionally the `data` part of the error object. The client library (`A2ARemoteAgentError`) makes this information accessible.
