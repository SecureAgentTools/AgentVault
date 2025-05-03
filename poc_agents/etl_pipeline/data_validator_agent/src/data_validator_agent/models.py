# Pydantic models for the Data Validator Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Input validation model (internal use)
class ValidateInput(BaseModel):
    transformed_data_artifact_id: int
    run_id: str

# Output data model (matches agent card output schema)
class ValidateOutput(BaseModel):
    artifact_db_id: int
    validation_status: str = Field(..., examples=["Success", "Warnings", "Failed"])
    invalid_rows: int

# Model for the validation report artifact content stored in DB
class ValidationErrorDetail(BaseModel):
    row_index: int # Original index might be tricky, use index in transformed list
    error_message: str
    row_data: Dict[str, Any]

class ValidationReport(BaseModel):
    total_rows_checked: int
    valid_rows: int
    invalid_rows: int
    status: str = Field(..., examples=["Success", "Warnings", "Failed"])
    error_details: List[ValidationErrorDetail] = Field(default_factory=list) # Store first N errors

class ValidationReportArtifact(BaseModel):
    report: ValidationReport
