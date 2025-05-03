# Pydantic models specific to the Trend Analysis Agent

from pydantic import BaseModel, Field
from typing import List, Optional

class TrendingData(BaseModel):
    timeframe: str
    trending_products: List[str] = Field(default_factory=list) # List of product IDs
    trending_categories: List[str] = Field(default_factory=list)

class TrendingDataArtifactContent(BaseModel):
    trending_data: TrendingData
