"""
Pydantic-based configuration for the MCP Test Pipeline.
"""
import os
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional

class ConfigurationError(Exception): pass

logger = logging.getLogger(__name__)
APP_ROOT = Path("/app") # Assuming running inside container

class AgentTargetConfig(BaseModel): hri: str
class OrchestrationConfig(BaseModel):
    recursion_limit: int = Field(default=10)
    registry_url: str = Field(default="http://localhost:8000")
class TimeoutConfig(BaseModel):
    agent_call_timeout: float = Field(default=90.0)
    sse_stream_timeout: float = Field(default=60.0)

class McpTestPipelineConfig(BaseModel):
    """Master configuration for the MCP Test pipeline."""
    # Only need the proxy agent for this pipeline
    mcp_tool_proxy_agent: AgentTargetConfig
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)

    @classmethod
    def load_from_json(cls, file_path: str) -> 'McpTestPipelineConfig':
        file_p = Path(file_path)
        if not file_p.is_absolute(): file_p = APP_ROOT / file_p
        if not file_p.is_file(): raise FileNotFoundError(f"MCP Test config file {file_p.resolve()} not found.")
        try:
            with open(file_p, 'r', encoding='utf-8') as f: config_data = json.load(f)
            config = cls.model_validate(config_data)
            logger.info(f"Loaded MCP Test config from {file_p.resolve()}")
            logger.info(f"  MCP Proxy HRI: {config.mcp_tool_proxy_agent.hri}")
            return config
        except Exception as e: raise ConfigurationError(f"Invalid config in {file_p.resolve()}: {e}") from e

_config_cache: Optional[McpTestPipelineConfig] = None
def get_pipeline_config(config_path_override: Optional[str] = None) -> McpTestPipelineConfig:
    global _config_cache
    if _config_cache is not None and config_path_override is None: return _config_cache
    from .settings import settings # Import locally to avoid circular dependency potential
    config_path = config_path_override or settings.MCP_TEST_PIPELINE_CONFIG # Use the correct setting name
    if not config_path: raise ConfigurationError("MCP Test config path required.")
    try: loaded_config = McpTestPipelineConfig.load_from_json(config_path)
    except Exception as e: logger.critical(f"CRITICAL: Failed to load MCP Test config from '{config_path}': {e}"); raise
    if config_path_override is None: _config_cache = loaded_config
    return loaded_config
