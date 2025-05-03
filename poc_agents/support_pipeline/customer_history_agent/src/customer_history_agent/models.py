# Pydantic models specific to the Customer History Agent
# REQ-SUP-HIS-004, REQ-SUP-HIS-005, REQ-SUP-HIS-006

from pydantic import BaseModel, Field
from typing import Optional

# Input validation model (internal use)
class CustomerHistoryInput(BaseModel):
    customer_identifier: str

# Output data model (as defined in agent-card components)
class CustomerHistorySummary(BaseModel):
    customer_identifier: str
    status: str = Field(default="Unknown", examples=["VIP", "Standard", "New", "Churn Risk", "Unknown"])
    recent_interaction_summary: Optional[str] = None
    open_tickets: Optional[int] = None

# Artifact content model (as defined in agent-card components)
class CustomerHistoryArtifactContent(BaseModel):
    customer_history: CustomerHistorySummary
