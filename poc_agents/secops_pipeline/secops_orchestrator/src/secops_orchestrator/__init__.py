# SecOps Pipeline Orchestrator Package
# REQ-SECOPS-ORCH-1.9
import logging

# Import the monkey-patching for TaskState
# This immediately patches the TaskState class with the is_terminal method
from .task_state_helpers import is_terminal

# Configure null handler to avoid "No handler found" warnings
# Applications using this package should configure their own logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
