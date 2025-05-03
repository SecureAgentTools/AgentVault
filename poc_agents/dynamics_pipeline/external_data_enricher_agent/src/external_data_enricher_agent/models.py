# Pydantic models for the External Data Enrichment Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Input validation model (internal use)
class EnrichInput(BaseModel):
    website: str

# Model for the structure returned by the agent's skill
class ExternalDataPayload(BaseModel):
    news: List[str] = Field(default_factory=list)
    intent_signals: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)

# Output data model (matches agent card output schema)
class EnrichOutput(BaseModel):
    external_data: ExternalDataPayload
