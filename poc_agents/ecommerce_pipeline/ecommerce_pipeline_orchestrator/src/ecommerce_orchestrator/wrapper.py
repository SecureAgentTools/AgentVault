"""
Wrapper script that runs the E-commerce Pipeline Orchestrator.
This is a simpler entry point for use inside the container.
"""

import asyncio
import logging
import sys
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Print configuration information for debugging
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"Python path: {sys.path}")

# Before importing, inject the arguments our script expects
# This avoids the argument parsing error
sys.argv = [sys.argv[0], "docker-test-user"]

try:
    from ecommerce_orchestrator.run import main
    logger.info("Successfully imported main from ecommerce_orchestrator.run")
except ImportError as e:
    logger.error(f"Error importing main function: {e}")
    sys.exit(1)

def run_orchestrator():
    """Simple wrapper to run the main function."""
    logger.info("Starting E-commerce Orchestrator via wrapper...")
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Error running main: {e}")
        sys.exit(1)
    
if __name__ == "__main__":
    run_orchestrator()
