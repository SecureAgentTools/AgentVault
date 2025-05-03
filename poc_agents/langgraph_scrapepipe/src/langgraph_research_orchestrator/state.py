import logging
from typing import TypedDict, List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Define the structure for the state that will be passed around the graph.
class ResearchState(TypedDict):
    """
    Represents the overall state of the research pipeline graph.
    Stores inputs, intermediate results (as local file paths), and final outputs.
    """
    # Initial inputs
    initial_topic: str
    initial_config: Dict[str, Any]

    # Tracking & Error Handling
    project_id: str
    current_step: Optional[str]
    error_message: Optional[str]

    # Agent Outputs (Small ones stored directly)
    research_plan: Optional[Dict[str, Any]]
    search_queries: Optional[List[Dict[str, Any]]] # Changed from List[str]

    # Store local file paths instead of S3 URIs
    local_artifact_references: Dict[str, str] # Maps artifact type to absolute local file path

    # Store paths to final outputs
    final_article_local_path: Optional[str]
    final_visualization_local_path: Optional[str]

# Example state:
# {
#     ... initial inputs ...
#     "project_id": "proj_xyz",
#     "current_step": "content_crawler",
#     "error_message": None,
#     "research_plan": {...},
#     "search_queries": [{"subtopic": "...", "queries": ["..."]}],
#     "local_artifact_references": {
#         "raw_content": "/path/to/langgraph_scrapepipe/pipeline_artifacts/proj_xyz/content_crawler/raw_content.json"
#     },
#     "final_article_local_path": None,
#     "final_visualization_local_path": None
# }

logger.info("ResearchState TypedDict defined for local artifact storage.")
