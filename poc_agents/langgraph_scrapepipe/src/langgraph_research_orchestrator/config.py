# Placeholder for Pydantic-Settings configuration loading
# Will load variables from .env file (DATABASE_URL, S3 settings, LangSmith keys, etc.)
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Determine the root directory of this orchestrator component
CONFIG_DIR = Path(__file__).resolve().parent
ORCHESTRATOR_ROOT_DIR = CONFIG_DIR.parent.parent # Go up two levels (src/ -> langgraph_scrapepipe/)
ENV_FILE_PATH = ORCHESTRATOR_ROOT_DIR / ".env"

logger.info(f"Attempting to load .env file for orchestrator from: {ENV_FILE_PATH}")
if not ENV_FILE_PATH.is_file():
    logger.warning(f".env file NOT found at {ENV_FILE_PATH}. Relying on environment variables.")

class Settings(BaseSettings):
    DATABASE_URL: Optional[str] = None # Optional for now
    S3_BUCKET_NAME: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    MINIO_ENDPOINT_URL: Optional[str] = None # For local MinIO

    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_ENDPOINT: Optional[str] = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = "LangGraph Research Pipeline"

    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH if ENV_FILE_PATH.is_file() else None,
        env_file_encoding='utf-8',
        case_sensitive=False, # Environment variables are often uppercase
        extra='ignore'
    )

try:
    settings = Settings()
    log_level_int = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    # Configure root logger - might be better to configure specific loggers later
    logging.basicConfig(level=log_level_int, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    logger.info("Orchestrator settings loaded.")
    if not settings.S3_BUCKET_NAME:
        logger.warning("S3_BUCKET_NAME not configured. Artifact storage to S3 will fail.")
    if settings.LANGCHAIN_TRACING_V2.lower() == "true" and not settings.LANGCHAIN_API_KEY:
        logger.warning("LangSmith tracing enabled (LANGCHAIN_TRACING_V2=true) but LANGCHAIN_API_KEY is not set.")

except Exception as e:
    logger.exception(f"CRITICAL: Failed to load orchestrator settings: {e}")
    # Set default settings or raise error if essential settings are missing
    settings = Settings() # Load defaults
    # raise e # Or re-raise if settings are absolutely critical
