# Pydantic models specific to the ETL Pipeline Orchestrator State (if any)
# Currently, agents return simple dicts with IDs, so no complex models needed here.
# We might define internal input/output models for clarity if desired later.

from pydantic import BaseModel
from typing import Optional

# Example: Could define a model for the final result if needed
class EtlPipelineResult(BaseModel):
    project_id: str
    status: str
    final_load_status: Optional[str] = None
    load_confirmation_artifact_id: Optional[int] = None
    error_message: Optional[str] = None
