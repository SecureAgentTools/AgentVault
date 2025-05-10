"""
Helper functions for working with TaskState objects across all agents
"""

import logging

logger = logging.getLogger(__name__)

# Import definitions with fallback
try:
    from agentvault.models import TaskState
    _AGENTVAULT_AVAILABLE = True
    logger.debug("Successfully imported TaskState from agentvault.models")
except ImportError:
    logger.warning("Failed to import TaskState from agentvault.models, using fallback definition")
    class TaskState:
        SUBMITTED = "SUBMITTED"
        WORKING = "WORKING"
        INPUT_REQUIRED = "INPUT_REQUIRED"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"
        CANCELED = "CANCELED"
    _AGENTVAULT_AVAILABLE = False

# Define terminal states consistently
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELED"}

def is_terminal(state):
    """
    Helper function to check if a TaskState is terminal.
    Works with both enum members and string representations.
    """
    if hasattr(state, 'value'):
        # It's the enum version
        state_str = str(state.value)
    else:
        # It's already a string
        state_str = str(state)
        
    return state_str in TERMINAL_STATES

# Monkey patch the is_terminal method to TaskState objects
def apply_taskstate_patch():
    """
    Applies the is_terminal method to the TaskState class if it doesn't exist.
    """
    if _AGENTVAULT_AVAILABLE and not hasattr(TaskState, 'is_terminal'):
        logger.info("Applying is_terminal method patch to TaskState class")
        TaskState.is_terminal = lambda self: is_terminal(self)
        return True
    elif not _AGENTVAULT_AVAILABLE:
        logger.warning("Cannot apply TaskState patch: agentvault.models not available")
        return False
    else:
        logger.debug("TaskState.is_terminal already exists, no patching needed")
        return True

# Apply the patch immediately when imported
patched = apply_taskstate_patch()
