# Pydantic models for the Teams Notifier Agent

from pydantic import BaseModel, Field
from typing import Optional

# Input validation model (internal use, matches skill input schema)
class SendNotificationInput(BaseModel):
    target: str = Field(..., description="The target Teams webhook URL or chat ID.")
    message_text: str = Field(..., description="The text content of the message.")

# Output data model (matches skill output schema)
class SendNotificationOutput(BaseModel):
    success: bool
    message: str
