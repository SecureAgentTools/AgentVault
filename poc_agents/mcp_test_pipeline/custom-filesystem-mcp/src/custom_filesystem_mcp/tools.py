import logging
from pathlib import Path
from typing import Dict, Any, List

# Import security helpers
from .security import secure_resolve_path, check_write_permission, SecurityError, ConfigurationError, ROOT_DATA_DIR

logger = logging.getLogger(__name__)

# --- MCP Response Formatting Helpers ---

def create_mcp_success_response(content_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Formats a standard MCP success result."""
    return {"content": content_list}

def create_mcp_tool_error_response(error_message: str) -> Dict[str, Any]:
    """Formats a standard MCP tool execution error result."""
    return {"isError": True, "content": [{"type": "text", "text": error_message}]}

# --- Tool Implementations ---

async def read_file(path: str) -> Dict[str, Any]:
    """Securely reads the content of a file relative to the data directory."""
    logger.info(f"Processing readFile request for path: '{path}'")
    
    # Special handling for paths starting with /data/
    if path.startswith('/data/'):
        logger.info(f"Special handling for /data/ path: '{path}'")
        # Try multiple path resolution strategies
        
        # 1. Try direct path (if /data/ is a real directory)
        direct_path = Path(path)
        logger.info(f"- Direct path: {direct_path}")
        if direct_path.exists() and direct_path.is_file():
            try:
                content = direct_path.read_text(encoding='utf-8')
                logger.info(f"Successfully read file using direct path: '{direct_path}'")
                return create_mcp_success_response([{"type": "text", "text": content}])
            except Exception as e:
                logger.warning(f"Direct path read failed: {e}")
        
        # 2. Try without /data/ prefix
        without_data_path = Path(path.replace('/data/', '/'))
        logger.info(f"- Without data path: {without_data_path}")
        if without_data_path.exists() and without_data_path.is_file():
            try:
                content = without_data_path.read_text(encoding='utf-8')
                logger.info(f"Successfully read file using without-data path: '{without_data_path}'")
                return create_mcp_success_response([{"type": "text", "text": content}])
            except Exception as e:
                logger.warning(f"Without-data path read failed: {e}")
        
        # 3. Try relative path (assuming /data/ is our ROOT_DATA_DIR)
        if ROOT_DATA_DIR is not None:
            relative_path = ROOT_DATA_DIR / path[6:]  # Remove '/data/' prefix
            logger.info(f"- Relative path: {relative_path}")
            if relative_path.exists() and relative_path.is_file():
                try:
                    content = relative_path.read_text(encoding='utf-8')
                    logger.info(f"Successfully read file using relative path: '{relative_path}'")
                    return create_mcp_success_response([{"type": "text", "text": content}])
                except Exception as e:
                    logger.warning(f"Relative path read failed: {e}")
        
        # All attempts failed, log and return error
        logger.info(f"Attempting to read file at resolved path: {path}")
        error_msg = f"File not found at any of the attempted locations: {path}"
        logger.error(error_msg)
        return create_mcp_tool_error_response(error_msg)
    
    # Regular path handling
    try:
        resolved_path = secure_resolve_path(path, check_existence=True)
        if not resolved_path.is_file():
            raise ValueError(f"Specified path is not a file: '{path}'")
        content = resolved_path.read_text(encoding='utf-8')
        logger.info(f"Successfully read file: '{resolved_path}'")
        return create_mcp_success_response([{"type": "text", "text": content}])
    except (SecurityError, FileNotFoundError, PermissionError, IsADirectoryError, ValueError, OSError) as e:
        user_facing_error = f"Could not read file '{path}'. Reason: {type(e).__name__}: {e}"
        # Refine common error messages
        if isinstance(e, SecurityError): user_facing_error = f"Access denied or invalid path for file '{path}'."
        elif isinstance(e, FileNotFoundError): user_facing_error = f"File not found: '{path}'."
        elif isinstance(e, PermissionError): user_facing_error = f"Permission denied for file: '{path}'."
        elif isinstance(e, IsADirectoryError): user_facing_error = f"Cannot read path, it is a directory: '{path}'."
        elif isinstance(e, ValueError) and "not a file" in str(e): user_facing_error = f"Cannot read path, it is not a file: '{path}'."

        logger.error(f"readFile failed for '{path}': {e}")
        return create_mcp_tool_error_response(user_facing_error)
    except Exception as e:
        logger.exception(f"readFile unexpected error for '{path}': {e}")
        return create_mcp_tool_error_response("An unexpected server error occurred while reading the file.")

async def write_file(path: str, content: str) -> Dict[str, Any]:
    """Securely writes content to a file relative to the data directory."""
    logger.info(f"Processing writeFile request for path: '{path}'")
    
    # Special handling for paths starting with /data/
    if path.startswith('/data/'):
        logger.info(f"Special handling for /data/ path: '{path}'")
        
        try:
            check_write_permission() # Check if server is read-only
            
            # 1. Try direct path (if /data/ is a real directory)
            direct_path = Path(path)
            direct_parent = direct_path.parent
            
            # Ensure parent directory exists
            try:
                direct_parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created parent directory for direct path: {direct_parent}")
            except Exception as mkdir_err:
                logger.warning(f"Failed to create parent directory for direct path: {mkdir_err}")
            
            # Try to write to direct path
            try:
                direct_path.write_text(content, encoding='utf-8')
                logger.info(f"Successfully wrote to direct path: '{direct_path}'")
                return create_mcp_success_response([{"type": "text", "text": f"Successfully wrote to '{path}'"}])
            except Exception as write_err:
                logger.warning(f"Direct path write failed: {write_err}")
            
            # 2. Try without /data/ prefix
            without_data_path = Path(path.replace('/data/', '/'))
            without_data_parent = without_data_path.parent
            
            # Ensure parent directory exists
            try:
                without_data_parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created parent directory for without-data path: {without_data_parent}")
            except Exception as mkdir_err:
                logger.warning(f"Failed to create parent directory for without-data path: {mkdir_err}")
            
            # Try to write to without-data path
            try:
                without_data_path.write_text(content, encoding='utf-8')
                logger.info(f"Successfully wrote to without-data path: '{without_data_path}'")
                return create_mcp_success_response([{"type": "text", "text": f"Successfully wrote to '{path}'"}])
            except Exception as write_err:
                logger.warning(f"Without-data path write failed: {write_err}")
            
            # 3. Try relative path (assuming /data/ is our ROOT_DATA_DIR)
            if ROOT_DATA_DIR is not None:
                relative_part = path[6:]  # Remove '/data/' prefix
                relative_path = ROOT_DATA_DIR / relative_part
                relative_parent = relative_path.parent
                
                # Ensure parent directory exists
                try:
                    relative_parent.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created parent directory for relative path: {relative_parent}")
                except Exception as mkdir_err:
                    logger.warning(f"Failed to create parent directory for relative path: {mkdir_err}")
                
                # Try to write to relative path
                try:
                    relative_path.write_text(content, encoding='utf-8')
                    logger.info(f"Successfully wrote to relative path: '{relative_path}'")
                    return create_mcp_success_response([{"type": "text", "text": f"Successfully wrote to '{path}'"}])
                except Exception as write_err:
                    logger.warning(f"Relative path write failed: {write_err}")
            
            # All attempts failed, log and return error
            error_msg = f"Could not write to any of the attempted locations: {path}"
            logger.error(error_msg)
            return create_mcp_tool_error_response(error_msg)
            
        except (SecurityError, PermissionError, IsADirectoryError) as e:
            user_facing_error = f"Could not write file '{path}'. Reason: {type(e).__name__}: {e}"
            logger.error(f"writeFile failed for '{path}': {e}")
            return create_mcp_tool_error_response(user_facing_error)
    
    # Regular path handling
    try:
        check_write_permission() # Check if server is read-only

        # Basic validation on the path string itself
        if not path or not isinstance(path, str): raise SecurityError("Invalid path input.")
        path_obj = Path(path.strip())
        if path_obj.is_absolute() or str(path_obj).startswith(('/', '\\', '..')): raise SecurityError("Invalid relative path format.")
        if not path_obj.name: raise SecurityError("Path must include a filename.")

        # Construct the full potential path *without resolving yet*
        if ROOT_DATA_DIR is None: raise ConfigurationError("Filesystem root not configured") # Should not happen
        target_path = ROOT_DATA_DIR / path_obj

        # Resolve the *parent* directory securely, ensuring it exists and is within root
        parent_dir_relative = str(path_obj.parent)
        parent_dir_relative = "." if parent_dir_relative == "." else parent_dir_relative # Handle root case
        resolved_parent_dir = secure_resolve_path(parent_dir_relative, check_existence=True)

        # Now form the final absolute path using the resolved parent
        resolved_target_path = resolved_parent_dir / path_obj.name

        # Final check: Ensure the final target path is still within the root
        if not resolved_target_path.is_relative_to(ROOT_DATA_DIR):
            logger.error(f"Write path escaped root after parent resolution: Input='{path}', Target='{resolved_target_path}'")
            raise SecurityError("Path construction resulted in escaping the root directory.")

        # Prevent writing *to* a directory
        if resolved_target_path.is_dir():
            raise IsADirectoryError(f"Cannot write file, path exists and is a directory: '{path}'")

        # Write the content
        resolved_target_path.write_text(content, encoding='utf-8')
        logger.info(f"Successfully wrote to file: '{resolved_target_path}'")
        return create_mcp_success_response([{"type": "text", "text": f"Successfully wrote to '{path}'"}])

    except (SecurityError, FileNotFoundError, PermissionError, IsADirectoryError, NotADirectoryError, OSError) as e:
        user_facing_error = f"Could not write file '{path}'. Reason: {type(e).__name__}: {e}"
        # Refine common error messages
        if isinstance(e, SecurityError): user_facing_error = f"Access denied or invalid path for file '{path}'."
        elif isinstance(e, FileNotFoundError): user_facing_error = f"Cannot write file, parent directory not found: '{path}'."
        elif isinstance(e, PermissionError): user_facing_error = f"Permission denied for file: '{path}'."
        elif isinstance(e, IsADirectoryError): user_facing_error = f"Cannot write file, path exists and is a directory: '{path}'."
        elif isinstance(e, NotADirectoryError): user_facing_error = f"Cannot write file, parent path is not a directory: '{path}'."

        logger.error(f"writeFile failed for '{path}': {e}")
        return create_mcp_tool_error_response(user_facing_error)
    except Exception as e:
        logger.exception(f"writeFile unexpected error for '{path}': {e}")
        return create_mcp_tool_error_response("An unexpected server error occurred while writing the file.")

async def list_directory(path: str) -> Dict[str, Any]:
    """Securely lists the contents of a directory relative to the data directory."""
    logger.info(f"Processing listDirectory request for path: '{path}'")
    
    # Special handling for paths starting with /data/
    if path and path.strip() and path.startswith('/data/'):
        logger.info(f"Special handling for /data/ path: '{path}'")
        
        # 1. Try direct path (if /data/ is a real directory)
        direct_path = Path(path)
        logger.info(f"- Direct path: {direct_path}")
        if direct_path.exists() and direct_path.is_dir():
            try:
                items_list: List[str] = []
                for item in direct_path.iterdir():
                    try:
                        item_type = "[DIR]" if item.is_dir() else "[FILE]"
                        items_list.append(f"{item_type} {item.name}")
                    except OSError as item_e:
                        logger.warning(f"Could not stat item '{item.name}' in directory '{direct_path}': {item_e}")
                        items_list.append(f"[UNKNOWN] {item.name}")

                logger.info(f"Successfully listed directory using direct path: '{direct_path}'")
                list_text = "\n".join(items_list) if items_list else f"Directory '{path}' is empty."
                return create_mcp_success_response([{"type": "text", "text": list_text}])
            except Exception as e:
                logger.warning(f"Direct path listing failed: {e}")
        
        # 2. Try without /data/ prefix
        without_data_path = Path(path.replace('/data/', '/'))
        logger.info(f"- Without data path: {without_data_path}")
        if without_data_path.exists() and without_data_path.is_dir():
            try:
                items_list: List[str] = []
                for item in without_data_path.iterdir():
                    try:
                        item_type = "[DIR]" if item.is_dir() else "[FILE]"
                        items_list.append(f"{item_type} {item.name}")
                    except OSError as item_e:
                        logger.warning(f"Could not stat item '{item.name}' in directory '{without_data_path}': {item_e}")
                        items_list.append(f"[UNKNOWN] {item.name}")

                logger.info(f"Successfully listed directory using without-data path: '{without_data_path}'")
                list_text = "\n".join(items_list) if items_list else f"Directory '{path}' is empty."
                return create_mcp_success_response([{"type": "text", "text": list_text}])
            except Exception as e:
                logger.warning(f"Without-data path listing failed: {e}")
        
        # 3. Try relative path (assuming /data/ is our ROOT_DATA_DIR)
        if ROOT_DATA_DIR is not None:
            relative_part = path[6:]  # Remove '/data/' prefix
            relative_path = ROOT_DATA_DIR / relative_part
            logger.info(f"- Relative path: {relative_path}")
            if relative_path.exists() and relative_path.is_dir():
                try:
                    items_list: List[str] = []
                    for item in relative_path.iterdir():
                        try:
                            item_type = "[DIR]" if item.is_dir() else "[FILE]"
                            items_list.append(f"{item_type} {item.name}")
                        except OSError as item_e:
                            logger.warning(f"Could not stat item '{item.name}' in directory '{relative_path}': {item_e}")
                            items_list.append(f"[UNKNOWN] {item.name}")

                    logger.info(f"Successfully listed directory using relative path: '{relative_path}'")
                    list_text = "\n".join(items_list) if items_list else f"Directory '{path}' is empty."
                    return create_mcp_success_response([{"type": "text", "text": list_text}])
                except Exception as e:
                    logger.warning(f"Relative path listing failed: {e}")
        
        # All attempts failed, log and return error
        error_msg = f"Directory not found at any of the attempted locations: {path}"
        logger.error(error_msg)
        return create_mcp_tool_error_response(error_msg)
    
    # Regular path handling
    try:
        # Handle special case for listing the root directory itself
        if path is None or path.strip() in [".", ""]:
            if ROOT_DATA_DIR is None: raise ConfigurationError("Filesystem root not configured")
            resolved_path = ROOT_DATA_DIR
            input_path_display = "."
        else:
            resolved_path = secure_resolve_path(path, check_existence=True)
            input_path_display = path

        # Ensure it's a directory
        if not resolved_path.is_dir():
            raise NotADirectoryError(f"Specified path is not a directory: '{input_path_display}'")

        items_list: List[str] = []
        for item in resolved_path.iterdir():
            try:
                item_type = "[DIR]" if item.is_dir() else "[FILE]"
                items_list.append(f"{item_type} {item.name}")
            except OSError as item_e:
                logger.warning(f"Could not stat item '{item.name}' in directory '{resolved_path}': {item_e}")
                items_list.append(f"[UNKNOWN] {item.name}")

        logger.info(f"Successfully listed directory: '{resolved_path}'")
        list_text = "\n".join(items_list) if items_list else f"Directory '{input_path_display}' is empty."
        return create_mcp_success_response([{"type": "text", "text": list_text}])

    except (SecurityError, FileNotFoundError, PermissionError, NotADirectoryError, OSError) as e:
        input_path_display = path if path is not None and path.strip() not in [".", ""] else "."
        user_facing_error = f"Could not list directory '{input_path_display}'. Reason: {type(e).__name__}: {e}"
        # Refine common error messages
        if isinstance(e, SecurityError): user_facing_error = f"Access denied or invalid path for directory '{input_path_display}'."
        elif isinstance(e, FileNotFoundError): user_facing_error = f"Directory not found: '{input_path_display}'."
        elif isinstance(e, PermissionError): user_facing_error = f"Permission denied for directory: '{input_path_display}'."
        elif isinstance(e, NotADirectoryError): user_facing_error = f"Cannot list path, it is not a directory: '{input_path_display}'."

        logger.error(f"listDirectory failed for '{input_path_display}': {e}")
        return create_mcp_tool_error_response(user_facing_error)
    except Exception as e:
        input_path_display = path if path is not None and path.strip() not in [".", ""] else "."
        logger.exception(f"listDirectory unexpected error for '{input_path_display}': {e}")
        return create_mcp_tool_error_response("An unexpected server error occurred while listing the directory.")
