import asyncio
import logging
import uuid
import json
import sys
import os
import argparse
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Setup logger for early debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try importing the necessary modules from the support_orchestrator package
try:
    logger.debug("Attempting imports for support_orchestrator.run...")
    from support_orchestrator.state_definition import TicketProcessingState
    from support_orchestrator.graph import create_support_graph
    from support_orchestrator.config import settings, get_pipeline_config, SupportPipelineConfig, ConfigurationError
    from support_orchestrator.a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
    logger.debug("Imports successful.")
except ImportError as e:
    logger.error(f"Failed to import orchestrator components: {e}. sys.path: {sys.path}. Ensure PYTHONPATH is set correctly or run as a module.", exc_info=True)
    # Print CWD and attempt listing src for more context
    try:
        logger.error(f"Current working directory: {os.getcwd()}")
        logger.error(f"Contents of /app/src: {os.listdir('/app/src')}")
        logger.error(f"Contents of /app/src/support_orchestrator: {os.listdir('/app/src/support_orchestrator')}")
    except Exception as list_err:
        logger.error(f"Could not list directories: {list_err}")
    sys.exit(1)
except Exception as e:
     logger.error(f"An unexpected error occurred during imports: {e}", exc_info=True)
     sys.exit(1)


# --- Parse Args (REQ-SUP-ORCH-008) ---
def parse_args():
    """Parse command line arguments for the support pipeline."""
    parser = argparse.ArgumentParser(description='Run the Support Ticket Processing Pipeline.')
    # Expect arguments passed from entrypoint.sh / Docker CMD
    parser.add_argument(
        'ticket_text',
        type=str,
        help='The text content of the customer support ticket.'
    )
    parser.add_argument(
        'customer_identifier',
        type=str,
        help='The unique identifier (e.g., email, user ID) for the customer.'
    )
    parser.add_argument(
        '--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default=os.environ.get('LOG_LEVEL', 'INFO'), # Default from env or INFO
        help='Logging level'
    )
    parser.add_argument(
        '--project-id', type=str, help='Optional custom project ID (default: auto-generated)'
    )
    parser.add_argument(
        '--config', type=str, help='Path to a custom pipeline configuration JSON file (overrides .env setting).'
    )
    return parser.parse_args()

# --- Run Pipeline ---
async def run_pipeline(
    ticket_text: str,
    customer_identifier: str,
    project_id: Optional[str] = None,
    config_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run the support ticket processing pipeline. REQ-SUP-ORCH-008.
    """
    logger.info(f"--- Starting Support Ticket Pipeline Run for Customer: '{customer_identifier}' ---")

    # Load pipeline configuration using the specific function for this pipeline
    try:
        pipeline_config = get_pipeline_config(config_path) # Uses support_config.json by default
        logger.info(f"Loaded support pipeline configuration. Registry URL: {pipeline_config.orchestration.registry_url}")
    except (ConfigurationError, FileNotFoundError) as config_err:
        logger.critical(f"CRITICAL: Error loading pipeline configuration: {config_err}", exc_info=True)
        return {"error_message": f"Configuration error: {config_err}", "project_id": project_id, "customer_identifier": customer_identifier, "status": "FAILED"}
    except Exception as e:
         logger.critical(f"CRITICAL: Unexpected error loading configuration: {e}", exc_info=True)
         return {"error_message": f"Unexpected configuration error: {e}", "project_id": project_id, "customer_identifier": customer_identifier, "status": "FAILED"}

    if not project_id:
        project_id = f"supp-proj-{uuid.uuid4().hex[:8]}"

    a2a_wrapper_instance = None
    try:
        # Initialize the specific A2A wrapper for this pipeline
        a2a_wrapper_instance = A2AClientWrapper(config=pipeline_config)
        await a2a_wrapper_instance.initialize()
        logger.info("A2A Client Wrapper initialized successfully (support agents discovered).")
    except ConfigurationError as e:
        logger.error(f"Configuration error initializing A2A Wrapper: {e}. Cannot proceed.")
        return {"error_message": f"Configuration error: {e}", "project_id": project_id, "customer_identifier": customer_identifier, "status": "FAILED"}
    except Exception as e:
        logger.exception("Failed to initialize A2A Client Wrapper.")
        return {"error_message": f"Failed to initialize A2A Wrapper: {e}", "project_id": project_id, "customer_identifier": customer_identifier, "status": "FAILED"}

    try:
        # Create the specific graph for this pipeline
        app = create_support_graph()
        logger.info("Support ticket processing graph compiled successfully.")
    except Exception as e:
        logger.exception("Failed to create or compile the support graph.")
        if a2a_wrapper_instance: await a2a_wrapper_instance.close()
        return {"error_message": f"Graph compilation failed: {e}", "project_id": project_id, "customer_identifier": customer_identifier, "status": "FAILED"}

    # Prepare initial state (REQ-SUP-ORCH-003)
    initial_state: TicketProcessingState = {
        "ticket_text": ticket_text,
        "customer_identifier": customer_identifier,
        "pipeline_config": pipeline_config,
        "a2a_wrapper": a2a_wrapper_instance,
        "project_id": project_id,
        "current_step": None,
        "error_message": None,
        "ticket_analysis": None,
        "kb_results": None,
        "customer_history": None,
        "suggested_response": None,
        "local_artifact_references": {},
        # Add request_context if needed later, currently unused
        # "request_context": {},
    }
    logger.info(f"Initial input prepared for Project ID: {project_id}, Customer: '{customer_identifier}'")
    logger.debug(f"Initial State Input Keys: {list(initial_state.keys())}")

    final_state_dict: Dict[str, Any] = {}
    try:
        logger.info("Invoking the support ticket graph asynchronously...")
        recursion_limit = pipeline_config.orchestration.recursion_limit
        # --- MODIFIED: Use the correct state type ---
        final_state_typed: TicketProcessingState = await app.ainvoke(initial_state, {"recursion_limit": recursion_limit})
        # --- END MODIFIED ---
        # Convert TypedDict back to dict for easier processing/serialization
        final_state_dict = dict(final_state_typed)
        logger.info("Graph invocation finished.")

    except Exception as e:
        logger.exception("An error occurred during graph execution.")
        # Try to preserve initial state info in case of failure
        final_state_dict = dict(initial_state) # Convert initial state too
        final_state_dict["error_message"] = f"Graph execution error: {e}"
        final_state_dict["status"] = "FAILED"
    finally:
        if a2a_wrapper_instance:
            logger.info("Closing A2A Client Wrapper...")
            await a2a_wrapper_instance.close()
            logger.info("A2A Client Wrapper closed.")

    logger.info("--- Support Pipeline Run Finished ---")
    if not final_state_dict:
         logger.error("Graph execution failed to return a final state.")
         final_state_dict = {"error_message": "Graph execution failed unexpectedly.", "project_id": project_id, "customer_identifier": customer_identifier, "status": "FAILED"}

    error = final_state_dict.get("error_message")
    if error:
        logger.error(f"Pipeline failed: {error}")
        final_state_dict["status"] = "FAILED"
    else:
        logger.info(f"Pipeline completed successfully for customer '{customer_identifier}'")
        final_state_dict["status"] = "COMPLETED"

    # Log final suggested response if available
    suggested_response = final_state_dict.get("suggested_response")
    if suggested_response:
        logger.info("--- Suggested Response ---")
        logger.info(suggested_response)
        logger.info("------------------------")
    elif not error:
         logger.warning("Pipeline completed but no suggested response was generated.")

    artifacts = final_state_dict.get("local_artifact_references", {})
    if artifacts:
        logger.info("Generated artifacts saved locally:")
        for artifact_type, path in artifacts.items():
            logger.info(f"  - {artifact_type}: {path}")

    # Clean up non-serializable objects before returning/printing
    if "pipeline_config" in final_state_dict: del final_state_dict["pipeline_config"]
    if "a2a_wrapper" in final_state_dict: del final_state_dict["a2a_wrapper"]

    return final_state_dict

# --- Main Execution ---
async def main():
    """Parse arguments and run the pipeline."""
    args = parse_args()

    # Configure logging based on args
    log_level = args.log_level
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True # Override root logger config if already set
    )
    logger.info(f"Log level set to: {log_level}")
    logger.info(f"Received Ticket Text: {args.ticket_text[:100]}...")
    logger.info(f"Received Customer Identifier: {args.customer_identifier}")

    final_state = await run_pipeline(
        ticket_text=args.ticket_text,
        customer_identifier=args.customer_identifier,
        project_id=args.project_id,
        config_path=args.config
    )

    # Print final state as JSON
    try:
        # Custom serializer for non-serializable types like Pydantic models or datetime
        def default_serializer(obj):
            if isinstance(obj, datetime.datetime): return obj.isoformat()
            # Attempt Pydantic serialization first
            if hasattr(obj, 'model_dump') and callable(getattr(obj, 'model_dump')):
                 try: return obj.model_dump(mode='json')
                 except Exception: pass # Fall through if model_dump fails
            # Fallback to string representation
            return str(obj)

        print("\n--- FINAL STATE ---")
        print(json.dumps(final_state, indent=2, default=default_serializer))
        print("-------------------")
    except Exception as print_err:
        logger.error(f"Could not serialize final state for printing: {print_err}")
        print("\n--- FINAL STATE (RAW) ---")
        print(final_state) # Print raw dict if JSON fails
        print("-------------------------")

    # Exit with error code if pipeline failed
    if final_state.get("error_message"):
        sys.exit(1)

if __name__ == "__main__":
    # Ensure the script can find its own package modules when run directly
    # This might be needed depending on execution context
    current_dir = Path(__file__).parent.resolve()
    src_dir = current_dir.parent # Navigate up to 'src'
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
        logger.debug(f"Added {src_dir} to sys.path")

    # Double-check imports again after potential path modification
    try:
        from support_orchestrator.state_definition import TicketProcessingState # noqa F401
        logger.debug("Verified imports after potential path adjustment.")
    except ImportError as e:
        logger.critical(f"Still cannot import after path adjustment: {e}", exc_info=True)
        sys.exit(1)

    asyncio.run(main())
