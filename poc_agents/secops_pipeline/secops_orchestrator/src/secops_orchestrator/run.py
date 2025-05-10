import logging
import asyncio
import uuid
import json
import sys
import os
import argparse
import datetime
from typing import Dict, Any, Optional
from pathlib import Path

# Import pipeline events helper if available
try:
    from shared.pipeline_events import (
        emit_execution_started,
        emit_step_complete,
        emit_execution_completed
    )
    _EVENTS_AVAILABLE = True
except ImportError:
    try:
        # Try the direct publisher as a fallback
        from .direct_publish import (
            emit_execution_started,
            emit_step_complete,
            emit_execution_completed
        )
        _EVENTS_AVAILABLE = True
        logger.info("Using direct Redis publisher for dashboard events")
    except ImportError:
        _EVENTS_AVAILABLE = False
        logger.warning("No event publishing available - dashboard will not show pipeline executions")

# Setup logger early
# Basic config, will be overridden by settings load if successful
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try importing orchestrator components (REQ-SECOPS-ORCH-1.8)
try:
    logger.debug("Attempting imports for secops_orchestrator.run...")
    from .state_definition import SecopsPipelineState
    from .nodes import HANDLE_ERROR_NODE  # Import the node name constant
    from .graph import create_secops_graph
    from .config import settings, get_pipeline_config, SecopsPipelineConfig, ConfigurationError
    from .a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
    logger.debug("Imports successful.")
except ImportError as e:
    logger.error(f"Failed to import orchestrator components: {e}. Check PYTHONPATH and dependencies.", exc_info=True)
    # If basic imports fail, exit early.
    print(f"FATAL ERROR: Failed to import necessary orchestrator components: {e}", file=sys.stderr)
    print(f"Check installation and PYTHONPATH.", file=sys.stderr)
    sys.exit(1)
except Exception as e:
     logger.error(f"An unexpected error occurred during imports: {e}", exc_info=True)
     print(f"FATAL ERROR: Unexpected error during imports: {e}", file=sys.stderr)
     sys.exit(1)

# --- Parse Args (REQ-SECOPS-ORCH-1.8) ---
def parse_args():
    """Parse command line arguments for the SecOps Pipeline."""
    parser = argparse.ArgumentParser(description='Run the SecOps Alert Triage, Enrichment, and Response Pipeline.')
    # Define how initial alert data is provided
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--alert-file', type=str, help='Path to a JSON file containing the initial alert data (e.g., /data/alert.json).')
    input_group.add_argument('--alert-json', type=str, help='JSON string containing the initial alert data.')
    # Standard options
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default=os.environ.get('LOG_LEVEL', 'INFO'), help='Logging level (overrides LOG_LEVEL env var).')
    parser.add_argument('--project-id', type=str, help='Optional custom project ID (UUID will be generated if omitted)')
    parser.add_argument('--config', type=str, help='Path to custom pipeline configuration JSON file (overrides SECOPS_PIPELINE_CONFIG env var).')

    return parser.parse_args()

# --- Load Initial Alert Data (REQ-SECOPS-ORCH-1.8) ---
def load_initial_alert(args: argparse.Namespace) -> Dict[str, Any]:
    """Loads the initial alert data from file or JSON string."""
    if args.alert_file:
        alert_file_path = Path(args.alert_file)
        # Assume path might be relative to /app if not absolute
        if not alert_file_path.is_absolute():
            alert_file_path = Path("/app") / alert_file_path # Adjust if running outside Docker
        if not alert_file_path.is_file():
            raise FileNotFoundError(f"Alert file not found: {alert_file_path.resolve()}")
        try:
            with open(alert_file_path, 'r', encoding='utf-8') as f:
                alert_data = json.load(f)
            if not isinstance(alert_data, dict):
                raise ValueError("Alert file does not contain a valid JSON object.")
            logger.info(f"Loaded initial alert data from file: {alert_file_path.resolve()}")
            return alert_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from alert file {alert_file_path.resolve()}: {e}") from e
        except Exception as e:
            raise IOError(f"Failed to read alert file {alert_file_path.resolve()}: {e}") from e
    elif args.alert_json:
        try:
            alert_data = json.loads(args.alert_json)
            if not isinstance(alert_data, dict):
                raise ValueError("Alert JSON string is not a valid JSON object.")
            logger.info("Loaded initial alert data from JSON string argument.")
            return alert_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from alert string: {e}") from e
    else:
        # Should be caught by argparse mutual exclusion, but handle defensively
        raise ValueError("No initial alert data provided (use --alert-file or --alert-json).")


# --- Run Pipeline (REQ-SECOPS-ORCH-1.8) ---
async def run_pipeline(
    initial_alert_data: Dict[str, Any],
    project_id: Optional[str] = None,
    config_path: Optional[str] = None
) -> Dict[str, Any]:
    """Runs the SecOps pipeline graph."""
    start_time = datetime.datetime.now(datetime.timezone.utc)
    logger.info(f"--- Starting SecOps Pipeline Run ---")
    logger.info(f"Initial Alert Data Keys: {list(initial_alert_data.keys())}") # Log keys, not full data

    # Generate project ID if not provided
    if not project_id:
        project_id = f"secops-{start_time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    logger.info(f"Project ID: {project_id}")
    
    # Emit execution started event if available
    if _EVENTS_AVAILABLE:
        try:
            await emit_execution_started(project_id, initial_alert_data)
        except Exception as e:
            logger.warning(f"Failed to emit execution started event: {e}")

    pipeline_config: Optional[SecopsPipelineConfig] = None
    a2a_wrapper_instance: Optional[A2AClientWrapper] = None
    app = None
    final_state_dict: Dict[str, Any] = {"project_id": project_id, "status": "SETUP_FAILED", "error_message": "Initialization failed"}

    try:
        # 1. Load Configuration
        pipeline_config = get_pipeline_config(config_path)
        logger.info(f"Loaded SecOps config. Registry: {pipeline_config.orchestration.registry_url}")

        # 2. Initialize A2A Client Wrapper (handles agent discovery)
        a2a_wrapper_instance = A2AClientWrapper(config=pipeline_config)
        await a2a_wrapper_instance.initialize()
        logger.info("A2A Wrapper initialized.")

        # 3. Create LangGraph Application
        app = create_secops_graph()
        logger.info("SecOps pipeline graph compiled.")

        # 4. Prepare Initial State
        initial_state: SecopsPipelineState = {
            "pipeline_config": pipeline_config,
            "a2a_wrapper": a2a_wrapper_instance,
            "project_id": project_id,
            "initial_alert_data": initial_alert_data,
            "current_step": None, "error_message": None,
            "standardized_alert": None, "enrichment_results": None,
            "investigation_findings": None, "determined_response_action": None,
            "response_action_parameters": None, "response_action_status": None,
        }
        logger.info(f"Initial state prepared for Project ID: {project_id}")

        # 5. Invoke Graph
        logger.info("Invoking SecOps graph asynchronously...")
        recursion_limit = pipeline_config.orchestration.recursion_limit
        config_for_stream = {"recursion_limit": recursion_limit}
        final_event = None
        async for event in app.astream(initial_state, config=config_for_stream):
            # Capture the last event which should contain the final state
            final_event = event
            # Optional: Log intermediate steps if needed (can be very verbose)
            # logger.debug(f"Graph Event: {json.dumps(event, indent=2, default=str)}")

        logger.info("Graph invocation finished.")

        if final_event is None:
            raise AgentProcessingError("Graph stream completed without returning a final state.")

        # Extract the actual final state from the last event structure
        # The structure depends on where the graph ended (specific node or END)
        if isinstance(final_event, dict):
            # Look for state under the key of the last executed node, or __end__
            last_node_key = list(final_event.keys())[-1] # Get the last key
            final_state_dict = final_event.get(last_node_key, {})
        else:
             logger.error(f"Unexpected final event type from graph stream: {type(final_event)}")
             raise AgentProcessingError("Unexpected final event type from graph.")

        # Ensure project_id is preserved
        final_state_dict["project_id"] = project_id

    except (ConfigurationError, FileNotFoundError) as config_err:
        logger.critical(f"CRITICAL Config/Setup error: {config_err}", exc_info=True)
        final_state_dict = {"error_message": f"Setup error: {config_err}", "project_id": project_id, "status": "SETUP_FAILED"}
    except Exception as e:
        logger.exception("Error during graph setup or execution.")
        final_state_dict = dict(initial_state) if 'initial_state' in locals() else {"project_id": project_id}
        final_state_dict["error_message"] = f"Graph execution error: {type(e).__name__}: {e}"
        final_state_dict["status"] = "FAILED" # Add explicit status
    finally:
        # Ensure A2A client is closed
        if a2a_wrapper_instance:
            await a2a_wrapper_instance.close()
            logger.info("A2A Client Wrapper closed.")

    end_time = datetime.datetime.now(datetime.timezone.utc)
    duration = end_time - start_time
    logger.info(f"--- SecOps Pipeline Run Finished ---")
    logger.info(f"Project ID: {project_id}")
    logger.info(f"Duration: {duration}")

    # Determine final status based on error message
    error = final_state_dict.get("error_message")
    final_status = "UNKNOWN"
    if error:
        logger.error(f"Pipeline failed: {error}")
        final_status = "FAILED"
    elif final_state_dict: # Check if final_state_dict was populated
        # Check if the graph reached a known terminal state or just ended
        last_step = final_state_dict.get('current_step')
        if last_step == HANDLE_ERROR_NODE:
             final_status = "FAILED"
        else: # Assume completed if no error and graph finished
             final_status = "COMPLETED"
             logger.info(f"Pipeline completed successfully for project '{project_id}' (ended after step: {last_step or 'N/A'}).")   
    else:
         logger.error("Pipeline finished but final state dictionary is empty.")
         final_status = "UNKNOWN_ERROR"

    final_state_dict["status"] = final_status
    
    # Emit execution completed event if available
    if _EVENTS_AVAILABLE:
        try:
            # Create a clean copy of the state to emit
            event_state = {}
            for key, value in final_state_dict.items():
                # Skip internal objects
                if key not in ["pipeline_config", "a2a_wrapper"]:
                    event_state[key] = value
                    
            await emit_execution_completed(
                project_id=project_id,
                status=final_status,
                data=event_state,
                error=error
            )
        except Exception as e:
            logger.warning(f"Failed to emit execution completed event: {e}")

    # Clean up sensitive/internal state before returning/printing
    if "pipeline_config" in final_state_dict: del final_state_dict["pipeline_config"]
    if "a2a_wrapper" in final_state_dict: del final_state_dict["a2a_wrapper"]

    return final_state_dict

# --- Main Execution Block (REQ-SECOPS-ORCH-1.8) ---
async def main_cli():
    """Parse arguments and run the pipeline from CLI."""
    args = parse_args()

    # Update logging level based on args FIRST
    log_level_input = args.log_level or os.environ.get('LOG_LEVEL', 'INFO')
    log_level_int = getattr(logging, log_level_input.upper(), logging.INFO)
    # Use force=True to ensure root logger level is set even if already configured
    logging.basicConfig(level=log_level_int, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    # Set level for known loggers
    logging.getLogger("secops_orchestrator").setLevel(log_level_int)
    logging.getLogger("a2a_client_wrapper").setLevel(log_level_int)
    # Add other loggers if needed
    logging.getLogger("agentvault").setLevel(log_level_int) # Core library logger

    logger.info(f"Log level set to: {log_level_input.upper()}")

    try:
        initial_alert = load_initial_alert(args)
    except (FileNotFoundError, ValueError, IOError) as e:
        logger.critical(f"Failed to load initial alert data: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Unexpected error loading alert data: {e}", exc_info=True)
        sys.exit(1)

    final_state = await run_pipeline(
        initial_alert_data=initial_alert,
        project_id=args.project_id,
        config_path=args.config
    )

    # Print final state summary
    print("\n" + "="*30 + " Pipeline Execution Summary " + "="*30)
    print(f"Project ID: {final_state.get('project_id', 'N/A')}")
    print(f"Final Status: {final_state.get('status', 'UNKNOWN')}")
    if final_state.get("error_message"):
        print(f"Error: {final_state.get('error_message')}")
    # Optionally print key results if needed
    # print(f"Standardized Alert: {final_state.get('standardized_alert')}")
    # print(f"Enrichment: {final_state.get('enrichment_results')}")
    # print(f"Investigation: {final_state.get('investigation_findings')}")
    # print(f"Response Status: {final_state.get('response_action_status')}")
    print("="*88)

    # Exit with non-zero code if the pipeline failed or had errors
    if final_state.get("status") != "COMPLETED":
        sys.exit(1)

def cli_entry_point():
    """Synchronous wrapper for the async main function."""
    try:
        asyncio.run(main_cli())
    except KeyboardInterrupt:
        logger.warning("Pipeline execution interrupted by user.")
        sys.exit(130) # Standard exit code for Ctrl+C
    except Exception as e:
         logger.critical(f"Unhandled exception in pipeline execution: {e}", exc_info=True)
         sys.exit(1)


if __name__ == "__main__":
    # Ensure src directory is in Python path if running directly
    current_dir = Path(__file__).parent.resolve()
    src_dir = current_dir # Assumes run.py is directly in src/secops_orchestrator
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
        logger.debug(f"Added {src_dir} to sys.path")
    # Also add the parent of src to allow `from secops_orchestrator import ...`
    project_root_ish = src_dir.parent
    if str(project_root_ish) not in sys.path:
         sys.path.insert(0, str(project_root_ish))
         logger.debug(f"Added {project_root_ish} to sys.path")

    cli_entry_point()
