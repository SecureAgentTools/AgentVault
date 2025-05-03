# Pydantic models for the Briefing Generator Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# --- Input Models (representing data received from orchestrator) ---
# Re-define nested structures for clarity and validation within this agent
class AccountData(BaseModel):
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    status: Optional[str] = None

class ContactData(BaseModel):
    name: str
    role: Optional[str] = None

class OpportunityData(BaseModel):
    name: str
    stage: Optional[str] = None
    revenue: Optional[float] = None

class CaseData(BaseModel):
    subject: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None

class DynamicsDataPayload(BaseModel):
    account: Optional[AccountData] = None
    contacts: List[ContactData] = Field(default_factory=list)
    opportunities: List[OpportunityData] = Field(default_factory=list)
    cases: List[CaseData] = Field(default_factory=list)

class ExternalDataPayload(BaseModel):
    news: List[str] = Field(default_factory=list)
    intent_signals: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)

class AccountAnalysisPayload(BaseModel):
    risk_level: str
    opportunity_level: str
    engagement_level: str
    analysis_summary: str

# Input validation model (internal use)
class BriefingInput(BaseModel):
    dynamics_data: DynamicsDataPayload
    external_data: ExternalDataPayload
    account_analysis: AccountAnalysisPayload

# Output data model (matches agent card output schema)
class BriefingOutput(BaseModel):
    account_briefing: str
