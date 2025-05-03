# Pydantic models for the MCP Tool Proxy Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal, Union

# --- A2A Skill Input Model ---
class McpToolExecInput(BaseModel):
    target_mcp_server_id: str = Field(..., description="Logical identifier for the target MCP server (e.g., 'filesystem').")
    tool_name: str = Field(..., description="Name of the MCP tool to execute (e.g., 'filesystem.readFile').")
    arguments: Dict[str, Any] = Field(..., description="Arguments for the tool.")

# --- A2A Skill Output Models ---
class McpErrorDetails(BaseModel):
    """Structure for detailed error reporting."""
    source: Literal["A2A_PROXY", "MCP_PROTOCOL", "MCP_TOOL"]
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None # To hold raw MCP errors etc.
    
    # Safer model_dump method that avoids recursion issues
    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Compatibility method for Pydantic v1 to mimic v2's model_dump method.
        Uses a direct approach to avoid recursion issues between dict() and model_dump()
        """
        # Extract exclude_none option
        exclude_none = kwargs.pop('exclude_none', False)
        
        # Get model fields directly and create a dict
        data = {}
        for field_name, field_value in self.__dict__.items():
            # Skip internal fields (those starting with underscore)
            if field_name.startswith('_'):
                continue
                
            # Skip None values if exclude_none is True
            if exclude_none and field_value is None:
                continue
                
            # Handle nested Pydantic models
            if hasattr(field_value, 'model_dump') and callable(getattr(field_value, 'model_dump')):
                field_value = field_value.model_dump(**kwargs)
                
            data[field_name] = field_value
            
        return data
    
    # Safer model_dump_json method that avoids recursion issues
    def model_dump_json(self, **kwargs) -> str:
        """Compatibility method for Pydantic v1 to mimic v2's model_dump_json method.
        Uses model_dump to get data and then converts to JSON safely.
        """
        import json
        data = self.model_dump(**kwargs)
        return json.dumps(data)

class McpToolExecOutput(BaseModel):
    """Output model for the mcp.execute_tool skill."""
    success: bool
    mcp_result: Optional[Dict[str, Any]] = None # Holds the 'result' field from MCP response
    error: Optional[McpErrorDetails] = None # Holds structured error info

    # Add model_validate method for Pydantic v1 compatibility with v2 code
    @classmethod
    def model_validate(cls, obj: Any) -> 'McpToolExecOutput':
        """Compatibility method for Pydantic v1 to mimic v2's model_validate method."""
        # This is equivalent to parse_obj in v1
        return cls.parse_obj(obj)
        
    # Safer model_dump method that avoids recursion issues
    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Compatibility method for Pydantic v1 to mimic v2's model_dump method.
        Uses a direct approach to avoid recursion issues between dict() and model_dump()
        """
        # Extract exclude_none option
        exclude_none = kwargs.pop('exclude_none', False)
        
        # Get model fields directly and create a dict
        data = {}
        for field_name, field_value in self.__dict__.items():
            # Skip internal fields (those starting with underscore)
            if field_name.startswith('_'):
                continue
                
            # Skip None values if exclude_none is True
            if exclude_none and field_value is None:
                continue
                
            # Handle nested Pydantic models
            if hasattr(field_value, 'model_dump') and callable(getattr(field_value, 'model_dump')):
                field_value = field_value.model_dump(**kwargs)
                
            data[field_name] = field_value
            
        return data
    
    # Safer model_dump_json method that avoids recursion issues
    def model_dump_json(self, **kwargs) -> str:
        """Compatibility method for Pydantic v1 to mimic v2's model_dump_json method.
        Uses model_dump to get data and then converts to JSON safely.
        """
        import json
        data = self.model_dump(**kwargs)
        return json.dumps(data)

    # Ensure either mcp_result or error is present based on success
    # (Pydantic v2 root_validator equivalent - using model_validator)
    # @model_validator(mode='after')
    # def check_result_or_error(cls, data: Any) -> Any:
    #     if isinstance(data, McpToolExecOutput): # Check needed for v2
    #         if data.success and data.error is not None:
    #             raise ValueError("error must be null when success is true")
    #         if not data.success and data.mcp_result is not None:
    #             raise ValueError("mcp_result must be null when success is false")
    #         if not data.success and data.error is None:
    #             raise ValueError("error must be provided when success is false")
    #     return data
