"""
Shared MCP Tool Proxy models used across agents in the SecOps pipeline.
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel

class McpErrorDetails(BaseModel):
    """Error details for MCP tool execution failures."""
    source: str
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

class McpToolExecOutput(BaseModel):
    """Output model for MCP tool execution results."""
    success: bool
    mcp_result: Optional[Dict[str, Any]] = None
    error: Optional[McpErrorDetails] = None
