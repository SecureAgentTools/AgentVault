# Pydantic models for the SecOps MCP Tool Proxy Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal, Union

# --- A2A Skill Input Model ---
class McpToolExecInput(BaseModel):
    target_mcp_server_id: str = Field(..., description="Logical identifier for the target MCP server (e.g., 'tip_virustotal').")
    tool_name: str = Field(..., description="Name of the MCP tool to execute (e.g., 'ip.report').")
    arguments: Dict[str, Any] = Field(..., description="Arguments for the tool.")

# --- A2A Skill Output Models ---
class McpErrorDetails(BaseModel):
    """Structure for detailed error reporting."""
    source: Literal["A2A_PROXY", "MCP_PROTOCOL", "MCP_TOOL"]
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None # To hold raw MCP errors etc.
    
    # Non-recursive model_dump method
    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Compatibility method for Pydantic v1 to mimic v2's model_dump method."""
        exclude_none = kwargs.pop('exclude_none', False)
        
        data = {}
        for field_name, field_value in self.__dict__.items():
            if field_name.startswith('_'):
                continue
                
            if exclude_none and field_value is None:
                continue
                
            if hasattr(field_value, 'model_dump') and callable(getattr(field_value, 'model_dump')):
                field_value = field_value.model_dump(**kwargs)
                
            data[field_name] = field_value
            
        return data

class McpToolExecOutput(BaseModel):
    """Output model for the mcp.execute_tool skill."""
    success: bool
    mcp_result: Optional[Dict[str, Any]] = None # Holds the 'result' field from MCP response
    error: Optional[McpErrorDetails] = None # Holds structured error info

    # Add model_validate method for compatibility
    @classmethod
    def model_validate(cls, obj: Any) -> 'McpToolExecOutput':
        """Compatibility method for Pydantic v1 to mimic v2's model_validate method."""
        if hasattr(cls, 'parse_obj'):
            return cls.parse_obj(obj)
        else:
            return cls(**obj)
        
    # Non-recursive model_dump method
    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Safe model_dump implementation to avoid recursion issues."""
        exclude_none = kwargs.pop('exclude_none', False)
        
        data = {}
        for field_name, field_value in self.__dict__.items():
            if field_name.startswith('_'):
                continue
                
            if exclude_none and field_value is None:
                continue
                
            if hasattr(field_value, 'model_dump') and callable(getattr(field_value, 'model_dump')):
                try:
                    field_value = field_value.model_dump(**kwargs)
                except RecursionError:
                    # Fallback for recursion issues
                    if hasattr(field_value, '__dict__'):
                        field_value = field_value.__dict__.copy()
                
            data[field_name] = field_value
            
        return data
