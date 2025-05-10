"""
Settings module for the SecOps Pipeline Orchestrator.
Loads configuration from environment variables and .env file.
REQ-SECOPS-ORCH-1.3
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, HttpUrl # Use HttpUrl for validation
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Define application root relative to this file's location in src/config
APP_ROOT = Path(__file__).parent.parent.parent.parent.resolve() # Should resolve to /app in Docker
# Define path to .env file relative to APP_ROOT
ENV_FILE_PATH = APP_ROOT / ".env"
# Default config file path *within the container*
DEFAULT_CONFIG_PATH_STR = "/app/secops_pipeline_config.json" # Default JSON config path inside container

logger.info(f"Orchestrator APP_ROOT determined as: {APP_ROOT}")
logger.info(f"Attempting to load .env file for secops_orchestrator from: {ENV_FILE_PATH}")
if not ENV_FILE_PATH.is_file():
    logger.warning(f".env file NOT found at {ENV_FILE_PATH}. Will rely on defaults or environment variables.")
else:
     logger.info(".env file found.")

class Settings(BaseSettings):
    """Loads application settings from .env file or environment variables."""
    # --- Core Orchestration Settings ---
    # Path to the main JSON configuration file for the pipeline
    # Allow overriding via env var, default to path inside container
    SECOPS_PIPELINE_CONFIG: str = Field(
        default=DEFAULT_CONFIG_PATH_STR,
        description="Path to the JSON pipeline configuration file."
    )
    # AgentVault Registry URL - Use HttpUrl for validation
    AGENTVAULT_REGISTRY_URL: HttpUrl = Field(
        default="http://localhost:8000", # Default for local dev if not set in .env
        description="URL of the AgentVault Registry API."
    )

    # --- Observability (Optional) ---
    LANGCHAIN_TRACING_V2: str = Field(default="false")
    LANGCHAIN_ENDPOINT: Optional[str] = Field(default="https://api.smith.langchain.com")
    LANGCHAIN_API_KEY: Optional[str] = Field(default=None)
    LANGCHAIN_PROJECT: Optional[str] = Field(default="SecOps Pipeline PoC")

    # --- General ---
    LOG_LEVEL: str = Field(default="INFO")

    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.is_file() else None,
        env_file_encoding='utf-8',
        case_sensitive=False, # Environment variables are typically uppercase
        extra='ignore' # Ignore extra fields from .env that don't match
    )

# Load settings instance
try:
    settings = Settings()
    # Configure logging based on loaded settings
    log_level_int = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    # Use force=True to ensure root logger level is set even if already configured
    logging.basicConfig(level=log_level_int, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    # Set level for known orchestrator loggers
    logging.getLogger("secops_orchestrator").setLevel(log_level_int)
    logging.getLogger("a2a_client_wrapper").setLevel(log_level_int) # Also set for wrapper

    logger.info("SecOps orchestrator settings loaded successfully.")
    logger.info(f"  Registry URL (from settings): {settings.AGENTVAULT_REGISTRY_URL}")
    logger.info(f"  Pipeline Config Path (from settings): {settings.SECOPS_PIPELINE_CONFIG}")
    logger.info(f"  Log Level (from settings): {settings.LOG_LEVEL}")
except Exception as e:
    logger.exception(f"CRITICAL: Failed to load SecOps orchestrator settings: {e}")
    # Attempt to load with defaults if validation fails, log critical error
    logger.critical("Falling back to default settings due to loading error.")
    settings = Settings() # Create default instance
