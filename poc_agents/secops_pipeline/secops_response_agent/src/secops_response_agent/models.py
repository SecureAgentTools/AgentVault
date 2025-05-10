# Pydantic models specific to the SecOps Response Agent.

from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Optional, Any

# Input validation model used in agent.py
class ResponseActionInput(BaseModel):
    action_type: str # Examples: "CREATE_TICKET", "BLOCK_IP"
    parameters: Dict[str, Any]

    # Add model_validate for Pydantic V1 compatibility if needed
    @classmethod
    def model_validate(cls, obj: Any) -> 'ResponseActionInput':
        # Basic check for demonstration
        if not isinstance(obj, dict):
            # Allow Pydantic models to be passed directly for validation as well
            if not hasattr(obj, "__pydantic_fields__"): # Simple check for Pydantic model
                 raise TypeError(f"Expected dict or Pydantic model, got {type(obj)}")
        # Directly construct instance instead of calling parse_obj to avoid recursion
        if hasattr(obj, "dict") and callable(obj.dict):
            obj = obj.dict()
        return cls(**obj)


# Output validation model for the response agent (matches agent card)
class ActionStatusDetails(BaseModel):
    ticket_id: Optional[str] = Field(default=None)
    block_status: Optional[str] = Field(default=None)
    block_rule_id: Optional[str] = Field(default=None)  # Add firewall rule ID
    isolation_status: Optional[str] = Field(default=None)
    isolation_id: Optional[str] = Field(default=None)  # Add isolation session ID
    target_ip: Optional[str] = Field(default=None)  # Target IP for block actions
    target_host: Optional[str] = Field(default=None)  # Target host for isolation actions
    error_details: Optional[Any] = Field(default=None) # Can be string or dict from proxy
    # Add other action-specific details as needed
    raw_mcp_result: Optional[Dict[str, Any]] = Field(default=None, description="Raw mcp_result from proxy if available")


class ActionExecutionResult(BaseModel):
    action: str
    status: str # "Success", "Failed", "Error"
    details: Optional[ActionStatusDetails] = Field(default_factory=ActionStatusDetails) # Ensure details is always present

    # Add model_dump for Pydantic V1 compatibility if needed
    def model_dump(self, **kwargs) -> Dict[str, Any]:
        # More careful Pydantic v1/v2 dump
        exclude_none = kwargs.pop('exclude_none', False)
        # Remove 'mode' parameter if present (Pydantic v1 doesn't support it)
        kwargs.pop('mode', None)
        
        # Get dict representation directly to avoid recursion
        base_dict = self.__dict__.copy() if hasattr(self, '__dict__') else {}
        
        # Process the dict representation
        data = {}
        for k, v in base_dict.items():
            # Skip private attributes
            if k.startswith('_'):
                continue
            
            # Handle None values if exclude_none is True
            if exclude_none and v is None:
                continue
                
            # Handle nested Pydantic models
            if hasattr(v, 'model_dump') and callable(v.model_dump):
                data[k] = v.model_dump(exclude_none=exclude_none)
            elif hasattr(v, 'dict') and callable(v.dict):
                data[k] = v.dict(exclude_none=exclude_none)
            else:
                data[k] = v
                
        return data
