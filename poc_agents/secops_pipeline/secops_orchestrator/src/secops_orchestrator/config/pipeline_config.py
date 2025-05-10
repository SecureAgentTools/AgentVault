"""
Pydantic-based configuration for the SecOps Pipeline.
Defines the structure expected in the JSON configuration file.
REQ-SECOPS-ORCH-1.3
"""
import os
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field, HttpUrl # Added HttpUrl
from typing import Optional

# Local exception type
class ConfigurationError(Exception): pass

logger = logging.getLogger(__name__)
# Assume APP_ROOT is defined appropriately for container/local execution context
APP_ROOT = Path(os.environ.get("APP_ROOT_DIR", "/app"))

# --- Configuration Model Components ---

class AgentTargetConfig(BaseModel):
    """Specifies how to target a required agent."""
    hri: str = Field(..., description="Human-Readable ID of the target agent (e.g., 'local-poc/secops-enrichment'). Used for discovery via registry.")
    # Add other optional fields if needed, like specific version constraints

class OrchestrationConfig(BaseModel):
    """General orchestration settings."""
    recursion_limit: int = Field(default=15, description="Maximum recursion depth for LangGraph execution.")
    # Registry URL is now primarily loaded from settings/env var, but can be here as fallback/override
    registry_url: Optional[HttpUrl] = Field(default=None, description="AgentVault Registry URL (Overrides env var if set here).")

class TimeoutConfig(BaseModel):
    """Timeout settings for agent interactions."""
    agent_call_timeout: float = Field(default=120.0, description="Timeout in seconds for synchronous-style A2A agent calls (initiate + wait for result).")
    sse_stream_timeout: float = Field(default=300.0, description="Timeout in seconds for waiting on the entire SSE event stream to complete.")

class SecopsPipelineConfig(BaseModel):
    """Master configuration model for the SecOps pipeline."""
    # Define required specialist agents based on workflow
    alert_ingestor_agent: Optional[AgentTargetConfig] = Field(default=None, description="Target config for the Alert Ingestor agent (Optional - ingest logic might be in orchestrator).")
    enrichment_agent: AgentTargetConfig = Field(..., description="Target config for the Enrichment agent.")
    investigation_agent: AgentTargetConfig = Field(..., description="Target config for the Investigation agent.")
    response_agent: AgentTargetConfig = Field(..., description="Target config for the Response agent.")
    # Add other agents if needed (e.g., separate ticketing agent)

    # General orchestration and timeout settings
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)

    @classmethod
    def load_from_json(cls, file_path: str) -> 'SecopsPipelineConfig':
        """Loads and validates configuration from a JSON file."""
        file_p = Path(file_path)
        # If path is relative, assume it's relative to APP_ROOT
        if not file_p.is_absolute():
            file_p = APP_ROOT / file_p

        if not file_p.is_file():
            logger.error(f"Configuration file not found at resolved path: {file_p.resolve()}")
            raise FileNotFoundError(f"SecOps config file '{file_path}' (resolved to {file_p.resolve()}) not found.")

        try:
            logger.info(f"Attempting to load SecOps pipeline configuration from: {file_p.resolve()}")
            with open(file_p, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # Validate the loaded data using Pydantic
            config = cls.model_validate(config_data)
            logger.info(f"Successfully loaded and validated SecOps config from {file_p.resolve()}")

            # Log loaded agent HRIs for verification
            if config.alert_ingestor_agent: logger.info(f"  Alert Ingestor HRI: {config.alert_ingestor_agent.hri}")
            logger.info(f"  Enrichment Agent HRI: {config.enrichment_agent.hri}")
            logger.info(f"  Investigation Agent HRI: {config.investigation_agent.hri}")
            logger.info(f"  Response Agent HRI: {config.response_agent.hri}")
            logger.info(f"  Registry URL (from config file): {config.orchestration.registry_url}")

            return config
        except json.JSONDecodeError as json_err:
            logger.error(f"Invalid JSON in config file {file_p.resolve()}: {json_err}", exc_info=True)
            raise ConfigurationError(f"Invalid JSON in config file {file_p.resolve()}: {json_err}") from json_err
        except Exception as e: # Catch Pydantic validation errors and others
            logger.error(f"Failed to load or validate config from {file_p.resolve()}: {e}", exc_info=True)
            raise ConfigurationError(f"Invalid or incomplete config in {file_p.resolve()}: {e}") from e

# --- Singleton Pattern for Config Loading ---
_config_cache: Optional[SecopsPipelineConfig] = None

def get_pipeline_config(config_path_override: Optional[str] = None) -> SecopsPipelineConfig:
    """
    Gets the pipeline configuration, loading it from file if necessary.
    Uses cached config unless an override path is provided.
    Prioritizes override path, then environment variable (via settings), then default path.
    Ensures registry_url is resolved.
    """
    global _config_cache
    # If override is given, always reload
    if config_path_override:
        logger.info(f"Loading SecOps config from override path: {config_path_override}")
        # Load directly, then check/update registry URL from settings
        loaded_config = SecopsPipelineConfig.load_from_json(config_path_override)
    # If cache exists and no override, return cache
    elif _config_cache is not None:
        logger.debug("Returning cached SecOps pipeline configuration.")
        return _config_cache
    # No override, no cache - load from settings (env var or default)
    else:
        from .settings import settings # Import locally to use latest settings potentially loaded from .env
        config_path = settings.SECOPS_PIPELINE_CONFIG # Load path from settings
        if not config_path:
             logger.critical("CRITICAL: No configuration path found in settings or override.")
             raise ConfigurationError("SecOps pipeline configuration path is required but not found.")
        try:
            loaded_config = SecopsPipelineConfig.load_from_json(config_path)
            _config_cache = loaded_config # Cache the loaded config
        except Exception as e:
            logger.critical(f"CRITICAL: Failed to load SecOps config from path '{config_path}': {e}", exc_info=True)
            raise # Re-raise critical configuration errors

    # --- Registry URL Resolution ---
    # Priority: 1) Value in JSON config, 2) Env Var (via settings), 3) Default in settings
    final_registry_url = None
    if loaded_config.orchestration.registry_url:
        final_registry_url = str(loaded_config.orchestration.registry_url) # Use URL from JSON file if present
        logger.info(f"Using Registry URL from config file: {final_registry_url}")
    else:
        # If not in JSON, use the value from settings (which loads from ENV or its own default)
        from .settings import settings
        final_registry_url = str(settings.AGENTVAULT_REGISTRY_URL)
        logger.info(f"Using Registry URL from settings/env var: {final_registry_url}")
        # Update the config object's value for consistency
        loaded_config.orchestration.registry_url = settings.AGENTVAULT_REGISTRY_URL # Assign Pydantic type

    if not final_registry_url: # Should be caught by settings validation ideally
         raise ConfigurationError("AgentVault Registry URL is required but not found.")

    # If caching (i.e., no override), store the potentially updated config
    if config_path_override is None:
        _config_cache = loaded_config

    return loaded_config
