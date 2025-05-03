import os
import logging

logger = logging.getLogger(__name__)

# Default timeout if environment variable is not set or invalid
DEFAULT_TIMEOUT = 10

try:
    TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", DEFAULT_TIMEOUT))
    if TIMEOUT_SECONDS <= 0:
        logger.warning(f"Invalid TIMEOUT_SECONDS value ({TIMEOUT_SECONDS}), using default: {DEFAULT_TIMEOUT}s")
        TIMEOUT_SECONDS = DEFAULT_TIMEOUT
    else:
        logger.info(f"Code execution timeout set to: {TIMEOUT_SECONDS} seconds")
except ValueError:
    logger.warning(f"Could not parse TIMEOUT_SECONDS environment variable, using default: {DEFAULT_TIMEOUT}s")
    TIMEOUT_SECONDS = DEFAULT_TIMEOUT

# Add any other security-related constants or functions here if needed later
# For example, allowed modules for import, filesystem path restrictions etc.
# For now, security relies primarily on subprocess isolation and Docker hardening.
