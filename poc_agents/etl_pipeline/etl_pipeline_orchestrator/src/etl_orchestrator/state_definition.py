import logging
from typing import TypedDict, List, Optional, Dict, Any

# Import config and wrapper types for state typing
try:
    from etl_orchestrator.config import EtlPipelineConfig
    # Placeholder for A2AClientWrapper
    class A2AClientWrapper: pass
except ImportError:
    class EtlPipelineConfig: pass # type: ignore
    class A2AClientWrapper: pass # type: ignore

logger = logging.getLogger(__name__)

# Define the structure for the state passed around the ETL graph.
# REQ-ETL-ORCH-003
class EtlProcessingState(TypedDict):
    """
    Represents the overall state of the ETL processing pipeline graph.
    """
    # --- Initial inputs & Configuration ---
    source_identifier: str             # Path or identifier for the source data (e.g., "/data/input.csv")
    pipeline_config: EtlPipelineConfig # Holds the validated pipeline config
    a2a_wrapper: A2AClientWrapper      # Holds the initialized A2A wrapper instance

    # --- Tracking & Error Handling ---
    project_id: str                    # Unique ID for this pipeline run (used as run_id in DB)
    current_step: Optional[str]        # Name of the last executed node
    error_message: Optional[str]       # Stores error messages if a step fails

    # --- Artifact Management (Using DB IDs) --- REQ-ETL-ORCH-006
    # Stores database primary keys of the artifacts created by agents
    db_artifact_references: Dict[str, int] # e.g., {"raw_data": 1, "transformed_data": 5, ...}

    # --- Final result indicator ---
    final_load_status: Optional[str]   # Status reported by the loader agent (e.g., "Success", "Aborted")

logger.info("EtlProcessingState TypedDict defined.")
