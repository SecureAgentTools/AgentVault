import asyncio
import logging
import uuid
import json
import sys
import os
import argparse
import datetime
from typing import Dict, Any, Optional
from pathlib import Path

# Setup logger early
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try importing orchestrator components
try:
    logger.debug("Attempting imports for mcp_test_orchestrator.run...")
    from .state_definition import McpTestState
    from .graph import create_mcp_test_graph
    from .config import settings, get_pipeline_config, McpTestPipelineConfig, ConfigurationError
    # Use our local A2AClientWrapper
    from .a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
    logger.debug("Imports successful.")
except ImportError as e:
    logger.error(f"Failed to import orchestrator components: {e}. sys.path: {sys.path}.", exc_info=True)
    sys.exit(1)
except Exception as e:
     logger.error(f"An unexpected error occurred during imports: {e}", exc_info=True)
     sys.exit(1)

# --- Parse Args ---
def parse_args():
    """Parse command line arguments for the MCP Test pipeline."""
    parser = argparse.ArgumentParser(description='Run the MCP Test Pipeline.')
    parser.add_argument('--file', type=str, help='Path to the Python script file within the shared volume (e.g., /data/script.py).')
    parser.add_argument('--code', type=str, help='Direct Python code string to execute.')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default=os.environ.get('LOG_LEVEL', 'INFO'), help='Logging level')
    parser.add_argument('--project-id', type=str, help='Optional custom project ID')
    parser.add_argument('--config', type=str, help='Path to custom pipeline configuration JSON file.')

    # Add validation: Must provide --file or --code
    args = parser.parse_args()
    if not args.file and not args.code:
        parser.error("Either --file or --code must be provided.")
    if args.file and args.code:
        parser.error("Provide either --file or --code, not both.")
    # --- CORRECTED LINE ---
    return args # Return the parsed args object directly
    # --- END CORRECTION ---

# --- Run Pipeline ---
async def run_pipeline(
    input_file_path: Optional[str] = None,
    input_python_code: Optional[str] = None,
    project_id: Optional[str] = None,
    config_path: Optional[str] = None
) -> Dict[str, Any]:
    """Runs the MCP Test pipeline."""
    logger.info(f"--- Starting MCP Test Pipeline Run ---")
    if input_file_path: logger.info(f"Input File: '{input_file_path}'")
    if input_python_code: logger.info(f"Input Code Provided (length: {len(input_python_code)})")

    try:
        pipeline_config = get_pipeline_config(config_path)
        logger.info(f"Loaded MCP Test config. Registry: {pipeline_config.orchestration.registry_url}")
    except (ConfigurationError, FileNotFoundError) as config_err:
        logger.critical(f"CRITICAL Config error: {config_err}", exc_info=True)
        return {"error_message": f"Configuration error: {config_err}", "project_id": project_id, "status": "FAILED"}
    except Exception as e:
         logger.critical(f"CRITICAL: Unexpected config error: {e}", exc_info=True)
         return {"error_message": f"Unexpected config error: {e}", "project_id": project_id, "status": "FAILED"}

    if not project_id: project_id = f"mcp-test-{uuid.uuid4().hex[:8]}"

    a2a_wrapper_instance = None
    try:
        # Reuse the A2AClientWrapper, configured via McpTestPipelineConfig
        a2a_wrapper_instance = A2AClientWrapper(config=pipeline_config) # type: ignore
        await a2a_wrapper_instance.initialize()
        logger.info("A2A Wrapper initialized (MCP proxy agent discovered).")
    except Exception as e:
        logger.exception("Failed to initialize A2A Wrapper."); return {"error_message": f"A2A Init failed: {e}", "project_id": project_id, "status": "FAILED"}

    try:
        app = create_mcp_test_graph()
        logger.info("MCP Test pipeline graph compiled.")
    except Exception as e:
        logger.exception("Failed to create/compile MCP Test graph.");
        if a2a_wrapper_instance: await a2a_wrapper_instance.close()
        return {"error_message": f"Graph compilation failed: {e}", "project_id": project_id, "status": "FAILED"}

    initial_state: McpTestState = {
        "pipeline_config": pipeline_config,
        "a2a_wrapper": a2a_wrapper_instance,
        "project_id": project_id,
        "input_file_path": input_file_path,
        "input_python_code": input_python_code,
        "current_step": None, "error_message": None,
        "read_file_content": None,
        "code_execution_output": None,
        "write_file_result": None,
    }
    logger.info(f"Initial state prepared for Project ID: {project_id}")

    final_state_dict: Dict[str, Any] = {}
    try:
        logger.info("Invoking MCP Test graph asynchronously...")
        recursion_limit = pipeline_config.orchestration.recursion_limit
        final_state_typed: McpTestState = await app.ainvoke(initial_state, {"recursion_limit": recursion_limit})
        final_state_dict = dict(final_state_typed)
        logger.info("Graph invocation finished.")
    except Exception as e:
        logger.exception("Error during graph execution.")
        final_state_dict = dict(initial_state); final_state_dict["error_message"] = f"Graph execution error: {e}"; final_state_dict["status"] = "FAILED"
    finally:
        if a2a_wrapper_instance: await a2a_wrapper_instance.close(); logger.info("A2A Client Wrapper closed.")

    logger.info("--- MCP Test Pipeline Run Finished ---")
    if not final_state_dict: final_state_dict = {"error_message": "Graph execution failed unexpectedly.", "project_id": project_id, "status": "FAILED"}

    error = final_state_dict.get("error_message")
    if error: logger.error(f"Pipeline failed: {error}"); final_state_dict["status"] = "FAILED"
    else: logger.info(f"Pipeline completed successfully for project '{project_id}'"); final_state_dict["status"] = "COMPLETED"

    # Log key results
    if final_state_dict.get("code_execution_output"):
        logger.info("--- Code Execution Output ---")
        # Access attributes directly since it's a Pydantic model
        output = final_state_dict['code_execution_output']
        stdout = output.stdout if hasattr(output, 'stdout') else ''
        stderr = output.stderr if hasattr(output, 'stderr') else ''
        logger.info(f"STDOUT:\n{stdout}")
        logger.info(f"STDERR:\n{stderr}")
        logger.info("---------------------------")

    # Clean up sensitive/internal state before returning/printing
    if "pipeline_config" in final_state_dict: del final_state_dict["pipeline_config"]
    if "a2a_wrapper" in final_state_dict: del final_state_dict["a2a_wrapper"]

    return final_state_dict

# --- Main Execution ---
async def main():
    """Parse arguments and run the pipeline."""
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    logger.info(f"Log level set to: {args.log_level}")

    final_state = await run_pipeline(
        input_file_path=args.file,
        input_python_code=args.code,
        project_id=args.project_id,
        config_path=args.config
    )

    try: # Print final state as JSON
        def default_serializer(obj):
            if isinstance(obj, datetime.datetime): return obj.isoformat()
            # Use model_dump if available (Pydantic v2)
            if hasattr(obj, 'model_dump') and callable(obj.model_dump):
                try:
                    return obj.model_dump(mode='json')
                except Exception:
                    pass # Fallback if model_dump fails
            # Try dict() for Pydantic v1 models
            if hasattr(obj, '__dict__'):
                try:
                    return dict(obj)
                except Exception:
                    pass
            return str(obj)

        print("\n--- FINAL STATE ---"); print(json.dumps(final_state, indent=2, default=default_serializer)); print("-------------------")
    except Exception as print_err: logger.error(f"Could not serialize final state: {print_err}"); print(final_state)

    if final_state.get("error_message"): sys.exit(1)

if __name__ == "__main__":
    # Ensure src is in path if running as script
    from pathlib import Path
    current_dir = Path(__file__).parent.resolve(); src_dir = current_dir.parent
    # Add dynamics orchestrator src path for shared A2AClientWrapper import
    dynamics_orchestrator_src = Path(__file__).parent.parent.parent / "dynamics_pipeline" / "src" / "dynamics_orchestrator"
    if str(src_dir) not in sys.path: sys.path.insert(0, str(src_dir)); logger.debug(f"Added {src_dir} to sys.path")
    if str(dynamics_orchestrator_src) not in sys.path: sys.path.insert(0, str(dynamics_orchestrator_src)); logger.debug(f"Added {dynamics_orchestrator_src} to sys.path")
    asyncio.run(main())
