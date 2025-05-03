"""
Configuration package for the Research Pipeline.

This package contains configuration modules for the research pipeline,
including the main pipeline_config module and settings utilities.
"""

from .pipeline_config import (
    get_pipeline_config,
    ResearchPipelineConfig,
    ResearchDepth,
    SearchEngineConfig,
    ScraperConfig,
    FactExtractionConfig,
    FactVerificationConfig,
    VisualizationConfig,
    ContentSynthesisConfig,
    EditorConfig,
    OrchestrationConfig
)
from .settings import settings

__all__ = [
    'get_pipeline_config',
    'ResearchPipelineConfig',
    'ResearchDepth',
    'SearchEngineConfig',
    'ScraperConfig',
    'FactExtractionConfig',
    'FactVerificationConfig',
    'VisualizationConfig',
    'ContentSynthesisConfig',
    'EditorConfig',
    'OrchestrationConfig',
    'settings'
]
