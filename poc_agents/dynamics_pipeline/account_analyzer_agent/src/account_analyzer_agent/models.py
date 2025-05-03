# Pydantic models for the Account Health Analyzer Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# --- Input Models (representing data received from orchestrator) ---
# These mirror the structures returned by the previous agents
class AccountData(BaseModel): # Simplified from fetcher's output model
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

# Input validation model (internal use)
class AnalyzeInput(BaseModel):
    dynamics_data: DynamicsDataPayload
    external_data: ExternalDataPayload

# --- Output Models ---
# Model for the analysis result (matches agent card output schema)
class AccountAnalysisPayload(BaseModel):
    risk_level: str = Field(..., examples=["Low", "Medium", "High"])
    opportunity_level: str = Field(..., examples=["Low", "Medium", "High"])
    engagement_level: str = Field(..., examples=["Low", "Medium", "High"])
    analysis_summary: str

# Output data model (matches agent card output schema)
class AnalyzeOutput(BaseModel):
    account_analysis: AccountAnalysisPayload
