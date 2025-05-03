# Pydantic models specific to the E-commerce Pipeline Orchestrator
# Re-define shared models here for clarity or import from a shared location

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Dict, Optional, Any
import datetime

# --- User Profile ---
class UserPreferences(BaseModel):
    categories: List[str] = Field(default_factory=list)
    brands: List[str] = Field(default_factory=list)

class UserProfile(BaseModel):
    user_id: str
    purchase_history: List[str] = Field(default_factory=list)
    browsing_history: List[str] = Field(default_factory=list)
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    last_active: Optional[datetime.datetime] = None

# --- Product Catalog ---
class ProductDetail(BaseModel):
    product_id: str
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    image_url: Optional[HttpUrl] = None
    stock_level: Optional[int] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)

# --- Trend Analysis ---
class TrendingData(BaseModel):
    timeframe: str
    trending_products: List[str] = Field(default_factory=list)
    trending_categories: List[str] = Field(default_factory=list)

# --- Recommendations ---
class ProductRecommendation(BaseModel):
    product_id: str
    recommendation_score: float = Field(..., ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    details: Optional[ProductDetail] = None # Embed details if needed

# --- Artifact Content Schemas ---
class UserProfileArtifactContent(BaseModel):
    user_profile: UserProfile

class ProductDetailsArtifactContent(BaseModel):
    product_details: List[ProductDetail]

class TrendingDataArtifactContent(BaseModel):
    trending_data: TrendingData

class RecommendationsArtifactContent(BaseModel):
    recommendations: List[ProductRecommendation]
