# Pydantic models specific to the Ticket Analyzer Agent
# REQ-SUP-ANA-004, REQ-SUP-ANA-005, REQ-SUP-ANA-006

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

# Input validation model (internal use)
class TicketAnalysisInput(BaseModel):
    ticket_text: str
    customer_identifier: str

# Output data model (as defined in agent-card components)
class TicketAnalysis(BaseModel):
    summary: str
    category: str = Field(default="Unknown", examples=["Billing", "Technical", "Sales", "General Inquiry", "Unknown"])
    sentiment: str = Field(default="Neutral", examples=["Positive", "Negative", "Neutral"])
    extracted_entities: Dict[str, List[str]] = Field(default_factory=dict, examples=[{"product_names": ["Widget Pro"], "order_ids": ["12345"]}])

# Artifact content model (as defined in agent-card components)
class TicketAnalysisArtifactContent(BaseModel):
    ticket_analysis: TicketAnalysis
