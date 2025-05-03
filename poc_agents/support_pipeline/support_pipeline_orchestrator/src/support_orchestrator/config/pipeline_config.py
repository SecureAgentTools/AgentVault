"""
Pydantic-based configuration for the Support Ticket Pipeline.
Adapts the e-commerce pipeline config structure. REQ-SUP-ORCH-002.
"""

import os
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field, validator, HttpUrl
from typing import List, Dict, Any, Optional, Union

# Import shared exception type if needed, or define locally
class ConfigurationError(Exception): pass

logger = logging.getLogger(__name__)

# Base directory is the app root in the container
APP_ROOT = Path("/app")
# Default artifact location specific to this pipeline (REQ-SUP-ORCH-002)
DEFAULT_ARTIFACTS_DIR = Path("/app/pipeline_artifacts/support")


# --- Reusable Sub-Models (identical to e-commerce example) ---
class AgentTargetConfig(BaseModel):
    """Configuration for identifying a target agent."""
    hri: str = Field(..., description="Human Readable ID of the target agent (used for registry lookup).")

class OrchestrationConfig(BaseModel):
    """Configuration for the LangGraph orchestration."""
    recursion_limit: int = Field(default=15, ge=5, le=50)
    artifact_base_path: str = Field(default=str(DEFAULT_ARTIFACTS_DIR.resolve()))
    registry_url: str = Field(default="http://localhost:8000", description="URL of the AgentVault Registry.")

class TimeoutConfig(BaseModel):
    """Timeout configurations for agent calls."""
    agent_call_timeout: float = Field(default=120.0, ge=10.0, le=600.0, description="Timeout in seconds for individual A2A agent calls.")
    sse_stream_timeout: float = Field(default=300.0, ge=30.0, le=1800.0, description="Timeout in seconds for waiting on SSE streams.")

# --- Support Pipeline Specific Configuration ---
class SupportPipelineConfig(BaseModel):
    """Master configuration for the support ticket pipeline."""
    # Agent Definitions (REQ-SUP-ORCH-002)
    ticket_analyzer_agent: AgentTargetConfig
    kb_search_agent: AgentTargetConfig
    customer_history_agent: AgentTargetConfig
    response_suggester_agent: AgentTargetConfig

    # Shared Config Sections
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)

    # --- Methods (can be reused from e-commerce example) ---
    def export_to_json(self, file_path: Optional[str] = None) -> str:
        """Export the configuration to JSON format."""
        try:
            config_dict = self.model_dump(mode='json')
            json_str = json.dumps(config_dict, indent=2)
            if file_path:
                file_p = Path(file_path)
                if not file_p.is_absolute():
                    # Assume relative to APP_ROOT if not absolute
                    file_p = APP_ROOT / file_p
                file_p.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
                with open(file_p, 'w', encoding='utf-8') as f: f.write(json_str)
                logger.info(f"Exported support pipeline configuration to {file_p.resolve()}")
            return json_str
        except Exception as e:
            logger.error(f"Error exporting support pipeline configuration to JSON: {e}")
            return "{}"

    @classmethod
    def load_from_json(cls, file_path: str) -> 'SupportPipelineConfig':
        """Load configuration from a JSON file (path relative to app root)."""
        file_p = Path(file_path)
        if not file_p.is_absolute():
            file_p = APP_ROOT / file_p

        if not file_p.is_file():
            logger.error(f"Configuration file not found: {file_p.resolve()}. Cannot load configuration.")
            raise FileNotFoundError(f"Support pipeline config file {file_p.resolve()} not found.")

        try:
            with open(file_p, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            config = cls.model_validate(config_data)
            logger.info(f"Successfully loaded support pipeline configuration from {file_p.resolve()}")
            return config
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {file_p.resolve()}: {e}.")
            raise ConfigurationError(f"Invalid JSON in config file {file_p.resolve()}") from e
        except Exception as e: # Catch Pydantic validation errors too
            logger.error(f"Error validating configuration from {file_p.resolve()}: {e}.")
            raise ConfigurationError(f"Invalid configuration in {file_p.resolve()}: {e}") from e

# --- Configuration Loading Function (adapted from e-commerce) ---
_config_cache: Optional[SupportPipelineConfig] = None

def get_pipeline_config(config_path_override: Optional[str] = None) -> SupportPipelineConfig:
    """
    Gets the support pipeline configuration, loading it from file or cache.
    Uses settings.RESEARCH_PIPELINE_CONFIG by default.
    """
    global _config_cache
    if _config_cache is not None and config_path_override is None:
        logger.debug("Returning cached support pipeline configuration.")
        return _config_cache

    from .settings import settings # Import here to avoid circular dependency
    config_path = config_path_override or settings.RESEARCH_PIPELINE_CONFIG

    if not config_path:
        logger.error("No configuration file path specified for support pipeline. Cannot proceed.")
        raise ConfigurationError("Support pipeline configuration file path is required but not specified.")

    try:
        # load_from_json now handles path resolution relative to APP_ROOT
        loaded_config = SupportPipelineConfig.load_from_json(config_path)
    except (FileNotFoundError, ConfigurationError) as e:
        logger.critical(f"CRITICAL: Failed to load support pipeline configuration from '{config_path}': {e}. Cannot proceed.")
        # Unlike e-commerce, we might consider this fatal if the config is essential
        raise ConfigurationError(f"Failed to load essential support pipeline config from {config_path}") from e

    # Ensure orchestration path exists (REQ-SUP-ORCH-006)
    try:
        Path(loaded_config.orchestration.artifact_base_path).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create artifact directory '{loaded_config.orchestration.artifact_base_path}': {e}")

    # Cache only if no override was provided
    if config_path_override is None:
        _config_cache = loaded_config

    return loaded_config
