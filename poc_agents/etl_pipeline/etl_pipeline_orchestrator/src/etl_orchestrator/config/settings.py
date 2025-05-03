"""
Settings module for the ETL Pipeline Orchestrator.
Loads settings from .env file or environment variables.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Base directory assumptions for container
APP_ROOT = Path("/app")
ENV_FILE_PATH = APP_ROOT / ".env"
DEFAULT_CONFIG_PATH = APP_ROOT / "etl_config.json" # Default config file name

logger.info(f"Attempting to load .env file for ETL orchestrator from: {ENV_FILE_PATH}")
if not ENV_FILE_PATH.is_file():
    logger.warning(f".env file NOT found at {ENV_FILE_PATH}. Relying on environment variables.")

class Settings(BaseSettings):
    """Application settings."""
    RESEARCH_PIPELINE_CONFIG: Optional[str] = Field(
        default=str(DEFAULT_CONFIG_PATH), # Store as string
        description="Path to the JSON pipeline configuration file (relative to /app)."
    )
    AGENTVAULT_REGISTRY_URL: str = Field(
        default="http://localhost:8000",
        description="URL of the AgentVault Registry API."
    )
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_ENDPOINT: Optional[str] = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = "ETL Pipeline PoC"
    LOG_LEVEL: str = "INFO"

    # DB settings are intentionally omitted here - assuming agents handle their own connections

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.is_file() else None,
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

try:
    settings = Settings()
    log_level_int = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=log_level_int, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    logger.info("ETL orchestrator settings loaded.")
    logger.info(f"Registry URL set to: {settings.AGENTVAULT_REGISTRY_URL}")
    logger.info(f"Pipeline config file path (from settings): {settings.RESEARCH_PIPELINE_CONFIG}")
except Exception as e:
    logger.exception(f"CRITICAL: Failed to load ETL orchestrator settings: {e}")
    settings = Settings() # Load defaults on error
