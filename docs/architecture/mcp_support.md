# AgentVault MCP Support (Conceptual Profile)

## Introduction

The AgentVault Agent-to-Agent (A2A) protocol defines the core mechanisms for secure communication, task management, and event streaming between agents. However, many complex agent interactions require more than just the primary message content. Agents often need additional **context** to perform their tasks effectively. This could include:

*   User profile information
*   Relevant snippets from previous interactions
*   Metadata about the environment
*   References to external files or data artifacts
*   Schema definitions for expected inputs/outputs
*   Tool descriptions and schemas

The **Model Context Protocol (MCP)** concept within AgentVault provides a structured way to embed this richer context *within* standard A2A messages.

## Current Status (AgentVault v1.0.0)

**Evolving Standard:** The formal MCP specification is still evolving within the broader AI agent community.

**AgentVault Implementation:** AgentVault v1.0.0 provides **basic, conceptual support** for MCP.
*   The core `agentvault` library includes utilities (`agentvault.mcp_utils`) for formatting and validating a basic MCP structure (`MCPContext` and `MCPItem` Pydantic models).
*   The `AgentVaultClient` allows embedding this structured context into the `message.metadata["mcp_context"]` field during `initiate_task` or `send_message` calls.
*   The `agentvault-server-sdk` provides a helper (`get_mcp_context`) for agents to easily extract this dictionary from incoming messages.

This provides a flexible mechanism for passing structured context but **does not yet enforce a strict, standardized MCP schema** beyond the basic container structure defined in `mcp_utils.py`. Future AgentVault versions will aim to align with official MCP standards as they mature.

## Transport Mechanism

MCP context is embedded within the `metadata` field of standard A2A `Message` objects (`agentvault.models.Message`) under the key `"mcp_context"`.

```json
// Example A2A Message including MCP Context
{
  "role": "user",
  "parts": [
    { "type": "text", "content": "Refactor the attached Python script based on these guidelines." }
  ],
  "metadata": {
    "timestamp": "...",
    "client_request_id": "...",
    // MCP context is embedded here:
    "mcp_context": {
       "items": {
         "guidelines_doc": {
            "ref": "artifact://guideline-doc-123",
            "mediaType": "text/markdown"
         },
         "user_prefs": {
            "content": {"refactoring_style": "aggressive", "target_python": "3.11"},
            "mediaType": "application/json"
         }
         // ... potentially other context items ...
       }
    }
  }
}
```

## Structure (Current Conceptual Model)

The `agentvault.mcp_utils` module defines placeholder Pydantic models for structure validation:

1.  **`MCPContext` (Root Object):**
    *   `items` (Dict[str, MCPItem]): Dictionary mapping unique item names/IDs to `MCPItem` objects.

2.  **`MCPItem` (Individual Context Piece):**
    *   `id` (Optional `str`): Item identifier within the context.
    *   `mediaType` (Optional `str`): MIME type (e.g., "text/plain", "application/json").
    *   `content` (Optional `Any`): Direct content (string, dict, list).
    *   `ref` (Optional `str`): Reference to external context (URL, artifact ID).
    *   `metadata` (Optional `Dict[str, Any]`): Item-specific metadata.

**Example `mcp_context` Payload:**

```json
"mcp_context": {
  "items": {
    "user_profile": {
      "mediaType": "application/json",
      "content": {
        "user_id": "usr_123",
        "preferences": {"theme": "dark"},
        "permissions": ["read", "write"]
      },
      "metadata": {"source": "internal_db"}
    },
    "target_document": {
      "mediaType": "application/pdf",
      "ref": "s3://my-bucket/documents/report.pdf",
      "metadata": {"version": "1.2"}
    }
  }
}
```

## Client-Side Usage (`agentvault` Library)

Use the `mcp_context` parameter in `AgentVaultClient` methods:

```python
from agentvault import AgentVaultClient, KeyManager, Message, TextPart, agent_card_utils

async def run_with_mcp(client: AgentVaultClient, card, km, msg, context_dict):
    try:
        task_id = await client.initiate_task(
            agent_card=card,
            initial_message=msg,
            key_manager=km,
            mcp_context=context_dict # Pass the context here
        )
        print(f"Task with MCP started: {task_id}")
        # ... stream events ...
    except Exception as e:
        print(f"Error: {e}")
```
The library validates and embeds the dictionary under `message.metadata["mcp_context"]`.

## Server-Side Usage (`agentvault-server-sdk`)

Use the `get_mcp_context` helper:

```python
from agentvault_server_sdk import BaseA2AAgent
from agentvault_server_sdk.mcp_utils import get_mcp_context
from agentvault.models import Message

class MyAgent(BaseA2AAgent):
    async def handle_task_send(self, task_id: Optional[str], message: Message) -> str:
        mcp_data = get_mcp_context(message)
        if mcp_data:
            print(f"MCP Data Received: {mcp_data}")
            # Process mcp_data['items']...
        # ... rest of logic ...
```

## Future

AgentVault aims to adopt official MCP standards as they stabilize, potentially refining the `mcp_utils` models and validation, and adding more specific helpers in the client library and server SDK. The current implementation provides a basic, flexible mechanism for passing structured context.
