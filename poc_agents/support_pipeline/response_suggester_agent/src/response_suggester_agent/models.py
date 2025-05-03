# Pydantic models specific to the Response Suggestion Agent
# REQ-SUP-SUG-004, REQ-SUP-SUG-005

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

# --- Models defining the expected input structure ---
# Re-define or import from a shared location if available
class TicketAnalysis(BaseModel):
    summary: str
    category: str
    sentiment: str
    extracted_entities: Dict[str, List[str]] = Field(default_factory=dict)

class KnowledgeBaseArticle(BaseModel):
    article_id: str
    title: str
    summary: str
    relevance_score: Optional[float] = None

class CustomerHistorySummary(BaseModel):
    customer_identifier: str
    status: str
    recent_interaction_summary: Optional[str] = None
    open_tickets: Optional[int] = None

# Input validation model (internal use)
class SuggestionInput(BaseModel):
    ticket_analysis: TicketAnalysis
    kb_results: List[KnowledgeBaseArticle] = Field(default_factory=list)
    customer_history: Optional[CustomerHistorySummary] = None

# Artifact content model (as defined in agent-card components)
class SuggestedResponseArtifactContent(BaseModel):
    suggested_response: str
