import logging
from typing import Literal

from langgraph.graph import StateGraph, END

# Import node functions and constants
from dynamics_orchestrator.nodes import (
    start_account_processing, fetch_dynamics_data, fetch_external_data,
    analyze_account_health, recommend_actions,
    # --- ADDED: Import new node function and constant ---
    execute_recommended_actions,
    # --- END ADDED ---
    generate_account_briefing,
    handle_pipeline_error,
    START_NODE, FETCH_DYNAMICS_NODE, FETCH_EXTERNAL_NODE, ANALYZE_HEALTH_NODE,
    RECOMMEND_ACTIONS_NODE,
    # --- ADDED: Import new node constant ---
    EXECUTE_ACTIONS_NODE,
    # --- END ADDED ---
    GENERATE_BRIEFING_NODE, ERROR_HANDLER_NODE
)
# Import the state definition
from dynamics_orchestrator.state_definition import AccountProcessingState

logger = logging.getLogger(__name__)

# --- Graph Definition (REQ-DYN-ORCH-005) ---

def should_continue(state: AccountProcessingState) -> Literal["continue", "handle_error"]:
    """Determines whether to continue the pipeline or handle an error."""
    step = state.get('current_step', 'unknown')
    error = state.get('error_message')
    logger.debug(f"Checking continuation after step: {step}, Error: {error}")

    if error:
        logger.error(f"Error detected after step '{step}': {error}")
        return "handle_error"
    else:
        logger.debug(f"Step '{step}' completed successfully. Continuing.")
        return "continue"

def create_dynamics_graph() -> StateGraph:
    """Creates the LangGraph StateGraph for the Dynamics pipeline."""
    logger.info("Creating the Dynamics Account Processing pipeline graph...")

    workflow = StateGraph(AccountProcessingState)

    # --- Add Nodes (REQ-DYN-ORCH-004 & REQ-DYN-EXEC-001) ---
    workflow.add_node(START_NODE, start_account_processing)
    workflow.add_node(FETCH_DYNAMICS_NODE, fetch_dynamics_data)
    workflow.add_node(FETCH_EXTERNAL_NODE, fetch_external_data)
    workflow.add_node(ANALYZE_HEALTH_NODE, analyze_account_health)
    workflow.add_node(RECOMMEND_ACTIONS_NODE, recommend_actions)
    # --- ADDED: Add new execution node ---
    workflow.add_node(EXECUTE_ACTIONS_NODE, execute_recommended_actions)
    # --- END ADDED ---
    workflow.add_node(GENERATE_BRIEFING_NODE, generate_account_briefing)
    workflow.add_node(ERROR_HANDLER_NODE, handle_pipeline_error)

    # --- Define Graph Flow (REQ-DYN-ORCH-005 & REQ-DYN-EXEC-002) ---
    logger.debug("Defining Dynamics graph edges...")
    workflow.set_entry_point(START_NODE)

    # Sequential flow with error checking
    workflow.add_conditional_edges(START_NODE, should_continue, {
        "continue": FETCH_DYNAMICS_NODE, "handle_error": ERROR_HANDLER_NODE
    })
    workflow.add_conditional_edges(FETCH_DYNAMICS_NODE, should_continue, {
        "continue": FETCH_EXTERNAL_NODE, "handle_error": ERROR_HANDLER_NODE
    })
    workflow.add_conditional_edges(FETCH_EXTERNAL_NODE, should_continue, {
        "continue": ANALYZE_HEALTH_NODE, "handle_error": ERROR_HANDLER_NODE
    })
    workflow.add_conditional_edges(ANALYZE_HEALTH_NODE, should_continue, {
        "continue": RECOMMEND_ACTIONS_NODE, "handle_error": ERROR_HANDLER_NODE
    })
    # --- MODIFIED: Insert execution node ---
    workflow.add_conditional_edges(RECOMMEND_ACTIONS_NODE, should_continue, {
        "continue": EXECUTE_ACTIONS_NODE, "handle_error": ERROR_HANDLER_NODE # Go to executor
    })
    workflow.add_conditional_edges(EXECUTE_ACTIONS_NODE, should_continue, {
        "continue": GENERATE_BRIEFING_NODE, "handle_error": ERROR_HANDLER_NODE # Go to briefer (executor handles its own errors softly)
    })
    # --- END MODIFIED ---
    workflow.add_conditional_edges(GENERATE_BRIEFING_NODE, should_continue, {
        "continue": END, "handle_error": ERROR_HANDLER_NODE
    })

    # Error handler always goes to end
    workflow.add_edge(ERROR_HANDLER_NODE, END)

    logger.info("Compiling the Dynamics pipeline graph...")
    # Disable in-memory checkpointer to keep state transitions atomic
    app = workflow.compile(checkpointer=None)
    logger.info("Dynamics pipeline graph compilation complete.")
    return app
