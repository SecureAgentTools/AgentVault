# Model Context Protocol (MCP) Profile (Concept)

**Status:** Defined & Implemented via Proxy Pattern

## 1. Introduction

The Model Context Protocol (MCP) provides a standardized interface for AgentVault components (like orchestrators or other agents) to discover and execute external **Tools**. MCP enables interaction with capabilities that might reside outside the core A2A agent network, such as secure code execution environments, dedicated filesystem access points, specialized database query engines, or specific hardware interactions.

**Goal:** To enable standardized, reusable, and potentially secured access to a wide range of external capabilities within the AgentVault ecosystem, complementing the more general-purpose A2A protocol.

## 2. Protocol Basics

*   **Transport:** MCP uses HTTP/1.1 or HTTP/2, typically over TLS (HTTPS).
*   **Message Format:** MCP utilizes **JSON-RPC 2.0** ([Specification](https://www.jsonrpc.org/specification)) for all request/response interactions.
    *   Standard JSON-RPC fields (`jsonrpc`, `id`, `method`, `params`, `result`, `error`) are used.
*   **Tool Naming:** Tools are identified using a namespace convention, typically `namespace.toolName` (e.g., `filesystem.readFile`, `code.runPython`).
*   **Standard Results:** Successful tool executions return a JSON-RPC `result` object, conventionally containing a `content` array of standardized data structures (e.g., `{"type": "text", "text": "..."}`, `{"type": "code_output", "stdout": "...", "stderr": "..."}`).
*   **Tool Errors:** Tool-specific execution errors (e.g., file not found, code execution timeout) are typically reported within the JSON-RPC `result` object by setting an `"isError": true` flag and providing error details within the `content` array, distinct from JSON-RPC protocol errors.

```json
// Example MCP Success Result
{
  "jsonrpc": "2.0",
  "id": "req-123",
  "result": {
    "content": [{"type": "text", "text": "Content of the file."}]
  }
}

// Example MCP Tool Error Result
{
  "jsonrpc": "2.0",
  "id": "req-456",
  "result": {
    "isError": true,
    "content": [{"type": "text", "text": "Error: File not found at specified path."}]
  }
}
```

## 3. Integration with AgentVault (A2A Proxy Pattern)

While direct client-side support for MCP calls may be added to the `agentvault` library in the future, the **current recommended and proven pattern** for integrating MCP tools into AgentVault workflows is via a dedicated **MCP Tool Proxy Agent**.

*   **MCP Tool Proxy Agent:** An A2A-compliant agent (built using the `agentvault-server-sdk`) acts as a bridge.
*   **Workflow:**
    1.  An Orchestrator (or other A2A client) sends a standard A2A `tasks/send` request to the Proxy Agent. The request's `DataPart` specifies the target tool server (e.g., by a logical ID like `"filesystem"`), the tool name (`filesystem.readFile`), and the arguments (`{"path": "/data/file.txt"}`).
    2.  The Proxy Agent looks up the actual network address of the target MCP Tool Server based on the provided ID (often configured via environment variables).
    3.  The Proxy Agent constructs and sends a standard MCP JSON-RPC 2.0 request over HTTP to the target Tool Server's `/rpc` endpoint.
    4.  The MCP Tool Server executes the tool and returns a JSON-RPC 2.0 response (containing either a `result` or an `error`).
    5.  The Proxy Agent receives the MCP response and translates it back into a standard A2A task result (e.g., putting the MCP `result` or error details into a `DataPart` artifact or message).
    6.  The Orchestrator receives the outcome of the tool execution via the A2A protocol from the Proxy Agent.

*   **Benefits:** This pattern decouples the A2A and MCP domains, allowing orchestrators to leverage MCP tools without implementing MCP specifics. It centralizes the logic for communicating with different tool servers within the proxy.
*   **Demonstration:** The **[MCP Test Pipeline Example](./examples/poc_mcp_pipeline.md)** successfully implements this pattern, showcasing interaction with custom Python-based MCP servers for filesystem and code execution tasks.

## 4. MCP Tool Servers

These are the actual services performing the work. They only need to expose an HTTP endpoint (e.g., `/rpc`) that accepts JSON-RPC 2.0 requests for their specific tools.

*   **Examples:**
    *   `custom-filesystem-mcp`: Provides `filesystem.readFile`, `filesystem.writeFile`, `filesystem.listDirectory`.
    *   `custom-code-runner-mcp`: Provides `code.runPython`.
*   **Implementation:** Can be built using any web framework capable of handling JSON-RPC over HTTP (like FastAPI, Express, etc.). The AgentVault project provides examples using Python/FastAPI.

## 5. Future Directions

*   Formalizing standard MCP tool namespaces and content types.
*   Defining a standard MCP-based tool discovery mechanism.
*   Potentially adding direct MCP client capabilities to the `agentvault` library.
