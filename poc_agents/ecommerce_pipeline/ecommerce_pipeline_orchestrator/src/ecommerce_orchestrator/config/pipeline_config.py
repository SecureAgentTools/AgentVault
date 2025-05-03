"""
Central Pydantic-based configuration for the E-commerce Recommendation Pipeline.
"""

import os
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field, validator, HttpUrl
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

# Base directory is the app root in the container
APP_ROOT = Path("/app")
DEFAULT_ARTIFACTS_DIR = Path("/app/pipeline_artifacts/ecommerce")


# Agent Configuration Models
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

class EcommercePipelineConfig(BaseModel):
    """Master configuration for the e-commerce recommendation pipeline."""
    user_profile_agent: AgentTargetConfig
    product_catalog_agent: AgentTargetConfig
    trend_analysis_agent: AgentTargetConfig
    recommendation_engine_agent: AgentTargetConfig
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)

    def export_to_json(self, file_path: Optional[str] = None) -> str:
        """Export the configuration to JSON format."""
        try:
            config_dict = self.model_dump(mode='json')
            json_str = json.dumps(config_dict, indent=2)
            if file_path:
                # Resolve path relative to package root if not absolute
                file_p = Path(file_path)
                if not file_p.is_absolute():
                    file_p = ORCHESTRATOR_SRC_ROOT / file_p
                with open(file_p, 'w', encoding='utf-8') as f: f.write(json_str)
                logger.info(f"Exported e-commerce configuration to {file_p.resolve()}")
            return json_str
        except Exception as e:
            logger.error(f"Error exporting e-commerce configuration to JSON: {e}")
            return "{}"

    @classmethod
    def load_from_json(cls, file_path: str) -> 'EcommercePipelineConfig':
        """Load configuration from a JSON file (path relative to app root)."""
        file_p = Path(file_path)
        # Use the absolute path if provided, otherwise relative to app root
        if not file_p.is_absolute():
            file_p = APP_ROOT / file_p

        if not file_p.is_file():
            logger.error(f"Configuration file not found: {file_p.resolve()}. Using default configuration.")
            try:
                 return cls(
                     user_profile_agent=AgentTargetConfig(hri="local-poc/ecommerce-user-profile"),
                     product_catalog_agent=AgentTargetConfig(hri="local-poc/ecommerce-product-catalog"),
                     trend_analysis_agent=AgentTargetConfig(hri="local-poc/ecommerce-trend-analysis"),
                     recommendation_engine_agent=AgentTargetConfig(hri="local-poc/ecommerce-recommendation-engine")
                 )
            except Exception as default_err:
                 logger.error(f"Failed to create default config: {default_err}")
                 raise FileNotFoundError(f"Config file {file_p.resolve()} not found and default creation failed.")

        try:
            with open(file_p, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            config = cls.model_validate(config_data)
            logger.info(f"Successfully loaded e-commerce configuration from {file_p.resolve()}")
            return config
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {file_p.resolve()}: {e}.")
            raise ConfigurationError(f"Invalid JSON in config file {file_p.resolve()}") from e
        except Exception as e: # Catch Pydantic validation errors too
            logger.error(f"Error validating configuration from {file_p.resolve()}: {e}.")
            raise ConfigurationError(f"Invalid configuration in {file_p.resolve()}: {e}") from e

# --- Configuration Loading Function ---
_config_cache: Optional[EcommercePipelineConfig] = None

def get_pipeline_config(config_path_override: Optional[str] = None) -> EcommercePipelineConfig:
    """
    Gets the pipeline configuration, loading it from file or cache.
    Uses settings.RESEARCH_PIPELINE_CONFIG by default (relative to package root).
    """
    global _config_cache
    # --- MODIFIED: Always reload if override is provided ---
    if _config_cache is not None and config_path_override is None:
        logger.debug("Returning cached pipeline configuration.")
        return _config_cache
    # --- END MODIFIED ---

    from .settings import settings # Import here to avoid circular dependency at module level
    config_path = config_path_override or settings.RESEARCH_PIPELINE_CONFIG

    if not config_path:
        logger.warning("No configuration file path specified. Using default configuration object.")
        loaded_config = EcommercePipelineConfig(
             user_profile_agent=AgentTargetConfig(hri="local-poc/ecommerce-user-profile"),
             product_catalog_agent=AgentTargetConfig(hri="local-poc/ecommerce-product-catalog"),
             trend_analysis_agent=AgentTargetConfig(hri="local-poc/ecommerce-trend-analysis"),
             recommendation_engine_agent=AgentTargetConfig(hri="local-poc/ecommerce-recommendation-engine")
        )
    else:
        try:
            # load_from_json now handles path resolution relative to package root
            loaded_config = EcommercePipelineConfig.load_from_json(config_path)
        except (FileNotFoundError, ConfigurationError) as e:
            logger.error(f"Failed to load configuration from '{config_path}': {e}")
            logger.warning("Falling back to default configuration object.")
            loaded_config = EcommercePipelineConfig(
                 user_profile_agent=AgentTargetConfig(hri="local-poc/ecommerce-user-profile"),
                 product_catalog_agent=AgentTargetConfig(hri="local-poc/ecommerce-product-catalog"),
                 trend_analysis_agent=AgentTargetConfig(hri="local-poc/ecommerce-trend-analysis"),
                 recommendation_engine_agent=AgentTargetConfig(hri="local-poc/ecommerce-recommendation-engine")
            )

    # Ensure orchestration path exists
    try:
        Path(loaded_config.orchestration.artifact_base_path).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create artifact directory '{loaded_config.orchestration.artifact_base_path}': {e}")

    # Cache only if no override was provided
    if config_path_override is None:
        _config_cache = loaded_config

    return loaded_config
