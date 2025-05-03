# Pydantic models for the Dynamics Data Fetcher Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Input validation model (internal use)
class FetchInput(BaseModel):
    account_id: str

# Define structure for data returned (can be simplified if needed)
class AccountData(BaseModel):
    account_id: str
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    status: Optional[str] = None

class ContactData(BaseModel):
    contact_id: int
    account_id: str
    name: str
    role: Optional[str] = None

class OpportunityData(BaseModel):
    opportunity_id: int
    account_id: str
    name: str
    stage: Optional[str] = None
    revenue: Optional[float] = None # Use float for potential decimal from NUMERIC

class CaseData(BaseModel):
    case_id: int
    account_id: str
    subject: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None

# Model for the structure returned by the agent's skill
class DynamicsDataPayload(BaseModel):
    account: Optional[AccountData] = None
    contacts: List[ContactData] = Field(default_factory=list)
    opportunities: List[OpportunityData] = Field(default_factory=list)
    cases: List[CaseData] = Field(default_factory=list)

# Output data model (matches agent card output schema)
class FetchOutput(BaseModel):
    dynamics_data: DynamicsDataPayload
