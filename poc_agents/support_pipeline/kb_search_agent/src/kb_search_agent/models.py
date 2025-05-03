# Pydantic models specific to the KB Search Agent
# REQ-SUP-KBS-004, REQ-SUP-KBS-005, REQ-SUP-KBS-006

from pydantic import BaseModel, Field
from typing import List, Optional

# Input validation model (internal use)
class KBSearchInput(BaseModel):
    category: str
    keywords: Optional[List[str]] = None
    limit: int = 5

# Output data model (as defined in agent-card components)
class KnowledgeBaseArticle(BaseModel):
    article_id: str
    title: str
    summary: str
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

# Artifact content model (as defined in agent-card components)
class KBSearchResultsArtifactContent(BaseModel):
    kb_results: List[KnowledgeBaseArticle]
