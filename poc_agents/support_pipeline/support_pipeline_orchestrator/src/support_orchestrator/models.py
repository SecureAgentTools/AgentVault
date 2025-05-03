# Pydantic models specific to the Support Pipeline Orchestrator State
# Based on REQ-SUP-ANA-005, REQ-SUP-KBS-005, REQ-SUP-HIS-005

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import datetime

# --- Ticket Analysis Models ---
class TicketAnalysis(BaseModel):
    summary: str
    category: str = Field(default="Unknown")
    sentiment: str = Field(default="Neutral")
    extracted_entities: Dict[str, List[str]] = Field(default_factory=dict)

# --- Knowledge Base Models ---
class KnowledgeBaseArticle(BaseModel):
    article_id: str
    title: str
    summary: str
    relevance_score: Optional[float] = None

# --- Customer History Models ---
class CustomerHistorySummary(BaseModel):
    customer_identifier: str
    status: str = Field(default="Standard")
    recent_interaction_summary: Optional[str] = None
    open_tickets: Optional[int] = None

# --- Artifact Content Schemas (for loading/saving) ---
class TicketAnalysisArtifactContent(BaseModel):
    ticket_analysis: TicketAnalysis

class KBSearchResultsArtifactContent(BaseModel):
    kb_results: List[KnowledgeBaseArticle]

class CustomerHistoryArtifactContent(BaseModel):
    customer_history: CustomerHistorySummary

class SuggestedResponseArtifactContent(BaseModel):
    suggested_response: str
