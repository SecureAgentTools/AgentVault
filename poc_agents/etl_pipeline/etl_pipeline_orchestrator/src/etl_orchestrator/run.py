import asyncio
import logging
import uuid
import json
import sys
import os
import argparse
import datetime
from typing import Dict, Any, Optional
from pathlib import Path # CORRECTED: Added import

# Setup logger early
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try importing orchestrator components
try:
    logger.debug("Attempting imports for etl_orchestrator.run...")
    from etl_orchestrator.state_definition import EtlProcessingState
    from etl_orchestrator.graph import create_etl_graph
    from etl_orchestrator.config import settings, get_pipeline_config, EtlPipelineConfig, ConfigurationError
    from etl_orchestrator.a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
    logger.debug("Imports successful.")
except ImportError as e:
    logger.error(f"Failed to import orchestrator components: {e}. sys.path: {sys.path}.", exc_info=True)
    sys.exit(1)
except Exception as e:
     logger.error(f"An unexpected error occurred during imports: {e}", exc_info=True)
     sys.exit(1)

# --- Parse Args (REQ-ETL-ORCH-008) ---
def parse_args():
    """Parse command line arguments for the ETL pipeline."""
    parser = argparse.ArgumentParser(description='Run the Simple ETL Pipeline.')
    parser.add_argument(
        'source_identifier',
        type=str,
        help='Path or identifier for the source data (e.g., /data/input.csv inside container).'
    )
    parser.add_argument(
        '--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default=os.environ.get('LOG_LEVEL', 'INFO'), help='Logging level'
    )
    parser.add_argument(
        '--project-id', type=str, help='Optional custom project ID (default: auto-generated)'
    )
    parser.add_argument(
        '--config', type=str, help='Path to custom pipeline configuration JSON file.'
    )
    return parser.parse_args()

# --- Run Pipeline ---
async def run_pipeline(
    source_identifier: str,
    project_id: Optional[str] = None,
    config_path: Optional[str] = None
) -> Dict[str, Any]:
    """Runs the ETL pipeline."""
    logger.info(f"--- Starting ETL Pipeline Run for Source: '{source_identifier}' ---")

    try:
        pipeline_config = get_pipeline_config(config_path)
        logger.info(f"Loaded ETL pipeline configuration. Registry URL: {pipeline_config.orchestration.registry_url}")
    except (ConfigurationError, FileNotFoundError) as config_err:
        logger.critical(f"CRITICAL: Config error: {config_err}", exc_info=True)
        return {"error_message": f"Configuration error: {config_err}", "project_id": project_id, "source_identifier": source_identifier, "status": "FAILED"}
    except Exception as e:
         logger.critical(f"CRITICAL: Unexpected config error: {e}", exc_info=True)
         return {"error_message": f"Unexpected config error: {e}", "project_id": project_id, "source_identifier": source_identifier, "status": "FAILED"}

    if not project_id: project_id = f"etl-proj-{uuid.uuid4().hex[:8]}"

    a2a_wrapper_instance = None
    try:
        a2a_wrapper_instance = A2AClientWrapper(config=pipeline_config)
        await a2a_wrapper_instance.initialize()
        logger.info("A2A Client Wrapper initialized successfully (ETL agents discovered).")
    except ConfigurationError as e: logger.error(f"Config error initializing A2A Wrapper: {e}."); return {"error_message": f"A2A Config error: {e}", "project_id": project_id, "status": "FAILED"}
    except Exception as e: logger.exception("Failed to initialize A2A Wrapper."); return {"error_message": f"A2A Init failed: {e}", "project_id": project_id, "status": "FAILED"}

    try:
        app = create_etl_graph()
        logger.info("ETL pipeline graph compiled successfully.")
    except Exception as e:
        logger.exception("Failed to create/compile ETL graph.");
        if a2a_wrapper_instance: await a2a_wrapper_instance.close()
        return {"error_message": f"Graph compilation failed: {e}", "project_id": project_id, "status": "FAILED"}

    initial_state: EtlProcessingState = {
        "source_identifier": source_identifier,
        "pipeline_config": pipeline_config,
        "a2a_wrapper": a2a_wrapper_instance,
        "project_id": project_id,
        "current_step": None,
        "error_message": None,
        "db_artifact_references": {},
        "final_load_status": None,
    }
    logger.info(f"Initial input prepared for Project ID: {project_id}, Source: '{source_identifier}'")

    final_state_dict: Dict[str, Any] = {}
    try:
        logger.info("Invoking the ETL graph asynchronously...")
        recursion_limit = pipeline_config.orchestration.recursion_limit
        final_state_typed: EtlProcessingState = await app.ainvoke(initial_state, {"recursion_limit": recursion_limit})
        final_state_dict = dict(final_state_typed)
        logger.info("Graph invocation finished.")
    except Exception as e:
        logger.exception("Error during graph execution.")
        final_state_dict = dict(initial_state); final_state_dict["error_message"] = f"Graph execution error: {e}"; final_state_dict["status"] = "FAILED"
    finally:
        if a2a_wrapper_instance: await a2a_wrapper_instance.close(); logger.info("A2A Client Wrapper closed.")

    logger.info("--- ETL Pipeline Run Finished ---")
    if not final_state_dict: final_state_dict = {"error_message": "Graph execution failed unexpectedly.", "project_id": project_id, "status": "FAILED"}

    error = final_state_dict.get("error_message")
    final_load_status = final_state_dict.get("final_load_status")
    if error: logger.error(f"Pipeline failed: {error}"); final_state_dict["status"] = "FAILED"
    elif final_load_status != "Success": logger.warning(f"Pipeline completed but load status was: {final_load_status}"); final_state_dict["status"] = "COMPLETED_WITH_ISSUES"
    else: logger.info(f"Pipeline completed successfully for source '{source_identifier}'. Load Status: {final_load_status}"); final_state_dict["status"] = "COMPLETED"

    artifacts = final_state_dict.get("db_artifact_references", {})
    if artifacts:
        logger.info("Database artifact IDs generated:")
        for artifact_type, db_id in artifacts.items(): logger.info(f"  - {artifact_type}: ID={db_id}")

    if "pipeline_config" in final_state_dict: del final_state_dict["pipeline_config"]
    if "a2a_wrapper" in final_state_dict: del final_state_dict["a2a_wrapper"]

    return final_state_dict

# --- Main Execution ---
async def main():
    """Parse arguments and run the pipeline."""
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    logger.info(f"Log level set to: {args.log_level}")
    logger.info(f"Received Source Identifier: {args.source_identifier}")

    final_state = await run_pipeline(
        source_identifier=args.source_identifier,
        project_id=args.project_id,
        config_path=args.config
    )

    try: # Print final state as JSON
        # CORRECTED default_serializer function
        def default_serializer(obj):
            if isinstance(obj, datetime.datetime):
                return obj.isoformat()
            if hasattr(obj, 'model_dump') and callable(getattr(obj, 'model_dump')):
                try:
                    # Use try-except block on separate lines
                    return obj.model_dump(mode='json')
                except Exception:
                    pass # Fall through
            return str(obj) # Fallback

        print("\n--- FINAL STATE ---"); print(json.dumps(final_state, indent=2, default=default_serializer)); print("-------------------")
    except Exception as print_err: logger.error(f"Could not serialize final state: {print_err}"); print(final_state)

    if final_state.get("error_message"): sys.exit(1)

if __name__ == "__main__":
    # CORRECTED: Ensure Path is imported before use
    from pathlib import Path
    current_dir = Path(__file__).parent.resolve(); src_dir = current_dir.parent
    if str(src_dir) not in sys.path: sys.path.insert(0, str(src_dir)); logger.debug(f"Added {src_dir} to sys.path")
    asyncio.run(main())
