"""
Configuration package for the SecOps Pipeline Orchestrator.
Loads settings and pipeline configuration.
REQ-SECOPS-ORCH-1.3, REQ-SECOPS-ORCH-1.9
"""
from .pipeline_config import (
    get_pipeline_config,
    SecopsPipelineConfig, # Export the specific config model
    AgentTargetConfig,
    OrchestrationConfig,
    TimeoutConfig,
    ConfigurationError
)
from .settings import settings # Export the loaded settings instance

__all__ = [
    'get_pipeline_config',
    'SecopsPipelineConfig', # Make specific model available
    'AgentTargetConfig',
    'OrchestrationConfig',
    'TimeoutConfig',
    'ConfigurationError',
    'settings'
]
