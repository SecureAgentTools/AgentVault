# Pydantic models specific to the Product Catalog Agent

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Dict, Optional, Any

class ProductDetail(BaseModel):
    product_id: str
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    image_url: Optional[HttpUrl] = None
    stock_level: Optional[int] = None
    attributes: Dict[str, Any] = Field(default_factory=dict) # For other details

class ProductDetailsArtifactContent(BaseModel):
    product_details: List[ProductDetail]
