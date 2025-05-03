"""
Pydantic-based configuration for the Dynamics Pipeline. REQ-DYN-ORCH-002.
"""
import os
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional

class ConfigurationError(Exception): pass

logger = logging.getLogger(__name__)
APP_ROOT = Path("/app")

class AgentTargetConfig(BaseModel): hri: str
class OrchestrationConfig(BaseModel):
    recursion_limit: int = Field(default=15)
    registry_url: str = Field(default="http://localhost:8000")
class TimeoutConfig(BaseModel):
    agent_call_timeout: float = Field(default=120.0)
    sse_stream_timeout: float = Field(default=300.0)

class DynamicsPipelineConfig(BaseModel):
    """Master configuration for the Dynamics pipeline."""
    fetcher_agent: AgentTargetConfig
    enricher_agent: AgentTargetConfig
    analyzer_agent: AgentTargetConfig
    recommender_agent: AgentTargetConfig
    briefing_agent: AgentTargetConfig
    # --- ADDED: New agent configs (REQ-DYN-EXEC-008) ---
    task_creator_agent: AgentTargetConfig
    slack_notifier_agent: AgentTargetConfig
    teams_notifier_agent: AgentTargetConfig
    # --- END ADDED ---
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)

    @classmethod
    def load_from_json(cls, file_path: str) -> 'DynamicsPipelineConfig':
        file_p = Path(file_path)
        if not file_p.is_absolute(): file_p = APP_ROOT / file_p
        if not file_p.is_file(): raise FileNotFoundError(f"Dynamics config file {file_p.resolve()} not found.")
        try:
            with open(file_p, 'r', encoding='utf-8') as f: config_data = json.load(f)
            config = cls.model_validate(config_data)
            logger.info(f"Loaded Dynamics config from {file_p.resolve()}")
            # --- ADDED: Log loaded HRIs for new agents ---
            logger.info(f"  Task Creator HRI: {config.task_creator_agent.hri}")
            logger.info(f"  Slack Notifier HRI: {config.slack_notifier_agent.hri}")
            logger.info(f"  Teams Notifier HRI: {config.teams_notifier_agent.hri}")
            # --- END ADDED ---
            return config
        except Exception as e: raise ConfigurationError(f"Invalid config in {file_p.resolve()}: {e}") from e

_config_cache: Optional[DynamicsPipelineConfig] = None
def get_pipeline_config(config_path_override: Optional[str] = None) -> DynamicsPipelineConfig:
    global _config_cache
    if _config_cache is not None and config_path_override is None: return _config_cache
    from .settings import settings
    config_path = config_path_override or settings.RESEARCH_PIPELINE_CONFIG
    if not config_path: raise ConfigurationError("Dynamics config path required.")
    try: loaded_config = DynamicsPipelineConfig.load_from_json(config_path)
    except Exception as e: logger.critical(f"CRITICAL: Failed to load Dynamics config from '{config_path}': {e}"); raise
    if config_path_override is None: _config_cache = loaded_config
    return loaded_config
