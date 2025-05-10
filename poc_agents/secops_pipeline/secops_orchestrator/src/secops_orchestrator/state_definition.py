import logging
from typing import TypedDict, List, Optional, Dict, Any

# Import config and wrapper types for state typing (REQ-SECOPS-ORCH-1.4)
try:
    from .config import SecopsPipelineConfig
    # Import the actual wrapper class
    from .a2a_client_wrapper import A2AClientWrapper
except ImportError:
    # Placeholders if run in isolation or during early dev
    logging.getLogger(__name__).warning("Could not import config/wrapper for state definition typing.")
    class SecopsPipelineConfig: pass # type: ignore
    class A2AClientWrapper: pass # type: ignore

logger = logging.getLogger(__name__)

# REQ-SECOPS-ORCH-1.4: State Definition
class SecopsPipelineState(TypedDict):
    """LangGraph state definition for the SecOps Pipeline."""

    # --- Configuration and Infrastructure (Set at Start) ---
    pipeline_config: SecopsPipelineConfig
    a2a_wrapper: A2AClientWrapper
    project_id: str

    # --- Input Data (Set at Start) ---
    initial_alert_data: Optional[Dict[str, Any]] # Raw data from source

    # --- Pipeline Tracking ---
    current_step: Optional[str]   # Tracks the last completed node name
    error_message: Optional[str]  # Stores error details if a step fails

    # --- Intermediate Results (Populated by Nodes) ---
    # Derived from REQ-SECOPS-ORCH-1.4 placeholders
    standardized_alert: Optional[Dict[str, Any]] # Alert data after ingest/parsing
    enrichment_results: Optional[Dict[str, Any]] # Results from TIPs, internal lookups etc.
    investigation_findings: Optional[Dict[str, Any]] # Findings from log queries, analysis etc.
    determined_response_action: Optional[str] # e.g., "CREATE_TICKET", "BLOCK_IP", "CLOSE_FALSE_POSITIVE", None
    response_action_parameters: Optional[Dict[str, Any]] # Parameters needed for the response action
    response_action_status: Optional[Dict[str, Any]] # Status/result from the Response Agent

logger.info("SecopsPipelineState TypedDict defined.")
