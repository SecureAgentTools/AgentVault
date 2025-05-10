"""
Models for the SecOps Investigation Agent.
Simplified version for debugging.
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

class InvestigationInput(BaseModel):
    """Input model for investigation requests."""
    alert: Dict[str, Any] = Field(default_factory=dict)
    enrichment: Dict[str, Any] = Field(default_factory=dict)

class InvestigationFindings(BaseModel):
    """Output model for investigation results."""
    severity: str = Field(default="Unknown", examples=["Low", "Medium", "High", "Critical"])
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str = Field(default="Investigation could not be completed.")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict)

    # Add compatibility methods for different Pydantic versions
    @classmethod
    def model_validate(cls, obj: Any) -> 'InvestigationFindings':
        """Compatibility wrapper for model validation."""
        # Try Pydantic v2 method first
        if hasattr(cls, "model_validate") and callable(getattr(cls, "model_validate")):
            try:
                return cls.model_validate(obj)
            except Exception:
                pass
        
        # Fall back to Pydantic v1 method
        if hasattr(cls, "parse_obj") and callable(getattr(cls, "parse_obj")):
            return cls.parse_obj(obj)
        
        # Last resort: direct instantiation
        return cls(**obj)

    def model_dump(self, mode='python', **kwargs) -> Dict[str, Any]:
        """Compatibility wrapper for model serialization."""
        # Try Pydantic v2 method first
        if hasattr(self, "model_dump") and callable(getattr(self, "model_dump")):
            try:
                return self.model_dump(**kwargs)
            except Exception:
                pass
        
        # Fall back to Pydantic v1 method
        if hasattr(self, "dict") and callable(getattr(self, "dict")):
            if mode == 'json':
                kwargs['exclude_none'] = kwargs.get('exclude_none', True)
            return self.dict(**kwargs)
        
        # Last resort: convert to dict using vars() or __dict__
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
