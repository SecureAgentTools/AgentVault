# Pydantic models specific to the User Profile Agent (if needed beyond core)
# For now, using the shared models defined in the orchestrator plan.
# If complex internal logic requires specific models, define them here.

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import datetime

class UserPreferences(BaseModel):
    categories: List[str] = Field(default_factory=list)
    brands: List[str] = Field(default_factory=list)

class UserProfile(BaseModel):
    user_id: str
    purchase_history: List[str] = Field(default_factory=list) # List of product IDs
    browsing_history: List[str] = Field(default_factory=list) # List of product IDs
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    last_active: Optional[datetime.datetime] = None

class UserProfileArtifactContent(BaseModel):
    user_profile: UserProfile
