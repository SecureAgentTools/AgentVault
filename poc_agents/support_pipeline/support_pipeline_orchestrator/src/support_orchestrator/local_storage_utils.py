# Adapted local_storage_utils from e-commerce example for the Support Pipeline
# REQ-SUP-ORCH-006

import logging
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)

# Define the base directory for storing artifacts relative to this project
# Assuming this file is in src/support_orchestrator/
UTILS_FILE_PATH = Path(__file__).resolve()
ORCHESTRATOR_ROOT_DIR = UTILS_FILE_PATH.parent.parent.parent # Go up 3 levels: config -> src -> orchestrator root
# Default path from REQ-SUP-ORCH-002
DEFAULT_ARTIFACT_STORAGE_DIR = Path("/app/pipeline_artifacts/support")

# Ensure the base directory exists
try:
    DEFAULT_ARTIFACT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Ensured local artifact storage directory exists: {DEFAULT_ARTIFACT_STORAGE_DIR}")
except OSError as e:
    logger.error(f"Failed to create artifact storage directory at {DEFAULT_ARTIFACT_STORAGE_DIR}: {e}", exc_info=True)

# --- Helper Functions ---

async def save_local_artifact(
    data: Union[Dict[str, Any], List[Any], str],
    project_id: str,
    step_name: str,
    artifact_name: str, # e.g., 'ticket_analysis.json', 'suggested_response.txt'
    is_json: bool = True,
    base_path: Optional[str] = None # Path from SupportPipelineConfig.orchestration.artifact_base_path
) -> Optional[str]:
    """
    Saves Python dictionary/list (as JSON) or string data to the local filesystem
    for the support pipeline.

    Args:
        data: The dictionary, list, or string to save.
        project_id: The unique ID for the current pipeline run.
        step_name: The name of the pipeline step generating the artifact.
        artifact_name: The name of the artifact file.
        is_json: If True, serialize dict/list to JSON. If False, save data as raw string.
        base_path: Optional override for the base path (from configuration).

    Returns:
        The absolute file path (as a string) if successful, None otherwise.
    """
    if base_path:
        try:
            base_dir = Path(base_path)
            base_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Using configured base path: {base_dir}")
        except Exception as e:
            logger.warning(f"Failed to use configured base path '{base_path}': {e}. Falling back to default.")
            base_dir = DEFAULT_ARTIFACT_STORAGE_DIR
    else:
        base_dir = DEFAULT_ARTIFACT_STORAGE_DIR

    # Handle None data - create placeholders specific to support pipeline artifacts
    if data is None:
        logger.warning(f"Attempted to save None data for artifact '{artifact_name}' in step '{step_name}'. Creating empty placeholder.")
        if is_json:
            if "analysis" in artifact_name: data = {"ticket_analysis": {}}
            elif "kb_results" in artifact_name: data = {"kb_results": []}
            elif "history" in artifact_name: data = {"customer_history": {}}
            else: data = {} # Generic fallback
        else:
            if "response" in artifact_name: data = "# Placeholder for suggested response\n\nNo content was available.\n"
            else: data = f"# Placeholder for {artifact_name}\n\nNo content was available.\n"


    try:
        artifact_dir = base_dir / project_id / step_name
        artifact_dir.mkdir(parents=True, exist_ok=True)
        file_path = artifact_dir / artifact_name

        logger.info(f"Saving artifact to local path: {file_path}...")
        logger.debug(f"Artifact data type: {type(data)}")
        if isinstance(data, dict): logger.debug(f"Artifact keys: {list(data.keys())}")

        with open(file_path, 'w', encoding='utf-8') as f:
            if is_json:
                try:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                except TypeError as e:
                    logger.error(f"Failed to serialize data to JSON for local save ({file_path}): {e}", exc_info=True)
                    try:
                        # Attempt fallback serialization converting non-serializable types to string
                        sanitized_data = json.loads(json.dumps(data, default=str))
                        json.dump(sanitized_data, f, indent=2, ensure_ascii=False)
                        logger.info(f"Saved sanitized JSON data to {file_path}")
                        return str(file_path.resolve())
                    except Exception as e2:
                        logger.error(f"Failed to save sanitized data for {file_path}: {e2}", exc_info=True)
                        return None
            else:
                if not isinstance(data, str):
                    logger.warning(f"Data for non-JSON save is not string ({type(data)}), converting.")
                    data = str(data)
                f.write(data)

        logger.info(f"Successfully saved artifact to {file_path}")
        return str(file_path.resolve())
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
    (Identical logic to e-commerce example).
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
                return None
        else:
            return content_str
    except IOError as e:
        logger.error(f"IOError loading artifact from {file_path}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"Unexpected error loading artifact from {file_path}: {e}")
        return None

def get_default_artifacts_dir() -> Path:
    """Returns the default artifacts directory path for the support pipeline."""
    return DEFAULT_ARTIFACT_STORAGE_DIR

logger.info("Local Storage Utilities initialized for support pipeline.")
