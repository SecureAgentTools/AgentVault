# Pydantic models specific to the SecOps Enrichment Agent, if any.

from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Optional, Any

# Input validation model used in agent.py
class EnrichmentInput(BaseModel):
    iocs: List[str] = Field(..., min_length=1)
    project_id: str = Field(default="unknown")
    
# Structure for enrichment results
class EnrichmentDetails(BaseModel):
    source: Optional[str] = None
    reputation: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# Example: Define structure for enrichment results if desired
# class EnrichmentDetails(BaseModel):
#     source: str
#     reputation: str
#     details: Optional[Dict[str, Any]] = None
#
# class EnrichmentOutput(BaseModel):
#     results: Dict[str, EnrichmentDetails] # Map IOC string to details

# No other specific models needed for the current implementation
