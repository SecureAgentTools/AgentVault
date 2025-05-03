"""
Pydantic-based configuration for the ETL Pipeline. REQ-ETL-ORCH-002.
"""

import os
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field, validator, HttpUrl
from typing import List, Dict, Any, Optional, Union

class ConfigurationError(Exception): pass

logger = logging.getLogger(__name__)

APP_ROOT = Path("/app")
# No default artifact dir needed if orchestrator doesn't save files

# --- Reusable Sub-Models ---
class AgentTargetConfig(BaseModel):
    hri: str = Field(..., description="Human Readable ID of the target agent.")

class OrchestrationConfig(BaseModel):
    recursion_limit: int = Field(default=15, ge=5, le=50)
    # artifact_base_path is not needed if using DB artifacts exclusively
    registry_url: str = Field(default="http://localhost:8000", description="URL of the AgentVault Registry.")

class TimeoutConfig(BaseModel):
    agent_call_timeout: float = Field(default=180.0, ge=10.0, le=600.0) # Increased default for potentially longer ETL steps
    sse_stream_timeout: float = Field(default=300.0, ge=30.0, le=1800.0)

# --- ETL Pipeline Specific Configuration ---
class EtlPipelineConfig(BaseModel):
    """Master configuration for the ETL pipeline."""
    extractor_agent: AgentTargetConfig
    transformer_agent: AgentTargetConfig
    validator_agent: AgentTargetConfig
    loader_agent: AgentTargetConfig
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)

    # DB Config is intentionally omitted here - agents load from their own .env

    @classmethod
    def load_from_json(cls, file_path: str) -> 'EtlPipelineConfig':
        """Load configuration from a JSON file (path relative to app root)."""
        file_p = Path(file_path)
        if not file_p.is_absolute(): file_p = APP_ROOT / file_p
        if not file_p.is_file(): raise FileNotFoundError(f"ETL pipeline config file {file_p.resolve()} not found.")
        try:
            with open(file_p, 'r', encoding='utf-8') as f: config_data = json.load(f)
            config = cls.model_validate(config_data)
            logger.info(f"Successfully loaded ETL pipeline configuration from {file_p.resolve()}")
            return config
        except json.JSONDecodeError as e: raise ConfigurationError(f"Invalid JSON in config file {file_p.resolve()}") from e
        except Exception as e: raise ConfigurationError(f"Invalid configuration in {file_p.resolve()}: {e}") from e

# --- Configuration Loading Function ---
_config_cache: Optional[EtlPipelineConfig] = None

def get_pipeline_config(config_path_override: Optional[str] = None) -> EtlPipelineConfig:
    """Gets the ETL pipeline configuration."""
    global _config_cache
    if _config_cache is not None and config_path_override is None: return _config_cache

    from .settings import settings
    config_path = config_path_override or settings.RESEARCH_PIPELINE_CONFIG
    if not config_path: raise ConfigurationError("ETL pipeline configuration file path is required.")

    try: loaded_config = EtlPipelineConfig.load_from_json(config_path)
    except (FileNotFoundError, ConfigurationError) as e: logger.critical(f"CRITICAL: Failed to load ETL config from '{config_path}': {e}"); raise
    except Exception as e: logger.critical(f"CRITICAL: Unexpected error loading ETL config: {e}"); raise ConfigurationError("Unexpected error loading ETL config") from e

    if config_path_override is None: _config_cache = loaded_config
    return loaded_config
