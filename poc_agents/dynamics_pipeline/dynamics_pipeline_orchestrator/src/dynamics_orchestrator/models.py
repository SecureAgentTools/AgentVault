# Pydantic models specific to the Dynamics Pipeline Orchestrator State
# These mirror the structures expected to be returned by the agents

from pydantic import BaseModel, Field, field_validator, HttpUrl
from typing import List, Dict, Optional, Any, Literal

# --- Data structures expected in the state ---
class AccountData(BaseModel):
    account_id: Optional[str] = None # Added account_id
    name: str
    industry: Optional[str] = None
    website: Optional[HttpUrl] = None # Use HttpUrl for validation
    status: Optional[str] = None

class ContactData(BaseModel):
    contact_id: Optional[int] = None # Added contact_id
    name: str
    role: Optional[str] = None

class OpportunityData(BaseModel):
    opportunity_id: Optional[int] = None # Added opportunity_id
    name: str
    stage: Optional[str] = None
    revenue: Optional[float] = None

class CaseData(BaseModel):
    case_id: Optional[int] = None # Added case_id
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

# Added for Action Recommender Agent output
class RecommendedAction(BaseModel):
    action_description: str
    rationale: str
    priority: Literal["High", "Medium", "Low"]
    related_record_id: Optional[str] = None

# --- Agent Output Models (for validation in orchestrator nodes) ---
class DynamicsFetcherOutput(BaseModel):
    dynamics_data: DynamicsDataPayload

class ExternalEnricherOutput(BaseModel):
    external_data: ExternalDataPayload

class AccountAnalyzerOutput(BaseModel):
    account_analysis: AccountAnalysisPayload

# Added for Action Recommender Agent
class ActionRecommenderOutput(BaseModel):
    recommended_actions: List[RecommendedAction] = Field(default_factory=list)

class BriefingGeneratorOutput(BaseModel):
    account_briefing: str

# --- Added for Task Creator Agent output ---
class CreateTaskOutput(BaseModel):
    success: bool
    message: str
    created_task_id: Optional[int] = None

# --- Added for Notifier Agents output ---
class SendNotificationOutput(BaseModel):
    success: bool
    message: str
