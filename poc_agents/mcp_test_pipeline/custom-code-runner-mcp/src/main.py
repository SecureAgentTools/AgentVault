import logging
import os
import json
from typing import Optional, Union, Literal # Added Literal, Union
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError # For potential future validation

# Import the tool function
from .tools import run_python_code

# Configure logging based on environment variable
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level_str, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Custom Code Runner MCP Server",
    version="0.1.0",
    description="Handles MCP `code.runPython` tool calls via HTTP POST JSON-RPC.",
)

# --- Optional: Pydantic Models for Request Validation ---
# While not strictly required by the research (manual parsing shown),
# using Pydantic can make validation cleaner.

class JsonRpcBase(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[Union[str, int]] = None

class CodeRunParams(BaseModel):
    code: str

class ToolCallRequest(JsonRpcBase):
    method: str
    params: CodeRunParams # Specific to code.runPython for now

# --- Tool Registry (Simple Dictionary) ---
# For this service, we only have one tool. A dictionary is sufficient.
# If more tools were added, using FastMCP for registration could be considered.
TOOL_REGISTRY = {
    "code.runPython": run_python_code
}

# --- JSON-RPC Endpoint ---

@app.post("/rpc",
          summary="MCP JSON-RPC Endpoint",
          description="Accepts JSON-RPC 2.0 requests over HTTP POST.",
          response_model=None, # Response varies (result or error object)
          tags=["MCP"]
          )
async def handle_rpc_request(request: Request):
    """
    Handles incoming JSON-RPC 2.0 requests, specifically targeting
    the 'code.runPython' method.
    """
    request_id: Optional[Union[str, int]] = None
    raw_body: bytes = b''
    try:
        raw_body = await request.body()
        # Attempt to parse the raw body as JSON
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON request body.")
            # JSON-RPC Parse Error (-32700)
            return JSONResponse(
                status_code=200, # Per spec, protocol errors often use 200 OK
                content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None}
            )

        # Basic validation of the JSON-RPC structure
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0" or "method" not in data:
            logger.warning(f"Received invalid JSON-RPC request structure: {data}")
            # JSON-RPC Invalid Request (-32600)
            return JSONResponse(
                status_code=200,
                content={"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": data.get("id") if isinstance(data, dict) else None}
            )

        # Store the request ID for the response
        request_id = data.get("id")
        method_name = data["method"]
        params = data.get("params", {}) # Default to empty dict if params missing

        # --- Method Dispatch ---
        tool_func = TOOL_REGISTRY.get(method_name)

        if tool_func is None:
            logger.warning(f"Requested method not found: '{method_name}'")
            # JSON-RPC Method Not Found (-32601)
            return JSONResponse(
                status_code=200,
                content={"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {method_name}"}, "id": request_id}
            )

        # --- Parameter Validation (Specific to code.runPython) ---
        # Expecting params to be an object like {"code": "print('hello')"}
        if not isinstance(params, dict) or "code" not in params:
            logger.warning(f"Invalid parameters for method '{method_name}': {params}")
            # JSON-RPC Invalid Params (-32602)
            return JSONResponse(
                status_code=200,
                content={"jsonrpc": "2.0", "error": {"code": -32602, "message": "Invalid params: Expected object with 'code' field"}, "id": request_id}
            )

        # --- Tool Execution ---
        logger.info(f"Dispatching request (ID: {request_id}) to tool: {method_name}")
        try:
            # Call the registered tool function (run_python_code)
            # The tool function handles its own internal errors and returns
            # a dictionary formatted for the 'result' field (success or tool error).
            tool_result_dict = await tool_func(code=params["code"])

            # Construct the final JSON-RPC success/tool error response
            response_data = {
                "jsonrpc": "2.0",
                "result": tool_result_dict, # Contains 'content' or 'isError'+'content'
                "id": request_id
            }
            return JSONResponse(content=response_data)

        except Exception as tool_exec_err:
            # This catches unexpected errors *during the call* to the tool function,
            # not errors *within* the tool function's logic (those are handled inside
            # run_python_code and return a dict with isError:true).
            logger.exception(f"Unexpected error occurred while calling tool '{method_name}' (ID: {request_id})")
            # Format as an MCP Tool Error response
            tool_error_result = {
                "isError": True,
                "content": [{"type": "text", "text": f"Internal server error calling tool: {tool_exec_err}"}]
            }
            response_data = {"jsonrpc": "2.0", "result": tool_error_result, "id": request_id}
            return JSONResponse(content=response_data)
        # --- End Tool Execution ---

    except Exception as e:
        # Catch-all for truly unexpected errors in the request handling logic itself
        logger.exception(f"Critical error processing request (ID: {request_id}). Body: {raw_body[:500]}")
        # JSON-RPC Internal Error (-32603)
        return JSONResponse(
            status_code=500, # Use 500 for server errors not covered by JSON-RPC protocol errors
            content={"jsonrpc": "2.0", "error": {"code": -32603, "message": "Internal server error"}, "id": request_id}
        )

@app.get("/health", tags=["Management"])
async def health_check():
    """Provides a basic health check endpoint."""
    return {"status": "ok", "service": "custom-code-runner-mcp"}

logger.info("Custom Code Runner MCP Server application initialized.")
logger.info(f"Registered tools: {list(TOOL_REGISTRY.keys())}")

# --- Optional: Add main execution block for local testing ---
# if __name__ == "__main__":
#     import uvicorn
#     port = int(os.environ.get("MCP_PORT", 8002))
#     log_level = os.environ.get("LOG_LEVEL", "info").lower()
#     print(f"Starting Custom Code Runner MCP Server on http://0.0.0.0:{port}")
#     uvicorn.run("main:app", host="0.0.0.0", port=port, log_level=log_level, reload=True) # Use reload for dev
