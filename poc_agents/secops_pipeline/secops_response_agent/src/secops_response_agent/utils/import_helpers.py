"""
Helper module to ensure proper imports for shared modules.
"""
import sys
import os
import logging

logger = logging.getLogger(__name__)

def ensure_shared_imports():
    """
    Ensures the shared modules directory is in the sys.path so imports will work correctly.
    """
    # Try different potential shared directory paths
    potential_paths = [
        "/app/shared",                                    # Docker container path
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared"),  # Development relative path
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "shared"))  # Absolute path
    ]
    
    for path in potential_paths:
        if os.path.exists(path) and path not in sys.path:
            logger.info(f"Adding shared module path to sys.path: {path}")
            sys.path.insert(0, path)
            return True
    
    logger.warning("Could not find shared module directory. Imports may fail.")
    return False

# Special import handling for task_state_helpers.py
def get_task_state_helpers():
    """
    Imports and returns the task_state_helpers module, falling back to a placeholder if needed.
    """
    ensure_shared_imports()
    
    try:
        # Try to import from the shared directory
        import task_state_helpers
        logger.info("Successfully imported task_state_helpers from shared path")
        return task_state_helpers
    except ImportError as e:
        logger.warning(f"Failed to import task_state_helpers: {e}")
        
        # Create placeholder functionality
        class TaskStatePlaceholder:
            """Placeholder for TaskState functionality if actual module cannot be imported."""
            @staticmethod
            def is_terminal(state):
                """Check if a state is terminal."""
                terminal_states = {"COMPLETED", "FAILED", "CANCELED"}
                return str(state) in terminal_states
                
            @staticmethod
            def apply_taskstate_patch():
                """Placeholder for patch application."""
                logger.warning("Using placeholder for apply_taskstate_patch")
                return False
                
        logger.warning("Using TaskStatePlaceholder instead of task_state_helpers")
        return TaskStatePlaceholder()

# Special import handling for registry_helpers.py
def get_registry_helpers():
    """
    Imports and returns the registry_helpers module, falling back to a placeholder if needed.
    """
    ensure_shared_imports()
    
    try:
        # Try to import from the shared directory
        from shared import registry_helpers
        logger.info("Successfully imported registry_helpers from shared path")
        return registry_helpers
    except ImportError as e:
        logger.warning(f"Failed to import registry_helpers: {e}")
        
        # Create placeholder functionality for load_agent_card
        async def load_agent_card(agent_ref, registry_url):
            logger.warning("Using placeholder load_agent_card function - card loading will fail")
            return None
        
        # Create a placeholder module-like object with the function
        class RegistryHelpersPlaceholder:
            """Placeholder for registry_helpers module if actual module cannot be imported."""
            load_agent_card = load_agent_card
        
        logger.warning("Using RegistryHelpersPlaceholder instead of registry_helpers")
        return RegistryHelpersPlaceholder()
