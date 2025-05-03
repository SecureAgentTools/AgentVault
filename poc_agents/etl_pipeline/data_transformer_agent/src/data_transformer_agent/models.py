# Pydantic models for the Data Transformer Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Input validation model (internal use)
class TransformInput(BaseModel):
    raw_data_artifact_id: int
    run_id: str

# Output data model (matches agent card output schema)
class TransformOutput(BaseModel):
    artifact_db_id: int
    rows_transformed: int

# Model for the transformed data artifact content stored in DB
class TransformedData(BaseModel):
    item_id: str = Field(..., alias="Item ID") # Use alias for renamed column
    item_name: str = Field(..., alias="Item Name")
    item_type: str = Field(..., alias="Type")
    price: Optional[float] = Field(..., alias="Price") # Allow None if conversion fails

class TransformedDataArtifact(BaseModel):
    data: List[TransformedData]
