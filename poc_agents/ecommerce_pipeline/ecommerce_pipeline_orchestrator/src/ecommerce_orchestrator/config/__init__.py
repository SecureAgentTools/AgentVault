"""
Configuration package for the E-commerce Pipeline Orchestrator.
"""

from .pipeline_config import (
    get_pipeline_config,
    EcommercePipelineConfig
    # Add other specific config models if needed
)
from .settings import settings

__all__ = [
    'get_pipeline_config',
    'EcommercePipelineConfig',
    'settings'
]
