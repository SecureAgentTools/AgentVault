"""
Settings module for the Research Pipeline.

This module provides environment-based settings using Pydantic's BaseSettings.
It handles .env file loading, environment variables, and basic configuration for
external services like S3, databases, and LangSmith.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Determine the root directory of this orchestrator component
CONFIG_DIR = Path(__file__).resolve().parent
ORCHESTRATOR_ROOT_DIR = CONFIG_DIR.parent.parent.parent  # Go up three levels (config/ -> langgraph_research_orchestrator/ -> src/ -> langgraph_scrapepipe/)
ENV_FILE_PATH = ORCHESTRATOR_ROOT_DIR / ".env"

logger.info(f"Attempting to load .env file for orchestrator from: {ENV_FILE_PATH}")
if not ENV_FILE_PATH.is_file():
    logger.warning(f".env file NOT found at {ENV_FILE_PATH}. Relying on environment variables.")


class Settings(BaseSettings):
    """
    Application settings derived from environment variables or .env file.
    
    These settings are primarily for external service connections and
    are separate from the pipeline configuration which controls behavior.
    """
    # Paths and Configuration
    RESEARCH_PIPELINE_CONFIG: Optional[str] = None  # Path to custom pipeline config
    
    # Database settings
    DATABASE_URL: Optional[str] = None  # Optional for now
    
    # S3/MinIO settings
    S3_BUCKET_NAME: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    MINIO_ENDPOINT_URL: Optional[str] = None  # For local MinIO

    # LangSmith/LangChain settings
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_ENDPOINT: Optional[str] = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = "LangGraph Research Pipeline"

    # Logging settings
    LOG_LEVEL: str = "INFO"
    
    # AgentVault connection settings
    AGENTVAULT_API_KEY: Optional[str] = None
    AGENTVAULT_REGISTRY_URL: Optional[str] = None
    
    # Default agent HRIs (can be overridden in config)
    TOPIC_RESEARCH_AGENT_HRI: str = "local-poc/topic-research"
    CONTENT_CRAWLER_AGENT_HRI: str = "local-poc/content-crawler"
    INFO_EXTRACTION_AGENT_HRI: str = "local-poc/information-extraction"
    FACT_VERIFICATION_AGENT_HRI: str = "local-poc/fact-verification"
    CONTENT_SYNTHESIS_AGENT_HRI: str = "local-poc/content-synthesis"
    EDITOR_AGENT_HRI: str = "local-poc/editor"
    VISUALIZATION_AGENT_HRI: str = "local-poc/visualization"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH if ENV_FILE_PATH.is_file() else None,
        env_file_encoding='utf-8',
        case_sensitive=False,  # Environment variables are often uppercase
        extra='ignore'
    )


try:
    settings = Settings()
    log_level_int = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    # Configure root logger - might be better to configure specific loggers later
    logging.basicConfig(level=log_level_int, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    logger.info("Orchestrator settings loaded.")
    
    # Log warnings about missing configurations
    if not settings.S3_BUCKET_NAME:
        logger.warning("S3_BUCKET_NAME not configured. Artifact storage to S3 will fail.")
    if settings.LANGCHAIN_TRACING_V2.lower() == "true" and not settings.LANGCHAIN_API_KEY:
        logger.warning("LangSmith tracing enabled (LANGCHAIN_TRACING_V2=true) but LANGCHAIN_API_KEY is not set.")

except Exception as e:
    logger.exception(f"CRITICAL: Failed to load orchestrator settings: {e}")
    # Set default settings or raise error if essential settings are missing
    settings = Settings()  # Load defaults
