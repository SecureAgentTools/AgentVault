# Pydantic models for the Action Recommendation Agent

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Union, Literal

# --- Input Models ---
# Re-define nested structures for clarity and validation within this agent
# (Could potentially be shared via a common library later)
class AccountData(BaseModel):
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    status: Optional[str] = None
    # Add account_id if available and needed for context
    account_id: Optional[str] = None

class ContactData(BaseModel):
    name: str
    role: Optional[str] = None
    contact_id: Optional[int] = None # Assuming ID might be available

class OpportunityData(BaseModel):
    name: str
    stage: Optional[str] = None
    revenue: Optional[float] = None
    opportunity_id: Optional[int] = None # Assuming ID might be available

class CaseData(BaseModel):
    subject: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    case_id: Optional[int] = None # Assuming ID might be available

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

# Input validation model for the agent's skill
class RecommendInput(BaseModel):
    account_id: str
    dynamics_data: DynamicsDataPayload
    external_data: ExternalDataPayload
    account_analysis: AccountAnalysisPayload
    account_briefing: Optional[str] = None # Include optional briefing

# --- Output Models ---
# Model for a single recommended action (matches agent card and JSON schema)
class RecommendedAction(BaseModel):
    action_description: str
    rationale: str
    priority: Literal["High", "Medium", "Low"]
    related_record_id: Optional[str] = None # Made optional as LLM might not find it

    # Validator to ensure priority is one of the allowed values
    @field_validator('priority')
    def check_priority(cls, v):
        allowed = {"High", "Medium", "Low"}
        if v not in allowed:
            # Attempt to normalize common variations, default to Medium if unsure
            v_lower = v.lower()
            if "high" in v_lower: return "High"
            if "low" in v_lower: return "Low"
            return "Medium" # Default fallback
        return v

# Output data model (matches agent card output schema)
class RecommendOutput(BaseModel):
    recommended_actions: List[RecommendedAction] = Field(default_factory=list)
