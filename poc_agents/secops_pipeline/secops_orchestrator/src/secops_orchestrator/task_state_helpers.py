"""
Helper functions for working with TaskState objects
"""

# Import definitions with fallback as in the client wrapper
try:
    from agentvault.models import TaskState
    _AGENTVAULT_AVAILABLE = True
except ImportError:
    class TaskState:
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"
        CANCELED = "CANCELED"
        UNKNOWN = "UNKNOWN"
        WORKING = "WORKING"
        SUBMITTED = "SUBMITTED"
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
if _AGENTVAULT_AVAILABLE and not hasattr(TaskState, 'is_terminal'):
    TaskState.is_terminal = lambda self: is_terminal(self)
