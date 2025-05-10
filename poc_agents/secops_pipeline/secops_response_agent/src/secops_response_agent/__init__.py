# SecOps Response Agent Package
import logging
import sys
import os

# Setup basic logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

# Initialize import helpers
from .utils.import_helpers import ensure_shared_imports, get_task_state_helpers

# Ensure shared imports are available
ensure_shared_imports()

# Try to import registry helpers
try:
    import shared.registry_helpers
    logging.getLogger(__name__).info("Successfully imported registry_helpers")
    
    # Directly import the load_agent_card function to make it available at module level
    try:
        from shared.registry_helpers import load_agent_card
        logging.getLogger(__name__).info("Successfully imported load_agent_card function")
    except ImportError as e:
        logging.getLogger(__name__).warning(f"Failed to import load_agent_card: {e}")
except ImportError as e:
    logging.getLogger(__name__).warning(f"Failed to import registry_helpers: {e}")
except Exception as e:
    logging.getLogger(__name__).exception(f"Error during registry_helpers initialization: {e}")

# Try to apply task state helpers patch
try:
    task_state = get_task_state_helpers()
    patched = task_state.apply_taskstate_patch()
    if patched:
        logging.getLogger(__name__).info("TaskState patch applied successfully")
    else:
        logging.getLogger(__name__).warning("Failed to apply TaskState patch")
except Exception as e:
    logging.getLogger(__name__).warning(f"Error applying TaskState patch: {e}")
