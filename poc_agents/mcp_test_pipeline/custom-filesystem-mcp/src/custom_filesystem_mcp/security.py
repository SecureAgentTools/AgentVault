import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# --- Root Directory Setup ---
# Get path from environment variable, default to /data for Docker convention
# This should run once at module load time.
try:
    data_dir_env = os.environ.get("MCP_DATA_DIR", "/data")
    
    # Check for explicit data dir existence, but allow failure for containers
    # where the directory might be mounted later
    data_dir_path = Path(data_dir_env)
    if data_dir_path.exists() and data_dir_path.is_dir():
        ROOT_DATA_DIR = data_dir_path.resolve()
        logger.info(f"MCP Filesystem Server Root Directory exists and is configured: {ROOT_DATA_DIR}")
    else:
        # Directory doesn't exist yet, but we'll still use the path for Docker environments
        # where volumes might be mounted at runtime
        ROOT_DATA_DIR = data_dir_path
        logger.warning(f"MCP_DATA_DIR does not exist yet or is not accessible: {data_dir_env}. Setting anyway for container environments.")
        
        # Create the directory if possible (helpful for testing)
        try:
            ROOT_DATA_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created root data directory: {ROOT_DATA_DIR}")
        except Exception as mkdir_err:
            logger.warning(f"Could not create root data directory: {mkdir_err}")

except Exception as e:
    logger.critical(f"CRITICAL ERROR: Unexpected error setting up MCP_DATA_DIR ('{data_dir_env}'): {e}")
    # Still set the default even if there was an error, for container environments
    ROOT_DATA_DIR = Path("/data")
    logger.warning(f"Falling back to default data directory: {ROOT_DATA_DIR}")
    
# Also set up a special flag to indicate if we should handle /data/ paths specially
# This helps with compatibility where paths might be referenced as /data/ in some contexts
SPECIAL_DATA_PATH_HANDLING = os.environ.get("MCP_SPECIAL_DATA_HANDLING", "true").lower() == "true"
logger.info(f"Special /data/ path handling enabled: {SPECIAL_DATA_PATH_HANDLING}")

# --- Security Exception ---
class SecurityError(ValueError):
    """Custom exception for path traversal or unsafe path attempts."""
    pass

class ConfigurationError(Exception):
    """Custom exception for configuration issues."""
    pass

# --- Secure Path Resolution Function ---
def secure_resolve_path(path: str, check_existence: bool = True) -> Path:
    """
    Resolves a path securely, preventing traversal, with special handling for /data/ paths.

    Args:
        path: The path string received from the client.
        check_existence: If True (default), requires the final path to exist.
                         Set to False for operations like writeFile where the
                         target may not exist yet, but its parent must.

    Returns:
        A resolved, validated Path object confirmed to be within ROOT_DATA_DIR.

    Raises:
        SecurityError: If the path is invalid, attempts traversal, or fails resolution.
        FileNotFoundError: If check_existence is True and the path does not exist.
        ConfigurationError: If ROOT_DATA_DIR was not configured properly.
    """
    # Early validation
    if not path or not isinstance(path, str):
        raise SecurityError("Invalid path input: must be a non-empty string.")

    # Clean the input path string slightly (e.g., strip whitespace)
    path = path.strip()
    if not path:
         raise SecurityError("Invalid path input: path is empty after stripping whitespace.")
         
    # Special handling for /data/ paths if enabled
    if SPECIAL_DATA_PATH_HANDLING and path.startswith('/data/'):
        logger.info(f"Special /data/ path handling for: '{path}'")
        
        # 1. Try direct path if it exists (for Docker environments where /data is mounted)
        direct_path = Path(path)
        if direct_path.exists():
            logger.info(f"Direct /data/ path exists and will be used: {direct_path}")
            return direct_path
            
        # 2. Try path relative to ROOT_DATA_DIR by stripping /data/ prefix
        relative_part = path[6:]  # Remove '/data/' prefix
        alt_path = ROOT_DATA_DIR / relative_part
        
        if alt_path.exists() or not check_existence:
            logger.info(f"Using modified path mapped to ROOT_DATA_DIR: {alt_path}")
            return alt_path
            
        # If we need existence but neither option worked, provide helpful error
        if check_existence:
            logger.warning(f"Could not resolve /data/ path: '{path}'. Tried: {direct_path}, {alt_path}")
            raise FileNotFoundError(f"Could not find file at any attempted location for: '{path}'")
            
        # As a last resort, return the ROOT_DATA_DIR-relative path even if it doesn't exist
        return alt_path
    
    # For absolute paths without /data/ prefix, verify they're allowed
    if Path(path).is_absolute():
        abs_path = Path(path)
        # If the absolute path exists and is within ROOT_DATA_DIR, allow it
        if abs_path.exists() and abs_path.is_relative_to(ROOT_DATA_DIR):
            logger.info(f"Permitting existing absolute path within ROOT_DATA_DIR: {abs_path}")
            return abs_path
        # Otherwise, reject absolute paths unless specifically allowed
        raise SecurityError(f"Absolute paths not allowed unless within ROOT_DATA_DIR: '{path}'")
    
    # Regular path handling - treat as relative to ROOT_DATA_DIR
    try:
        # Combine with ROOT_DATA_DIR for relative paths
        combined_path = ROOT_DATA_DIR / path

        # Resolve with appropriate strict mode based on caller's needs
        resolved_path = combined_path.resolve(strict=check_existence)

        # THE CRITICAL CHECK: Verify the resolved path is inside the root directory
        if not resolved_path.is_relative_to(ROOT_DATA_DIR):
            logger.warning(f"Path traversal attempt blocked: Input='{path}', Resolved='{resolved_path}'")
            raise SecurityError(f"Path traversal attempt detected for: '{path}'")

        return resolved_path

    except FileNotFoundError as e:
         # Only raise if existence was required
         if check_existence:
             logger.warning(f"Path not found during secure resolution (check_existence=True): '{path}' -> {e}")
             raise FileNotFoundError(f"Path component not found or invalid: '{path}'") from e
         else:
             # If check_existence is False, FileNotFoundError during resolve likely means
             # an intermediate directory is missing. Treat as security error for write operations.
             logger.warning(f"Intermediate path component not found for write target: '{path}' -> {e}")
             raise SecurityError(f"Cannot write to path, intermediate directory missing: '{path}'") from e
    except OSError as e:
        # Catch potential OS errors during resolution (e.g., path too long, invalid chars)
        logger.error(f"OS error during path resolution for '{path}': {e}")
        raise SecurityError(f"Path resolution failed due to OS error: '{path}'") from e
    except Exception as e:
        # Catch any other unexpected errors during resolution
        logger.error(f"Unexpected error resolving path '{path}': {e}", exc_info=True)
        raise SecurityError(f"Unexpected error processing path: '{path}'") from e

# --- Read-Only Check ---
def check_write_permission():
     """Raises PermissionError if server is configured as read-only."""
     read_only_env = os.environ.get("MCP_FS_READ_ONLY", "false").lower()
     if read_only_env == "true":
          logger.warning("Write operation blocked: Server is in read-only mode.")
          raise PermissionError("Write operations are disabled on this server.")
