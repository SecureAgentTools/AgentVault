import asyncio
import logging
import uuid
import json
import sys
import os
import argparse
import datetime
from typing import Dict, Any, Optional
from pathlib import Path # Ensure Path is imported

# Setup logger early
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try importing orchestrator components
try:
    logger.debug("Attempting imports for dynamics_orchestrator.run...")
    from dynamics_orchestrator.state_definition import AccountProcessingState
    from dynamics_orchestrator.graph import create_dynamics_graph
    from dynamics_orchestrator.config import settings, get_pipeline_config, DynamicsPipelineConfig, ConfigurationError
    from dynamics_orchestrator.a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
    logger.debug("Imports successful.")
except ImportError as e:
    logger.error(f"Failed to import orchestrator components: {e}. sys.path: {sys.path}.", exc_info=True)
    sys.exit(1)
except Exception as e:
     logger.error(f"An unexpected error occurred during imports: {e}", exc_info=True)
     sys.exit(1)

# --- Parse Args ---
def parse_args():
    """Parse command line arguments for the Dynamics pipeline."""
    parser = argparse.ArgumentParser(description='Run the Dynamics Account Processing Pipeline.')
    parser.add_argument('account_id', type=str, help='The Dynamics Account GUID to process.')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default=os.environ.get('LOG_LEVEL', 'INFO'), help='Logging level')
    parser.add_argument('--project-id', type=str, help='Optional custom project ID')
    parser.add_argument('--config', type=str, help='Path to custom pipeline configuration JSON file.')
    return parser.parse_args()

# --- Run Pipeline ---
async def run_pipeline(account_id: str, project_id: Optional[str] = None, config_path: Optional[str] = None) -> Dict[str, Any]:
    """Runs the Dynamics account processing pipeline."""
    logger.info(f"--- Starting Dynamics Pipeline Run for Account ID: '{account_id}' ---")
    try:
        pipeline_config = get_pipeline_config(config_path)
        logger.info(f"Loaded Dynamics config. Registry: {pipeline_config.orchestration.registry_url}")
    except (ConfigurationError, FileNotFoundError) as config_err:
        logger.critical(f"CRITICAL Config error: {config_err}", exc_info=True)
        return {"error_message": f"Configuration error: {config_err}", "project_id": project_id, "account_id": account_id, "status": "FAILED"}
    except Exception as e:
         logger.critical(f"CRITICAL: Unexpected config error: {e}", exc_info=True)
         return {"error_message": f"Unexpected config error: {e}", "project_id": project_id, "account_id": account_id, "status": "FAILED"}

    if not project_id: project_id = f"d365-proj-{uuid.uuid4().hex[:8]}"

    a2a_wrapper_instance = None
    try:
        a2a_wrapper_instance = A2AClientWrapper(config=pipeline_config)
        await a2a_wrapper_instance.initialize()
        logger.info("A2A Wrapper initialized (Dynamics agents discovered).")
    except Exception as e:
        logger.exception("Failed to initialize A2A Wrapper."); return {"error_message": f"A2A Init failed: {e}", "project_id": project_id, "status": "FAILED"}

    try:
        app = create_dynamics_graph()
        logger.info("Dynamics pipeline graph compiled.")
    except Exception as e:
        logger.exception("Failed to create/compile Dynamics graph.");
        if a2a_wrapper_instance: await a2a_wrapper_instance.close()
        return {"error_message": f"Graph compilation failed: {e}", "project_id": project_id, "status": "FAILED"}

    initial_state: AccountProcessingState = {
        "account_id": account_id,
        "pipeline_config": pipeline_config,
        "a2a_wrapper": a2a_wrapper_instance,
        "project_id": project_id,
        "current_step": None, "error_message": None,
        "dynamics_data": None, "external_data": None,
        "account_analysis": None, "account_briefing": None,
    }
    logger.info(f"Initial state prepared for Project ID: {project_id}, Account: '{account_id}'")

    final_state_dict: Dict[str, Any] = {}
    try:
        logger.info("Invoking Dynamics graph asynchronously...")
        recursion_limit = pipeline_config.orchestration.recursion_limit
        final_state_typed: AccountProcessingState = await app.ainvoke(initial_state, {"recursion_limit": recursion_limit})
        final_state_dict = dict(final_state_typed)
        logger.info("Graph invocation finished.")
    except Exception as e:
        logger.exception("Error during graph execution.")
        final_state_dict = dict(initial_state); final_state_dict["error_message"] = f"Graph execution error: {e}"; final_state_dict["status"] = "FAILED"
    finally:
        if a2a_wrapper_instance: await a2a_wrapper_instance.close(); logger.info("A2A Client Wrapper closed.")

    logger.info("--- Dynamics Pipeline Run Finished ---")
    if not final_state_dict: final_state_dict = {"error_message": "Graph execution failed unexpectedly.", "project_id": project_id, "status": "FAILED"}

    error = final_state_dict.get("error_message")
    if error: logger.error(f"Pipeline failed: {error}"); final_state_dict["status"] = "FAILED"
    else: logger.info(f"Pipeline completed successfully for account '{account_id}'"); final_state_dict["status"] = "COMPLETED"

    briefing = final_state_dict.get("account_briefing")
    if briefing: 
        # Add automated actions summary to the briefing for visibility
        # Always add notification section for consistency
        notification_summary = "\n\n" + "="*80 + "\n\n"
        notification_summary += "🚨 AUTOMATED ACTIONS REPORT 🚨\n" + "="*40 + "\n\n"
        
        # Check if we have execution results
        has_execution_results = "action_execution_results" in final_state_dict and final_state_dict["action_execution_results"]
        
        if has_execution_results:
            execution_results = final_state_dict["action_execution_results"]
            
            # Format task creation results
            task_results = execution_results.get("task_creation", [])
            slack_results = execution_results.get("slack_notification", [])
            teams_results = execution_results.get("teams_notification", [])
            
            successful_tasks = [t for t in task_results if t.get("success", False)]
            successful_slack = [t for t in slack_results if t.get("success", False)]
            successful_teams = [t for t in teams_results if t.get("success", False)]
            
            if successful_tasks:
                notification_summary += f"📝 TASKS CREATED IN DYNAMICS: {len(successful_tasks)}\n\n"
                for i, task in enumerate(successful_tasks):
                    task_id = task.get("created_task_id", "Unknown")
                    task_subject = task.get("task_subject", "[No subject]")
                    notification_summary += f"  ✓ Task #{i+1}: ID {task_id}\n"
                    notification_summary += f"      Subject: {task_subject[:60] + '...' if len(task_subject) > 60 else task_subject}\n\n"
            
            if successful_slack or successful_teams:
                notification_summary += "🔔 NOTIFICATIONS SENT:\n\n"
                
                if successful_slack:
                    notification_summary += f"  ✓ {len(successful_slack)} Slack notifications to #dynamics-alerts\n"
                
                if successful_teams:
                    notification_summary += f"  ✓ {len(successful_teams)} Teams notifications\n"
                
            # If we had execution results but no successful actions
            if not (successful_tasks or successful_slack or successful_teams):
                notification_summary += "\n🚦 NO SUCCESSFUL ACTIONS WERE EXECUTED\n"
                notification_summary += "Please check logs for possible errors.\n"
        else:
            # No execution results at all - likely no high-priority actions were found
            notification_summary += "🚦 NO AUTOMATED ACTIONS WERE EXECUTED\n\n"
            notification_summary += "* No high-priority actions were identified\n"
            notification_summary += "* Only high-priority actions trigger automated execution\n"
            notification_summary += "* Review the recommended actions in the briefing below\n"
        
        notification_summary += "\n" + "="*80 + "\n\n"
        
        # Prepend the summary to the briefing
        final_state_dict["account_briefing"] = notification_summary + briefing
        briefing = final_state_dict["account_briefing"]
            
        logger.info(f"\n--- Generated Briefing ---\n{briefing}\n------------------------")
    elif not error: logger.warning("Pipeline completed but no briefing was generated.")

    if "pipeline_config" in final_state_dict: del final_state_dict["pipeline_config"]
    if "a2a_wrapper" in final_state_dict: del final_state_dict["a2a_wrapper"]

    return final_state_dict

# --- Main Execution ---
async def main():
    """Parse arguments and run the pipeline."""
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
    logger.info(f"Log level set to: {args.log_level}")
    logger.info(f"Received Account ID: {args.account_id}")

    final_state = await run_pipeline(account_id=args.account_id, project_id=args.project_id, config_path=args.config)

    try: # Print final state as JSON
        # CORRECTED default_serializer function (AGAIN for this file)
        def default_serializer(obj):
            if isinstance(obj, datetime.datetime):
                return obj.isoformat()
            # Attempt Pydantic serialization first
            if hasattr(obj, 'model_dump') and callable(getattr(obj, 'model_dump')):
                try:
                    # Use try-except block on separate lines
                    return obj.model_dump(mode='json')
                except Exception:
                    # Fall through if model_dump fails
                    pass
            # Fallback to string representation
            return str(obj)

        print("\n--- FINAL STATE ---"); print(json.dumps(final_state, indent=2, default=default_serializer)); print("-------------------")
    except Exception as print_err: logger.error(f"Could not serialize final state: {print_err}"); print(final_state)

    if final_state.get("error_message"): sys.exit(1)

if __name__ == "__main__":
    # Ensure Path is imported before use
    from pathlib import Path
    current_dir = Path(__file__).parent.resolve(); src_dir = current_dir.parent
    if str(src_dir) not in sys.path: sys.path.insert(0, str(src_dir)); logger.debug(f"Added {src_dir} to sys.path")
    asyncio.run(main())
