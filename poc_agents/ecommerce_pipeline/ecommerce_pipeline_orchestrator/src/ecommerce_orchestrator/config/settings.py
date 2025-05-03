"""
Settings module for the E-commerce Pipeline Orchestrator.

Loads settings from .env file or environment variables.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Determine the root directory of this orchestrator component
CONFIG_DIR = Path(__file__).resolve().parent
# src/ecommerce_orchestrator/config -> src/ecommerce_orchestrator -> src -> /app
ORCHESTRATOR_SRC_ROOT = CONFIG_DIR.parent
# ORCHESTRATOR_ROOT_DIR = CONFIG_DIR.parent.parent.parent # Go up three levels from config
# ENV_FILE_PATH = ORCHESTRATOR_ROOT_DIR / ".env" # .env relative to project root

# Look for .env and config.json in the app root directory
ENV_FILE_PATH = Path("/app/.env")
DEFAULT_CONFIG_PATH = "/app/ecommerce_config.json"

# Add debug info about file availability
if ENV_FILE_PATH.is_file():
    print(f"DEBUG - .env file found at {ENV_FILE_PATH}")
else:
    print(f"DEBUG - .env file NOT found at {ENV_FILE_PATH}")

config_path = Path(DEFAULT_CONFIG_PATH)
if config_path.is_file():
    print(f"DEBUG - Config file found at {config_path}")
else:
    print(f"DEBUG - Config file NOT found at {config_path}")


logger.info(f"Attempting to load .env file for orchestrator from: {ENV_FILE_PATH}")
if not ENV_FILE_PATH.is_file():
    logger.warning(f".env file NOT found at {ENV_FILE_PATH}. Relying on environment variables.")


class Settings(BaseSettings):
    """
    Application settings derived from environment variables or .env file.
    """
    # Paths and Configuration
    RESEARCH_PIPELINE_CONFIG: Optional[str] = Field(
        default=DEFAULT_CONFIG_PATH, # Default config file name relative to package
        description="Path to the JSON pipeline configuration file (relative to package root)."
    )
    AGENTVAULT_REGISTRY_URL: str = Field(
        default="http://localhost:8000",
        description="URL of the AgentVault Registry API."
    )

    # LangSmith/LangChain settings
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_ENDPOINT: Optional[str] = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = "ECommerce Recommendation Pipeline"

    # Logging settings
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH if ENV_FILE_PATH.is_file() else None,
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

try:
    settings = Settings()
    log_level_int = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=log_level_int, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    logger.info("E-commerce orchestrator settings loaded.")
    logger.info(f"Registry URL set to: {settings.AGENTVAULT_REGISTRY_URL}")
    # Resolve the config path relative to the package root for clarity
    config_file_absolute_path = (ORCHESTRATOR_SRC_ROOT / settings.RESEARCH_PIPELINE_CONFIG).resolve()
    logger.info(f"Pipeline config file path (resolved): {config_file_absolute_path}")
    if settings.LANGCHAIN_TRACING_V2.lower() == "true" and not settings.LANGCHAIN_API_KEY:
        logger.warning("LangSmith tracing enabled (LANGCHAIN_TRACING_V2=true) but LANGCHAIN_API_KEY is not set.")

except Exception as e:
    logger.exception(f"CRITICAL: Failed to load orchestrator settings: {e}")
    settings = Settings() # Load defaults on error
