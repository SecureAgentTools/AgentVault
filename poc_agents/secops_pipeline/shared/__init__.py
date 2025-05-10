"""
Shared utilities for SecOps Pipeline components
"""

import logging
import os
import sys

# Setup basic logging for shared modules
logger = logging.getLogger(__name__)

# Import and initialize the registry helpers
# This will apply the monkey patch to agent_card_utils
try:
    from . import registry_helpers
    logger.info("Successfully imported registry_helpers")
except ImportError as e:
    logger.warning(f"Failed to import registry_helpers: {e}")
except Exception as e:
    logger.exception(f"Error during registry_helpers initialization: {e}")

# Import other shared modules
try:
    from . import task_state_helpers
    logger.info("Successfully imported task_state_helpers")
except ImportError as e:
    logger.warning(f"Failed to import task_state_helpers: {e}")
