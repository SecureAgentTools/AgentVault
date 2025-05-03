import logging
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)

# Define the base directory for storing artifacts relative to this project
# Assuming this file is in src/langgraph_research_orchestrator/
UTILS_FILE_PATH = Path(__file__).resolve()
ORCHESTRATOR_ROOT_DIR = UTILS_FILE_PATH.parent.parent.parent # Go up 3 levels
DEFAULT_ARTIFACT_STORAGE_DIR = ORCHESTRATOR_ROOT_DIR / "pipeline_artifacts"

# Ensure the base directory exists
try:
    DEFAULT_ARTIFACT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Ensured local artifact storage directory exists: {DEFAULT_ARTIFACT_STORAGE_DIR}")
except OSError as e:
    logger.error(f"Failed to create artifact storage directory at {DEFAULT_ARTIFACT_STORAGE_DIR}: {e}", exc_info=True)
    # Depending on requirements, could raise an error here or try to continue

# --- Helper Functions ---

async def save_local_artifact(
    data: Union[Dict[str, Any], List[Any], str],
    project_id: str,
    step_name: str,
    artifact_name: str,
    is_json: bool = True,
    base_path: Optional[str] = None
) -> Optional[str]:
    """
    Saves Python dictionary/list (as JSON) or string data to the local filesystem.

    Args:
        data: The dictionary, list, or string to save.
        project_id: The unique ID for the current pipeline run.
        step_name: The name of the pipeline step generating the artifact.
        artifact_name: The name of the artifact (e.g., 'raw_content.json', 'draft_article.md').
        is_json: If True, serialize dict/list to JSON before saving. If False, save data as raw string.
        base_path: Optional override for the base path (from configuration)

    Returns:
        The absolute file path (as a string) if successful, None otherwise.
    """
    # Determine the base directory to use
    if base_path:
        try:
            base_dir = Path(base_path)
            # Ensure the directory exists
            base_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Using configured base path: {base_dir}")
        except Exception as e:
            logger.warning(f"Failed to use configured base path '{base_path}': {e}. Falling back to default.")
            base_dir = DEFAULT_ARTIFACT_STORAGE_DIR
    else:
        base_dir = DEFAULT_ARTIFACT_STORAGE_DIR
    
    if data is None:
        logger.warning(f"Attempted to save None data for artifact '{artifact_name}' in step '{step_name}'. Creating empty placeholder.")
        # Create appropriate empty placeholders
        if is_json:
            if artifact_name.endswith(".json"):
                # Create appropriate empty structures based on artifact name
                if "bibliography" in artifact_name:
                    data = {"sources": []}
                elif "verified_facts" in artifact_name:
                    data = {"verified_facts": []}
                elif "extracted_information" in artifact_name:
                    data = {"extracted_facts": []}
                elif "viz_metadata" in artifact_name:
                    data = {"visualizations": []}
                else:
                    # Default empty structure
                    data = {}
            else:
                data = {}
        else:
            # For non-JSON (like markdown), provide minimal content
            data = f"# Placeholder for {artifact_name}\n\nNo content was available.\n"

    try:
        # Construct path: base_dir / project_id / step_name / artifact_name
        artifact_dir = base_dir / project_id / step_name
        artifact_dir.mkdir(parents=True, exist_ok=True) # Ensure subdirectory exists
        file_path = artifact_dir / artifact_name

        logger.info(f"Saving artifact to local path: {file_path}...")

        with open(file_path, 'w', encoding='utf-8') as f:
            if is_json:
                try:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                except TypeError as e:
                    logger.error(f"Failed to serialize data to JSON for local save ({file_path}): {e}", exc_info=True)
                    # Attempt to save a sanitized version
                    logger.warning(f"Attempting to save sanitized version of the data")
                    try:
                        # Try to convert to simple dict/list with basic types
                        if isinstance(data, dict):
                            sanitized_data = {}
                            for k, v in data.items():
                                if isinstance(k, (str, int, float, bool)) or k is None:
                                    if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                                        sanitized_data[str(k)] = v
                            json.dump(sanitized_data, f, indent=2, ensure_ascii=False)
                            logger.info(f"Saved sanitized dictionary with {len(sanitized_data)} keys")
                        elif isinstance(data, list):
                            sanitized_data = []
                            for item in data:
                                if isinstance(item, (str, int, float, bool, list, dict)) or item is None:
                                    sanitized_data.append(item)
                            json.dump(sanitized_data, f, indent=2, ensure_ascii=False)
                            logger.info(f"Saved sanitized list with {len(sanitized_data)} items")
                        else:
                            # Last resort - save string representation
                            f.write("{\"\_\_string_representation\":\"" + str(data).replace("\"", "\\\"") + "\"}")
                            logger.info("Saved string representation of unserializable data")
                        return str(file_path.resolve())
                    except Exception as e2:
                        logger.error(f"Failed to save sanitized data for {file_path}: {e2}", exc_info=True)
                        return None
            else:
                if not isinstance(data, str):
                    logger.error(f"Data must be a string when is_json=False for local save ({file_path}). Got {type(data)}.")
                    # Convert to string as a fallback
                    data = str(data)
                f.write(data)

        logger.info(f"Successfully saved artifact to {file_path}")
        return str(file_path.resolve()) # Return the absolute path as a string
    except IOError as e:
        logger.error(f"IOError saving artifact to {artifact_name} in {step_name}/{project_id}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"Unexpected error saving artifact to {artifact_name} in {step_name}/{project_id}: {e}")
        return None

async def load_local_artifact(
    file_path_str: str,
    is_json: bool = True
) -> Optional[Union[Dict[str, Any], List[Any], str]]:
    """
    Loads data (JSON object/list or raw string) from the local filesystem.

    Args:
        file_path_str: The absolute path to the artifact file.
        is_json: If True, attempt to parse the file content as JSON.
                 If False, return the raw string content.

    Returns:
        The loaded data (dict, list, or str) or None if loading/parsing fails.
    """
    if not file_path_str:
        logger.error("Load local artifact failed: file_path_str is empty.")
        return None

    file_path = Path(file_path_str)
    logger.info(f"Loading artifact from local path: {file_path}...")

    if not file_path.is_file():
        logger.error(f"Local artifact file not found: {file_path}")
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content_str = f.read()

        logger.info(f"Successfully read {len(content_str)} characters from {file_path}")

        if is_json:
            try:
                data = json.loads(content_str)
                logger.debug(f"Successfully parsed JSON data from {file_path}")
                return data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse content as JSON from {file_path}: {e}", exc_info=True)
                logger.debug(f"Content snippet: {content_str[:200]}...")
                return None
        else:
            # Return raw string
            return content_str

    except IOError as e:
        logger.error(f"IOError loading artifact from {file_path}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"Unexpected error loading artifact from {file_path}: {e}")
        return None

def get_default_artifacts_dir() -> Path:
    """
    Returns the default artifacts directory path.
    This can be useful for other modules that need to know where artifacts are stored.
    """
    return DEFAULT_ARTIFACT_STORAGE_DIR

logger.info("Local Storage Utilities initialized.")
