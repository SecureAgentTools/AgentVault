"""
Settings module for the MCP Test Pipeline Orchestrator.
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

APP_ROOT = Path("/app")
ENV_FILE_PATH = APP_ROOT / ".env"
DEFAULT_CONFIG_PATH = APP_ROOT / "mcp_test_config.json" # Default config file name for this orchestrator

logger.info(f"Attempting to load .env file for mcp_test_orchestrator from: {ENV_FILE_PATH}")
if not ENV_FILE_PATH.is_file(): logger.warning(f".env file NOT found at {ENV_FILE_PATH}.")

class Settings(BaseSettings):
    """Application settings."""
    # Renamed setting to avoid clash if running both orchestrators
    MCP_TEST_PIPELINE_CONFIG: Optional[str] = Field(
        default=str(DEFAULT_CONFIG_PATH),
        alias="RESEARCH_PIPELINE_CONFIG", # Allow reading from the old name for compatibility
        description="Path to the JSON pipeline configuration file."
    )
    AGENTVAULT_REGISTRY_URL: str = Field(default="http://localhost:8000")
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_ENDPOINT: Optional[str] = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = "MCP Test Pipeline PoC"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.is_file() else None,
        env_file_encoding='utf-8', case_sensitive=False, extra='ignore'
    )

try:
    settings = Settings()
    # Add RESEARCH_PIPELINE_CONFIG in a way pydantic allows
    # Instead of setting directly on the model, we'll use __dict__ to add the field
    settings.__dict__['RESEARCH_PIPELINE_CONFIG'] = settings.MCP_TEST_PIPELINE_CONFIG
    log_level_int = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=log_level_int, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    logger.info("MCP Test orchestrator settings loaded.")
    logger.info(f"Registry URL: {settings.AGENTVAULT_REGISTRY_URL}")
    logger.info(f"Pipeline config file path: {settings.MCP_TEST_PIPELINE_CONFIG}")
except Exception as e:
    logger.exception(f"CRITICAL: Failed to load mcp_test_orchestrator settings: {e}")
    # Load defaults
    settings = Settings()
    # Add RESEARCH_PIPELINE_CONFIG in a way pydantic allows
    settings.__dict__['RESEARCH_PIPELINE_CONFIG'] = settings.MCP_TEST_PIPELINE_CONFIG
