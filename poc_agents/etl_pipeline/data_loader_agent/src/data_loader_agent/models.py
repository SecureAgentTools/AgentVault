# Pydantic models for the Data Loader Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Input validation model (internal use)
class LoadInput(BaseModel):
    transformed_data_artifact_id: int
    validation_report_artifact_id: int
    run_id: str

# Output data model (matches agent card output schema)
class LoadOutput(BaseModel):
    artifact_db_id: int
    load_status: str = Field(..., examples=["Success", "Aborted", "Failed"])
    rows_processed: int
    rows_loaded: int

# Model for the validation report artifact content (needed for checking status)
class ValidationReport(BaseModel):
    total_rows_checked: int
    valid_rows: int
    invalid_rows: int
    status: str
    error_details: List[Dict[str, Any]] = Field(default_factory=list)

# Model for the load confirmation artifact content stored in DB
class LoadConfirmation(BaseModel):
    status: str = Field(..., examples=["Success", "Aborted", "Failed"])
    message: str
    rows_processed: int
    rows_loaded: int
    target_table: Optional[str] = None # Optional: Name of the mock target table used

class LoadConfirmationArtifact(BaseModel):
    confirmation: LoadConfirmation
