import logging
import os
import json # Added json import
from pathlib import Path
# --- MODIFIED: Added typing imports ---
from typing import Any, Optional, Union, List, Dict, Annotated
# --- END MODIFIED ---
# --- MODIFIED: Added Request, Depends, JSONResponse ---
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
# --- END MODIFIED ---
# --- MODIFIED: Added BaseModel, Field from Pydantic ---
from pydantic import BaseModel, Field
# --- END MODIFIED ---

# Import tool functions and security setup
from .tools import read_file, write_file, list_directory
from .security import ROOT_DATA_DIR # Import the validated root dir

# Configure logging
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level_str, logging.INFO),
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Check if ROOT_DATA_DIR was configured successfully
if ROOT_DATA_DIR is None:
     logger.critical("FATAL: MCP Filesystem Server cannot start due to invalid root directory configuration.")
     # In a real scenario, prevent FastAPI from starting
     # raise SystemExit("Invalid root directory configuration.") # Option to exit hard

# --- Simple Tool Registry ---
class SimpleToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Any] = {}
    
    def register(self, name: str, func):
        """Register a tool function with a name"""
        self.tools[name] = func
        return func

# --- FastAPI App Initialization ---
app = FastAPI(title="Custom MCP Filesystem Server (Python/FastAPI)")

# --- Tool Registry Initialization ---
# This instance will be used by the RPC handler
tool_registry = SimpleToolRegistry()

# Register filesystem tools
tool_registry.register("filesystem.readFile", read_file)
tool_registry.register("filesystem.writeFile", write_file)
tool_registry.register("filesystem.listDirectory", list_directory)
logger.info(f"Registered tools: {list(tool_registry.tools.keys())}")


# SSE transport removed - only /rpc endpoint needed for proxy


# --- NEW: Stateless JSON-RPC Endpoint for Proxy ---

# Pydantic model for basic JSON-RPC request validation
class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field(default="2.0", pattern="^2.0$")
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None

# Dependency function to provide the tool registry instance
async def get_tool_registry() -> SimpleToolRegistry:
    """Provides the globally initialized tool registry instance."""
    logger.debug(f"[Dependency] Returning tool_registry instance: id={id(tool_registry)}")
    return tool_registry

# Helper to create JSON-RPC error responses
def create_jsonrpc_error(request_id: Optional[Union[str, int]], code: int, message: str, data: Optional[Any] = None) -> JSONResponse:
    """Creates a JSONResponse object for a JSON-RPC error."""
    error_obj = {"code": code, "message": message}
    if data is not None:
        error_obj["data"] = data
    # Map JSON-RPC error codes to appropriate HTTP status codes if desired
    status_code = 500 # Default to Internal Server Error
    if code == -32700 or code == -32600 or code == -32602:
        status_code = 400 # Bad Request
    elif code == -32601:
        status_code = 404 # Not Found

    return JSONResponse(
        status_code=status_code,
        content={
            "jsonrpc": "2.0",
            "error": error_obj,
            "id": request_id
        }
    )

@app.post("/rpc", response_class=JSONResponse, tags=["RPC"])
async def handle_rpc_request(
    payload: JsonRpcRequest, # Use Pydantic model for validation
    # Inject the tool registry using FastAPI's Depends
    registry: Annotated[SimpleToolRegistry, Depends(get_tool_registry)]
):
    """Handles stateless JSON-RPC POST requests (e.g., from the proxy)."""
    logger.info(f"Received RPC request (ID: {payload.id}) for method: {payload.method}")
    logger.debug(f"[RPC Handler] Injected registry: id={id(registry)}")

    # --- Tool Lookup and Execution ---
    # Access tools directly from registry
    tool_name = payload.method
    arguments = payload.params or {} # Use params dict or empty dict if None
    
    # Log available tools
    available_tools = list(registry.tools.keys())
    logger.debug(f"[RPC Handler] Tools available: {available_tools}")
    
    # Check if tool exists
    if tool_name not in registry.tools:
        logger.warning(f"Method '{tool_name}' not found in available tools")
        return create_jsonrpc_error(payload.id, -32601, f"Method not found: {tool_name}")
    
    # Get the tool function
    tool_func = registry.tools[tool_name]
    
    try:
        logger.debug(f"Attempting to call tool '{tool_name}' with args: {arguments}")
        
        # Call the tool function directly
        # The tools expect keyword arguments, so we'll call it with **arguments
        result = await tool_func(**arguments)

        # --- Success Response ---
        # The tool function (`read_file`, etc.) should return a dict
        # suitable for the 'result' field (including isError if applicable)
        logger.info(f"Successfully executed RPC method: {tool_name}")
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "result": result, # Tool function's return value goes here
            "id": payload.id
        })

    except ValueError as e:
        # This might be raised by function signature mismatch
        logger.error(f"Parameter error executing RPC method {tool_name}: {e}", exc_info=True)
        return create_jsonrpc_error(payload.id, -32602, f"Invalid params for method '{tool_name}': {e}")
    except TypeError as e:
        # Handles cases where params don't match tool signature (caught by call_tool/Tool.run)
        logger.error(f"Parameter error executing RPC method {tool_name}: {e}", exc_info=True)
        return create_jsonrpc_error(payload.id, -32602, f"Invalid params for method '{tool_name}': {e}")
    except Exception as e:
        # Catch other potential errors during tool execution lookup/call
        logger.exception(f"Unexpected error executing RPC method {tool_name}: {e}")
        return create_jsonrpc_error(payload.id, -32603, f"Internal server error during method execution: {e}")
    # --- END MODIFICATION ---

# --- Health Check and Root Endpoint ---
@app.get("/health", tags=["Management"])
async def health_check():
    """A standard health check endpoint."""
    if ROOT_DATA_DIR is None:
         return {"status": "error", "detail": "Root data directory not configured"}
    return {"status": "ok", "root_directory": str(ROOT_DATA_DIR)}

@app.get("/", include_in_schema=False)
async def read_root():
    return {"message": "Custom Filesystem MCP Server. Proxy RPC at /rpc."}


# --- Test File Initialization ---
@app.on_event("startup")
async def initialize_test_environment():
    """Create necessary test files for the MCP test pipeline"""
    if ROOT_DATA_DIR is None:
        logger.warning("ROOT_DATA_DIR is not configured, skipping test environment initialization")
        return
        
    logger.info("Initializing test environment...")
    
    # Check if we have write permissions to ROOT_DATA_DIR
    try:
        test_file = Path(ROOT_DATA_DIR) / ".write_test"
        test_file.touch()
        test_file.unlink()
        logger.info(f"Write permissions confirmed for {ROOT_DATA_DIR}")
    except Exception as e:
        logger.warning(f"No write permissions to {ROOT_DATA_DIR}: {e}")
        logger.info("Skipping test file creation due to permission issues")
        return
    
    # Define test files with their content
    test_files = {
        "test_script.py": """# Test script for MCP filesystem server
def test_function():
    print("Hello from test_script.py")
    return "Test successful"

if __name__ == "__main__":
    test_function()
""",
        "test_data.json": """{
    "name": "MCP Test Data",
    "version": "1.0.0",
    "description": "Test data for the MCP filesystem server",
    "test_array": [1, 2, 3],
    "test_object": {
        "key1": "value1",
        "key2": "value2"
    }
}
"""
    }

    # Create files in ROOT_DATA_DIR
    for file_name, content in test_files.items():
        file_path = Path(ROOT_DATA_DIR) / file_name
        
        try:
            # Create parent directories if needed (should already exist)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write the file
            with open(file_path, "w") as f:
                f.write(content.strip())
            
            logger.info(f"Created test file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to create test file {file_path}: {e}")
    
    logger.info("Test environment initialization completed")

logger.info("Custom MCP Filesystem Server application initialized with /rpc endpoint.")
