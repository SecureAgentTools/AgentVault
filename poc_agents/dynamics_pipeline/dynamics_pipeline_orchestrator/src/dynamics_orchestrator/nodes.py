import logging
import asyncio
from typing import Dict, Any, List, Optional, cast
import uuid

from pydantic import ValidationError # For validating agent responses

# Import state definition, models, config, and wrapper for this pipeline
from dynamics_orchestrator.state_definition import AccountProcessingState
from dynamics_orchestrator.a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
from dynamics_orchestrator.config import DynamicsPipelineConfig
from dynamics_orchestrator.models import ( # Import models for type hints and validation
    DynamicsDataPayload, ExternalDataPayload, AccountAnalysisPayload, RecommendedAction,
    DynamicsFetcherOutput, ExternalEnricherOutput, AccountAnalyzerOutput,
    ActionRecommenderOutput, BriefingGeneratorOutput, # Keep existing
    # --- ADDED: Import output models for new execution agents ---
    CreateTaskOutput, SendNotificationOutput
    # --- END ADDED ---
)


logger = logging.getLogger(__name__)

# --- Constants for node names ---
START_NODE = "start_account_processing"
FETCH_DYNAMICS_NODE = "fetch_dynamics_data"
FETCH_EXTERNAL_NODE = "fetch_external_data"
ANALYZE_HEALTH_NODE = "analyze_account_health"
RECOMMEND_ACTIONS_NODE = "recommend_actions"
# --- ADDED: New node constant ---
EXECUTE_ACTIONS_NODE = "execute_recommended_actions"
# --- END ADDED ---
GENERATE_BRIEFING_NODE = "generate_account_briefing"
ERROR_HANDLER_NODE = "handle_pipeline_error"

# --- Node Functions (REQ-DYN-ORCH-004) ---

async def start_account_processing(state: AccountProcessingState) -> Dict[str, Any]:
    """Initial node: Logs start, validates essential state components."""
    project_id = state["project_id"]; account_id = state["account_id"]
    config: DynamicsPipelineConfig = state.get("pipeline_config") # type: ignore
    a2a_wrapper: A2AClientWrapper = state.get("a2a_wrapper") # type: ignore
    if not config or not a2a_wrapper or not account_id: return {"error_message": "Initial state missing config, wrapper, or account_id."}
    logger.info(f"NODE: {START_NODE} (Project: {project_id}) - Starting pipeline for Account ID: {account_id}")
    # Initialize recommended_actions and execution results in the state
    return {
        "current_step": START_NODE,
        "error_message": None,
        "recommended_actions": [],
        "action_execution_results": {} # Store results like {'task_creation': [...], 'slack': [...]}
    }

async def fetch_dynamics_data(state: AccountProcessingState) -> Dict[str, Any]:
    """Node to call the Dynamics Data Fetcher Agent."""
    try:
        config: DynamicsPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]; account_id = state["account_id"]
    except KeyError as e:
        return {"error_message": f"State missing key: {e}"}

    agent_hri = config.fetcher_agent.hri
    logger.info(f"NODE: {FETCH_DYNAMICS_NODE} (Project: {project_id}) - Calling agent {agent_hri} for account {account_id}")

    try:
        input_payload = {"account_id": account_id}
        result_data = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        logger.debug(f"Raw result from {agent_hri}: {result_data}")

        # Validate the structure of the returned data
        validated_output = DynamicsFetcherOutput.model_validate(result_data)
        dynamics_payload = validated_output.dynamics_data
        logger.info(f"Successfully fetched and validated Dynamics data for account {account_id}.")

        # Ensure account data exists, even if minimal
        if not dynamics_payload.account:
            logger.warning(f"Dynamics payload missing account data for {account_id}. Creating default placeholder.")
            from dynamics_orchestrator.models import AccountData
            dynamics_payload.account = AccountData(account_id=account_id, name=f"Unknown Account {account_id}", status="Not Found")

        return {"dynamics_data": dynamics_payload, "current_step": FETCH_DYNAMICS_NODE, "error_message": None}

    except (ValidationError, AgentProcessingError) as e:
        logger.error(f"NODE: {FETCH_DYNAMICS_NODE} - Error validating or processing response from {agent_hri}: {e}")
        return {"error_message": f"Error fetching/validating Dynamics data: {e}"}
    except Exception as e:
        logger.exception(f"NODE: {FETCH_DYNAMICS_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Unexpected error in {agent_hri}: {str(e)}"}

async def fetch_external_data(state: AccountProcessingState) -> Dict[str, Any]:
    """Node to call the External Data Enrichment Agent."""
    try:
        config: DynamicsPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        dynamics_data = state.get("dynamics_data")
        # Check if account and website exist
        if not dynamics_data or not dynamics_data.account or not dynamics_data.account.website:
            logger.warning(f"Project {project_id}: Skipping external data fetch - website missing in dynamics_data.")
            return {"external_data": ExternalDataPayload(), "current_step": FETCH_EXTERNAL_NODE, "error_message": None} # Return empty default, not None

        website = str(dynamics_data.account.website) # Convert HttpUrl to string if needed
    except KeyError as e: return {"error_message": f"State missing key: {e}"}

    agent_hri = config.enricher_agent.hri
    logger.info(f"NODE: {FETCH_EXTERNAL_NODE} (Project: {project_id}) - Calling agent {agent_hri} for website '{website}'")
    try:
        input_payload = {"website": website}
        result_data = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        validated_output = ExternalEnricherOutput.model_validate(result_data)
        external_payload = validated_output.external_data
        logger.info(f"Successfully fetched external data for website {website}.")
        return {"external_data": external_payload, "current_step": FETCH_EXTERNAL_NODE, "error_message": None}
    except (ValidationError, AgentProcessingError) as e:
        logger.error(f"NODE: {FETCH_EXTERNAL_NODE} - Error validating/processing response from {agent_hri}: {e}")
        logger.warning(f"Proceeding without external data due to error: {e}")
        return {"external_data": ExternalDataPayload(), "current_step": FETCH_EXTERNAL_NODE, "error_message": None} # Return empty default
    except Exception as e:
        logger.exception(f"NODE: {FETCH_EXTERNAL_NODE} failed for project {project_id}: {e}")
        logger.warning(f"Proceeding without external data due to unexpected error: {e}")
        return {"external_data": ExternalDataPayload(), "current_step": FETCH_EXTERNAL_NODE, "error_message": None} # Return empty default

async def analyze_account_health(state: AccountProcessingState) -> Dict[str, Any]:
    """Node to call the Account Health Analyzer Agent."""
    try:
        config: DynamicsPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        dynamics_data = state.get("dynamics_data")
        external_data = state.get("external_data") # Should be ExternalDataPayload (possibly empty)
    except KeyError as e: return {"error_message": f"State missing key: {e}"}

    if not dynamics_data: return {"error_message": "Cannot analyze health: Dynamics data is missing."}
    # Ensure external_data is the correct type, even if empty
    if not external_data: external_data = ExternalDataPayload()

    agent_hri = config.analyzer_agent.hri
    logger.info(f"NODE: {ANALYZE_HEALTH_NODE} (Project: {project_id}) - Calling agent {agent_hri}")
    try:
        input_payload = {
            "dynamics_data": dynamics_data.model_dump(mode='json'),
            "external_data": external_data.model_dump(mode='json')
        }
        result_data = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        validated_output = AccountAnalyzerOutput.model_validate(result_data)
        analysis_payload = validated_output.account_analysis
        logger.info(f"Successfully analyzed account health. Risk: {analysis_payload.risk_level}, Opp: {analysis_payload.opportunity_level}")
        return {"account_analysis": analysis_payload, "current_step": ANALYZE_HEALTH_NODE, "error_message": None}
    except (ValidationError, AgentProcessingError) as e:
        logger.error(f"NODE: {ANALYZE_HEALTH_NODE} - Error validating/processing response from {agent_hri}: {e}")
        return {"error_message": f"Error analyzing account health: {e}"}
    except Exception as e:
        logger.exception(f"NODE: {ANALYZE_HEALTH_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Unexpected error in {agent_hri}: {str(e)}"}

async def recommend_actions(state: AccountProcessingState) -> Dict[str, Any]:
    """Node to call the Action Recommendation Agent."""
    try:
        config: DynamicsPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        account_id = state["account_id"]
        dynamics_data = state.get("dynamics_data")
        external_data = state.get("external_data")
        account_analysis = state.get("account_analysis")
        account_briefing = state.get("account_briefing") # Optional briefing from previous step (if graph changes)
    except KeyError as e: return {"error_message": f"State missing key for recommendation: {e}"}

    # Ensure required inputs are present
    if not all([dynamics_data, external_data, account_analysis]):
        return {"error_message": "Cannot recommend actions: Missing dynamics, external, or analysis data."}

    agent_hri = config.recommender_agent.hri
    logger.info(f"NODE: {RECOMMEND_ACTIONS_NODE} (Project: {project_id}) - Calling agent {agent_hri}")
    try:
        input_payload = {
            "account_id": account_id,
            "dynamics_data": dynamics_data.model_dump(mode='json'),
            "external_data": external_data.model_dump(mode='json'),
            "account_analysis": account_analysis.model_dump(mode='json'),
            "account_briefing": account_briefing # Pass briefing if available
        }
        result_data = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        validated_output = ActionRecommenderOutput.model_validate(result_data)
        recommendations = validated_output.recommended_actions
        logger.info(f"Successfully generated {len(recommendations)} recommendations.")
        return {"recommended_actions": recommendations, "current_step": RECOMMEND_ACTIONS_NODE, "error_message": None}
    except (ValidationError, AgentProcessingError) as e:
        logger.error(f"NODE: {RECOMMEND_ACTIONS_NODE} - Error validating/processing response from {agent_hri}: {e}")
        # Allow pipeline to continue but with empty recommendations
        logger.warning(f"Proceeding without recommendations due to error: {e}")
        return {"recommended_actions": [], "current_step": RECOMMEND_ACTIONS_NODE, "error_message": None}
    except Exception as e:
        logger.exception(f"NODE: {RECOMMEND_ACTIONS_NODE} failed for project {project_id}: {e}")
        logger.warning(f"Proceeding without recommendations due to unexpected error: {e}")
        return {"recommended_actions": [], "current_step": RECOMMEND_ACTIONS_NODE, "error_message": None}

# --- ADDED: New node for executing actions ---
async def execute_recommended_actions(state: AccountProcessingState) -> Dict[str, Any]:
    """Node to filter recommendations and call execution agents."""
    try:
        config: DynamicsPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        account_id = state["account_id"]
        recommendations = state.get("recommended_actions") or []
        dynamics_data = state.get("dynamics_data")
        account_name = dynamics_data.account.name if dynamics_data and dynamics_data.account else "Unknown Account"
    except KeyError as e:
        return {"error_message": f"State missing key for action execution: {e}"}

    logger.info(f"NODE: {EXECUTE_ACTIONS_NODE} (Project: {project_id}) - Processing {len(recommendations)} recommendations for execution.")

    # Filter for high-priority actions (REQ-DYN-EXEC-003)
    high_priority_actions = [action for action in recommendations if action.priority == "High"]
    if not high_priority_actions:
        logger.info(f"No high-priority actions found for account {account_id}. Skipping execution.")
        return {"current_step": EXECUTE_ACTIONS_NODE, "error_message": None, "action_execution_results": {}}

    logger.info(f"Found {len(high_priority_actions)} high-priority actions to execute for account {account_id}.")

    execution_results: Dict[str, List[Dict[str, Any]]] = {
        "task_creation": [],
        "slack_notification": [],
        "teams_notification": []
    }

    # Get agent HRIs
    task_creator_hri = config.task_creator_agent.hri
    slack_notifier_hri = config.slack_notifier_agent.hri
    teams_notifier_hri = config.teams_notifier_agent.hri

    # --- Execute Actions (REQ-DYN-EXEC-004, 005, 006, 007) ---
    for i, action in enumerate(high_priority_actions):
        action_log_prefix = f"Action {i+1}/{len(high_priority_actions)} ('{action.action_description[:50]}...')"

        # 1. Create Dynamics Task
        try:
            task_input = {
                "account_id": account_id,
                "task_subject": action.action_description,
                "priority": action.priority,
                "related_record_id": action.related_record_id
            }
            logger.info(f"{action_log_prefix}: Calling task creator agent ({task_creator_hri}).")
            task_result_data = await a2a_wrapper.run_a2a_task(task_creator_hri, task_input)
            task_output = CreateTaskOutput.model_validate(task_result_data)
            task_result = task_output.model_dump()
            # Add task_subject to the result for better visibility in the summary
            task_result["task_subject"] = action.action_description
            execution_results["task_creation"].append(task_result)
            if task_output.success:
                logger.info(f"{action_log_prefix}: Task creation successful (ID: {task_output.created_task_id}).")
            else:
                logger.warning(f"{action_log_prefix}: Task creation failed: {task_output.message}")
        except (ValidationError, AgentProcessingError, Exception) as e:
            logger.error(f"{action_log_prefix}: Error calling task creator agent: {e}", exc_info=True)
            execution_results["task_creation"].append({"success": False, "message": f"Error calling agent: {e}"})

        # 2. Send Slack Notification
        try:
            slack_message = f"High Priority Action for {account_name}: {action.action_description}"
            # Target can be configured or hardcoded for PoC
            slack_target = "#dynamics-alerts"
            slack_input = {"target": slack_target, "message_text": slack_message}
            logger.info(f"{action_log_prefix}: Calling Slack notifier agent ({slack_notifier_hri}).")
            slack_result_data = await a2a_wrapper.run_a2a_task(slack_notifier_hri, slack_input)
            slack_output = SendNotificationOutput.model_validate(slack_result_data)
            slack_result = slack_output.model_dump()
            # Add the message and target for better visibility in summary
            slack_result["message_text"] = slack_message
            slack_result["target"] = slack_target
            execution_results["slack_notification"].append(slack_result)
            if slack_output.success:
                logger.info(f"{action_log_prefix}: Slack notification logged successfully.")
            else:
                logger.warning(f"{action_log_prefix}: Slack notification logging failed: {slack_output.message}")
        except (ValidationError, AgentProcessingError, Exception) as e:
            logger.error(f"{action_log_prefix}: Error calling Slack notifier agent: {e}", exc_info=True)
            execution_results["slack_notification"].append({"success": False, "message": f"Error calling agent: {e}"})

        # 3. Send Teams Notification
        try:
            teams_message = f"**High Priority Action** for Account **{account_name}**: {action.action_description}"
            # Target can be configured or hardcoded for PoC
            teams_target = "https://your-teams-webhook.example.com" # Placeholder
            teams_input = {"target": teams_target, "message_text": teams_message}
            logger.info(f"{action_log_prefix}: Calling Teams notifier agent ({teams_notifier_hri}).")
            teams_result_data = await a2a_wrapper.run_a2a_task(teams_notifier_hri, teams_input)
            teams_output = SendNotificationOutput.model_validate(teams_result_data)
            teams_result = teams_output.model_dump()
            # Add the message and target for better visibility in summary
            teams_result["message_text"] = teams_message
            teams_result["target"] = teams_target
            execution_results["teams_notification"].append(teams_result)
            if teams_output.success:
                logger.info(f"{action_log_prefix}: Teams notification logged successfully.")
            else:
                logger.warning(f"{action_log_prefix}: Teams notification logging failed: {teams_output.message}")
        except (ValidationError, AgentProcessingError, Exception) as e:
            logger.error(f"{action_log_prefix}: Error calling Teams notifier agent: {e}", exc_info=True)
            execution_results["teams_notification"].append({"success": False, "message": f"Error calling agent: {e}"})

    # Return success even if individual executions failed (REQ-DYN-EXEC-007)
    return {
        "action_execution_results": execution_results,
        "current_step": EXECUTE_ACTIONS_NODE,
        "error_message": None
    }
# --- END ADDED ---

async def generate_account_briefing(state: AccountProcessingState) -> Dict[str, Any]:
    """Node to call the Briefing Generator Agent."""
    try:
        config: DynamicsPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        dynamics_data = state.get("dynamics_data")
        external_data = state.get("external_data") # Should be ExternalDataPayload
        account_analysis = state.get("account_analysis")
        # --- MODIFIED: Include recommendations and execution results in briefing input ---
        recommendations = state.get("recommended_actions")
        execution_results = state.get("action_execution_results")
        # --- END MODIFIED ---
    except KeyError as e: return {"error_message": f"State missing key for briefing: {e}"}

    if not dynamics_data or not account_analysis: return {"error_message": "Cannot generate briefing: Dynamics data or analysis missing."}
    if not external_data: external_data = ExternalDataPayload() # Ensure default empty

    agent_hri = config.briefing_agent.hri
    logger.info(f"NODE: {GENERATE_BRIEFING_NODE} (Project: {project_id}) - Calling agent {agent_hri}")
    try:
        account_name = dynamics_data.account.name if dynamics_data.account else "Unknown"
        risk_level = account_analysis.risk_level if account_analysis else "Unknown"
        logger.info(f"Input summary for briefing - Account: {account_name}, Risk: {risk_level}")

        input_payload = {
            "dynamics_data": dynamics_data.model_dump(mode='json'),
            "external_data": external_data.model_dump(mode='json'),
            "account_analysis": account_analysis.model_dump(mode='json'),
            # --- ADDED: Pass recommendations and execution results ---
            # Note: The briefing agent's current prompt doesn't use these,
            # but we pass them for potential future enhancement.
            "recommendations": [rec.model_dump(mode='json') for rec in recommendations] if recommendations else [],
            "execution_results": execution_results if execution_results else {}
            # --- END ADDED ---
        }

        result_data = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        validated_output = BriefingGeneratorOutput.model_validate(result_data)
        briefing_text = validated_output.account_briefing
        logger.info(f"Successfully generated account briefing (length: {len(briefing_text)}).")
        logger.info(f"Briefing preview: {briefing_text[:100]}...")
        
        # --- ADDED: Check results and add to the output ---
        logger.info(f"EXECUTION RESULTS TYPE: {type(execution_results)}")
        logger.info(f"EXECUTION RESULTS KEYS: {list(execution_results.keys() if execution_results else [])}")
        for key, items in execution_results.items() if execution_results else {}:
            logger.info(f"Results for {key}: {len(items)} items")
            if items:
                logger.info(f"Sample item: {items[0]}")
        
        # --- Always add execution summary, even if results are empty ---
        # Construct a notification summary that will be VERY visible
        notification_summary = "\n\n" + "="*80 + "\n\n"
        notification_summary += "🚨 AUTOMATED ACTIONS EXECUTED 🚨\n" + "="*40 + "\n\n"
        
        # Format task creation results
        task_count = 0
        for item in execution_results.get("task_creation", []) if execution_results else []:
            if item.get("success", False):
                task_count += 1
        
        if task_count > 0:
            notification_summary += f"📝 TASKS CREATED IN DYNAMICS: {task_count}\n\n"
            for i, task in enumerate(execution_results.get("task_creation", []) if execution_results else []):
                if task.get("success", False):
                    task_id = task.get("created_task_id", "Unknown")
                    task_subject = task.get("task_subject", "[No subject]")
                    notification_summary += f"  ✓ Task #{i+1}: ID {task_id}\n"
                    notification_summary += f"      Subject: {task_subject[:60] + '...' if len(task_subject) > 60 else task_subject}\n\n"
        
        # Format notification results
        if execution_results:
            slack_count = sum(1 for item in execution_results.get("slack_notification", []) if item.get("success", False))
            teams_count = sum(1 for item in execution_results.get("teams_notification", []) if item.get("success", False))
        else:
            slack_count = teams_count = 0
        
        if slack_count > 0 or teams_count > 0:
            notification_summary += "🔔 NOTIFICATIONS SENT:\n\n"
            
            if slack_count > 0:
                notification_summary += f"  ✓ {slack_count} Slack notifications to #dynamics-alerts\n"
            
            if teams_count > 0:
                notification_summary += f"  ✓ {teams_count} Teams notifications\n"
        
        notification_summary += "\n" + "="*80 + "\n\n"
        
        # Always add the summary
        logger.info(f"ADDING NOTIFICATION SUMMARY: {len(notification_summary)} chars")
        logger.info(f"PREVIEW: {notification_summary[:200]}...")
        briefing_text = notification_summary + briefing_text
        
        return {"account_briefing": briefing_text, "current_step": GENERATE_BRIEFING_NODE, "error_message": None}
    except (ValidationError, AgentProcessingError) as e:
        logger.error(f"NODE: {GENERATE_BRIEFING_NODE} - Error validating/processing response from {agent_hri}: {e}")
        return {"error_message": f"Error generating briefing: {e}"}
    except Exception as e:
        logger.exception(f"NODE: {GENERATE_BRIEFING_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Unexpected error in {agent_hri}: {str(e)}"}

async def handle_pipeline_error(state: AccountProcessingState) -> Dict[str, Any]:
    """Node to handle pipeline errors."""
    error = state.get("error_message", "Unknown error")
    last_step = state.get("current_step", "Unknown step")
    project_id = state["project_id"]
    logger.error(f"DYNAMICS PIPELINE FAILED (Project: {project_id}) at step '{last_step}'. Error: {error}")
    # Ensure recommended_actions exists in the final error state if it was missing
    final_state_update = {"error_message": f"Pipeline failed at step: {last_step}. Reason: {error}"}
    if "recommended_actions" not in state:
        final_state_update["recommended_actions"] = []
    # --- ADDED: Ensure execution results exists in error state ---
    if "action_execution_results" not in state:
        final_state_update["action_execution_results"] = {}
    # --- END ADDED ---
    return final_state_update


logger.info("Dynamics pipeline node functions defined.")
