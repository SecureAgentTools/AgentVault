"""
SecOps Investigation Agent package.
Simplified version for debugging.
"""
import logging
import sys
import os

# Setup basic logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

# Initialize import helpers
from .utils.import_helpers import ensure_shared_imports, get_task_state_helpers

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

# Expose key classes at package level
from .models import InvestigationInput, InvestigationFindings
