# Pydantic models for the Dynamics Task Creator Agent

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

# Input validation model (internal use, matches skill input schema)
class CreateTaskInput(BaseModel):
    account_id: str
    task_subject: str
    priority: Literal["High", "Medium", "Low"]
    related_record_id: Optional[str] = None

# Output data model (matches skill output schema)
class CreateTaskOutput(BaseModel):
    success: bool
    message: str
    created_task_id: Optional[int] = None
