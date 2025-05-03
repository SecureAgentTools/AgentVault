"""
Configuration package for the Support Pipeline Orchestrator.
"""

from .pipeline_config import (
    get_pipeline_config,
    SupportPipelineConfig,
    AgentTargetConfig, # Re-export for potential use
    OrchestrationConfig, # Re-export
    TimeoutConfig, # Re-export
    ConfigurationError # <<< ADDED IMPORT from pipeline_config
)
from .settings import settings

__all__ = [
    'get_pipeline_config',
    'SupportPipelineConfig',
    'AgentTargetConfig',
    'OrchestrationConfig',
    'TimeoutConfig',
    'ConfigurationError', # <<< ADDED TO EXPORTS
    'settings'
]
