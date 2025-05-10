"""
Application lifecycle management for SecOps Investigation Agent
"""

import logging
import os
import sys
from typing import Optional

# Add import path for shared modules
sys.path.append('/app/shared')

# Import LLM client if available
try:
    from llm_client import close_llm_client
    _LLM_CLIENT_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Could not import LLM client for lifecycle management.")
    _LLM_CLIENT_AVAILABLE = False
    # Create a dummy function to avoid errors
    async def close_llm_client():
        pass

logger = logging.getLogger(__name__)

async def shutdown_handler():
    """Handle application shutdown tasks."""
    logger.info("Executing shutdown handler...")
    
    # Close LLM client if available
    if _LLM_CLIENT_AVAILABLE:
        try:
            await close_llm_client()
            logger.info("LLM client closed successfully.")
        except Exception as e:
            logger.error(f"Error closing LLM client: {str(e)}")
    
    logger.info("Shutdown handler completed.")

def register_shutdown_handler(app):
    """Register shutdown handler with the FastAPI app."""
    @app.on_event("shutdown")
    async def app_shutdown_event():
        await shutdown_handler()
