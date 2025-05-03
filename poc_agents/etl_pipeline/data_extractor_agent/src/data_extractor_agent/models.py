# Pydantic models for the Data Extractor Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any

# Input validation model (internal use)
class ExtractInput(BaseModel):
    source_path: str
    run_id: str

# Output data model (matches agent card output schema)
class ExtractOutput(BaseModel):
    artifact_db_id: int
    rows_extracted: int

# Model for the artifact content stored in DB (matches what's read from CSV)
# Assuming CSV has headers, read into list of dicts
class RawDataArtifact(BaseModel):
    data: List[Dict[str, Any]] # Store as list of dictionaries
