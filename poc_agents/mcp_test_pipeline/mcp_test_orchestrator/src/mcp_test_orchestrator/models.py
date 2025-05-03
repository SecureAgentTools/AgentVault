# Pydantic models specific to the MCP Test Pipeline Orchestrator State
# Primarily uses models defined in the proxy agent or core library

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

# Import the proxy agent's output model for validation within nodes
try:
    # Adjust path relative to this orchestrator's src
    from mcp_tool_proxy_agent.models import McpToolExecOutput
except ImportError:
    # Define placeholder if proxy models aren't accessible during isolated testing
    class McpToolExecOutput(BaseModel):
        success: bool
        mcp_result: Optional[Dict[str, Any]] = None
        error: Optional[Dict[str, Any]] = None

# Example: If the code execution tool returns structured output
class CodeExecutionResult(BaseModel):
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    return_code: Optional[int] = None
    # Add other fields if the code runner MCP server provides them
