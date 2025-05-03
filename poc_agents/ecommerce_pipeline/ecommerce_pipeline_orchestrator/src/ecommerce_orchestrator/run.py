import asyncio
import logging
import uuid
import json
import sys
import os
import argparse
import datetime
from typing import Dict, Any, List, Optional

# Early debugging - print Python path and CWD
print("DEBUG - Python sys.path:")
for p in sys.path:
    print(f"  {p}")
print(f"DEBUG - Current working directory: {os.getcwd()}")
print(f"DEBUG - Directory contents of /app/src:")
try:
    print("\n".join(os.listdir("/app/src")))
except Exception as e:
    print(f"Error listing /app/src: {e}")

# Setup logger for early debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try importing the necessary modules
try:
    # Import from the ecommerce_orchestrator package
    print("DEBUG - Attempting imports...")
    from ecommerce_orchestrator.state_definition import RecommendationState
    print("DEBUG - Imported RecommendationState successfully")
    from ecommerce_orchestrator.graph import create_ecommerce_graph
    print("DEBUG - Imported create_ecommerce_graph successfully")
    from ecommerce_orchestrator.config import settings, get_pipeline_config, EcommercePipelineConfig
    print("DEBUG - Imported config components successfully")
    from ecommerce_orchestrator.a2a_client_wrapper import A2AClientWrapper, AgentProcessingError, ConfigurationError
    print("DEBUG - Imported A2AClientWrapper successfully")
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    logger.error(f"Failed to import orchestrator components: {e}. sys.path: {sys.path}. Ensure PYTHONPATH is set correctly or run as a module.")
    sys.exit(1)

# Setup logger for this script
logger = logging.getLogger(__name__)

# --- Parse Args ---
def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run the E-commerce Recommendation Pipeline.'
    )
    # --- MODIFIED: Accept user_id as positional argument after -m module ---
    # The script receives args *after* the module name and its args
    # The entrypoint/CMD passes "docker-test-user" which becomes the first arg here
    parser.add_argument(
        'user_id', # Make it positional
        type=str,
        help='The user ID for which to generate recommendations.'
    )
    # --- END MODIFIED ---
    parser.add_argument(
        '--context-product-id', type=str, help='Optional: Product ID the user is currently viewing.'
    )
    parser.add_argument(
        '--context-search-query', type=str, help='Optional: Search query the user entered.'
    )
    parser.add_argument(
        '--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO', help='Logging level'
    )
    parser.add_argument(
        '--project-id', type=str, help='Optional custom project ID (default: auto-generated)'
    )
    parser.add_argument(
        '--config', type=str, help='Path to a custom pipeline configuration JSON file (overrides .env setting).'
    )
    # We need to parse known args because the entrypoint might pass unexpected things?
    # Or adjust entrypoint to only pass known args. Let's assume entrypoint passes only user_id for now.
    # return parser.parse_known_args() # If entrypoint passes more than user_id
    return parser.parse_args() # If entrypoint passes only user_id

# --- Run Pipeline ---
async def run_pipeline(
    user_id: str,
    context_product_id: Optional[str] = None,
    context_search_query: Optional[str] = None,
    project_id: Optional[str] = None,
    config_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run the e-commerce recommendation pipeline.
    """
    logger.info(f"--- Starting E-commerce Recommendation Pipeline Run for User: '{user_id}' ---")

    # Load pipeline configuration
    try:
        # Try multiple config paths
        config_paths = [
            config_path,  # First try the explicitly provided path
            "/app/ecommerce_config.json",  # Then try the root location
            "/app/src/ecommerce_orchestrator/ecommerce_config.json"  # Finally try the package location
        ]
        
        # Filter out None values
        config_paths = [p for p in config_paths if p]
        
        logger.info(f"Trying config paths: {config_paths}")
        
        # Try each path in order
        pipeline_config = None
        last_error = None
        
        for path in config_paths:
            try:
                logger.info(f"Trying to load config from: {path}")
                pipeline_config = get_pipeline_config(path)
                logger.info(f"Successfully loaded config from: {path}")
                break
            except Exception as e:
                logger.warning(f"Failed to load config from {path}: {e}")
                last_error = e
        
        # If we couldn't load from any path, use default config
        if pipeline_config is None:
            if last_error:
                logger.error(f"All config paths failed. Last error: {last_error}")
            logger.warning("Using default configuration as fallback")
            pipeline_config = get_pipeline_config(None)  # This should return default config
    except Exception as config_err:
        logger.error(f"Error loading pipeline configuration: {config_err}")
        return {"error_message": f"Configuration error: {config_err}", "project_id": project_id, "user_id": user_id, "status": "FAILED"}

    logger.info(f"Loaded pipeline configuration. Registry URL: {pipeline_config.orchestration.registry_url}")

    if not project_id:
        project_id = f"ecom-proj-{uuid.uuid4().hex[:8]}"

    request_context = {}
    if context_product_id: request_context["current_product_id"] = context_product_id
    if context_search_query: request_context["search_query"] = context_search_query

    a2a_wrapper_instance = None
    try:
        a2a_wrapper_instance = A2AClientWrapper(config=pipeline_config)
        await a2a_wrapper_instance.initialize()
        logger.info("A2A Client Wrapper initialized successfully (agents discovered via registry).")
    except ConfigurationError as e:
        logger.error(f"Configuration error initializing A2A Wrapper: {e}. Cannot proceed.")
        return {"error_message": f"Configuration error: {e}", "project_id": project_id, "user_id": user_id, "status": "FAILED"}
    except Exception as e:
        logger.exception("Failed to initialize A2A Client Wrapper.")
        return {"error_message": f"Failed to initialize A2A Wrapper: {e}", "project_id": project_id, "user_id": user_id, "status": "FAILED"}

    try:
        app = create_ecommerce_graph()
        logger.info("E-commerce recommendation graph compiled successfully.")
    except Exception as e:
        logger.exception("Failed to create or compile the e-commerce graph.")
        if a2a_wrapper_instance: await a2a_wrapper_instance.close()
        return {"error_message": f"Graph compilation failed: {e}", "project_id": project_id, "user_id": user_id, "status": "FAILED"}

    initial_state: RecommendationState = {
        "user_id": user_id,
        "request_context": request_context,
        "project_id": project_id,
        "pipeline_config": pipeline_config,
        "a2a_wrapper": a2a_wrapper_instance,
        "current_step": None,
        "error_message": None,
        "user_profile": None,
        "product_details": None,
        "trending_data": None,
        "recommendations": None,
        "local_artifact_references": {},
    }
    logger.info(f"Initial input prepared for Project ID: {project_id}, User ID: '{user_id}'")
    logger.debug(f"Initial State Input Keys: {list(initial_state.keys())}")

    final_state_dict: Dict[str, Any] = {}
    try:
        logger.info("Invoking the e-commerce recommendation graph asynchronously...")
        recursion_limit = pipeline_config.orchestration.recursion_limit
        final_state_typed: RecommendationState = await app.ainvoke(initial_state, {"recursion_limit": recursion_limit})
        final_state_dict = dict(final_state_typed)
        logger.info("Graph invocation finished.")

    except Exception as e:
        logger.exception("An error occurred during graph execution.")
        final_state_dict = dict(initial_state)
        final_state_dict["error_message"] = f"Graph execution error: {e}"
        final_state_dict["status"] = "FAILED"
    finally:
        if a2a_wrapper_instance:
            logger.info("Closing A2A Client Wrapper...")
            await a2a_wrapper_instance.close()
            logger.info("A2A Client Wrapper closed.")

    logger.info("--- Pipeline Run Finished ---")
    if not final_state_dict:
         logger.error("Graph execution failed to return a final state.")
         final_state_dict = {"error_message": "Graph execution failed unexpectedly.", "project_id": project_id, "user_id": user_id, "status": "FAILED"}

    error = final_state_dict.get("error_message")
    if error:
        logger.error(f"Pipeline failed: {error}")
        final_state_dict["status"] = "FAILED"
    else:
        logger.info(f"Pipeline completed successfully for user '{user_id}'")
        final_state_dict["status"] = "COMPLETED"

    recommendations = final_state_dict.get("recommendations")
    if recommendations is not None:
        logger.info(f"Generated {len(recommendations)} recommendations.")
        for i, rec in enumerate(recommendations[:3]):
            rec_dict = rec.model_dump(mode='json') if hasattr(rec, 'model_dump') else rec
            name = rec_dict.get('name', 'Unknown Product')
            price = rec_dict.get('price', 'N/A')
            logger.info(f"  Rec {i+1}: ID={rec_dict.get('product_id')}, Name={name}, Price=${price}, Score={rec_dict.get('recommendation_score')}, Reason={rec_dict.get('reasoning')}")
    elif not error:
         logger.warning("Pipeline completed but no recommendations were generated.")

    artifacts = final_state_dict.get("local_artifact_references", {})
    if artifacts:
        logger.info("Generated artifacts saved locally:")
        for artifact_type, path in artifacts.items():
            logger.info(f"  - {artifact_type}: {path}")

    if "pipeline_config" in final_state_dict: del final_state_dict["pipeline_config"]
    if "a2a_wrapper" in final_state_dict: del final_state_dict["a2a_wrapper"]

    return final_state_dict

# --- Main Execution ---
async def main():
    """Parse arguments and run the pipeline."""
    try:
        args = parse_args()
        user_id = args.user_id
        logger.info(f"Using user_id from command line args: {user_id}")
    except Exception as e:
        # If argument parsing fails (when called directly), use default user ID
        logger.info(f"Argument parsing failed: {e}. Using default user_id.")
        # Create a simple object with attributes to match args
        class Args:
            pass
        args = Args()
        args.user_id = "docker-test-user"
        args.context_product_id = None
        args.context_search_query = None
        args.log_level = "INFO"
        args.project_id = None
        args.config = None
        logger.info(f"Using default user_id: {args.user_id}")

    log_level = args.log_level
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )
    # Log the received user_id
    logger.info(f"Received user_id: {args.user_id}")

    final_state = await run_pipeline(
        user_id=args.user_id, # Pass positional arg
        context_product_id=args.context_product_id,
        context_search_query=args.context_search_query,
        project_id=args.project_id,
        config_path=args.config
    )

    try:
        def default_serializer(obj):
            if isinstance(obj, datetime.datetime): return obj.isoformat()
            if hasattr(obj, 'model_dump') and callable(getattr(obj, 'model_dump')):
                 try: return obj.model_dump(mode='json')
                 except Exception: return str(obj)
            return str(obj)

        print(json.dumps(final_state, indent=2, default=default_serializer))
    except Exception as print_err:
        logger.error(f"Could not serialize final state for printing: {print_err}")
        print(final_state)

    if final_state.get("error_message"):
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
