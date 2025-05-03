import logging
from typing import Dict, Literal, Optional, List, Any

from langgraph.graph import StateGraph, END
# Removed memory saver import as it's not needed

# Import node functions and constants from this package
from support_orchestrator.nodes import (
    start_ticket_processing,
    analyze_ticket,
    fetch_kb_articles,
    fetch_customer_history,
    aggregate_response_context,
    suggest_response,
    handle_pipeline_error,
    # Import node name constants
    START_PIPELINE_NODE, ANALYZE_TICKET_NODE, FETCH_KB_NODE, FETCH_HISTORY_NODE,
    AGGREGATE_CONTEXT_NODE, SUGGEST_RESPONSE_NODE, ERROR_HANDLER_NODE
)
# Import the state definition
from support_orchestrator.state_definition import TicketProcessingState

logger = logging.getLogger(__name__)

# --- Graph Definition (REQ-SUP-ORCH-005) ---

def should_continue(state: TicketProcessingState) -> Literal["continue", "handle_error"]:
    """Determines whether to continue the pipeline or handle an error."""
    if state.get("error_message"):
        # Check if the error is critical (e.g., missing ticket analysis)
        if "Critical failure: Ticket analysis missing" in state["error_message"]:
             logger.error(f"CRITICAL ERROR detected in state after step '{state.get('current_step', 'unknown')}': {state['error_message']}")
             return "handle_error"
        # Allow continuation if only non-critical data (like KB/History) failed, but log it
        logger.warning(f"Non-critical error detected after step '{state.get('current_step', 'unknown')}': {state['error_message']}. Attempting to continue.")
        # Clear the error message *if* we decide to continue despite it
        # state["error_message"] = None # Optional: Clear non-critical error to proceed
        # For PoC, let's handle *any* error for simplicity unless explicitly allowed above
        return "handle_error" # Default to handling any reported error
    else:
        logger.debug(f"Step '{state.get('current_step', 'unknown')}' completed successfully. Continuing.")
        return "continue"

def create_support_graph() -> StateGraph:
    """
    Creates and configures the LangGraph StateGraph for the support ticket pipeline.

    Returns:
        The compiled StateGraph application.
    """
    logger.info("Creating the support ticket processing pipeline graph...")

    # StateGraph uses the imported TicketProcessingState
    workflow = StateGraph(TicketProcessingState)

    # --- Add Nodes (REQ-SUP-ORCH-004) ---
    workflow.add_node(START_PIPELINE_NODE, start_ticket_processing)
    workflow.add_node(ANALYZE_TICKET_NODE, analyze_ticket)
    workflow.add_node(FETCH_KB_NODE, fetch_kb_articles)
    workflow.add_node(FETCH_HISTORY_NODE, fetch_customer_history)
    workflow.add_node(AGGREGATE_CONTEXT_NODE, aggregate_response_context)
    workflow.add_node(SUGGEST_RESPONSE_NODE, suggest_response)
    workflow.add_node(ERROR_HANDLER_NODE, handle_pipeline_error)

    # --- Define Graph Flow (REQ-SUP-ORCH-005) ---
    logger.debug("Defining graph edges...")
    workflow.set_entry_point(START_PIPELINE_NODE)

    workflow.add_edge(START_PIPELINE_NODE, ANALYZE_TICKET_NODE)
    workflow.add_edge(ANALYZE_TICKET_NODE, FETCH_KB_NODE) # Sequential for PoC
    workflow.add_edge(FETCH_KB_NODE, FETCH_HISTORY_NODE)
    workflow.add_edge(FETCH_HISTORY_NODE, AGGREGATE_CONTEXT_NODE)

    # Conditional edge after aggregation
    workflow.add_conditional_edges(
        AGGREGATE_CONTEXT_NODE,
        should_continue,
        {
            "continue": SUGGEST_RESPONSE_NODE,
            "handle_error": ERROR_HANDLER_NODE
        }
    )

    # Conditional edge after response suggestion
    workflow.add_conditional_edges(
        SUGGEST_RESPONSE_NODE,
        should_continue,
        {
            "continue": END, # End successfully if response generated without error
            "handle_error": ERROR_HANDLER_NODE
        }
    )

    # Error handler always goes to END
    workflow.add_edge(ERROR_HANDLER_NODE, END)

    logger.info("Compiling the support pipeline graph...")
    # Compile without a checkpointer for now, similar to the ecommerce pipeline
    app = workflow.compile()
    logger.info("Support pipeline graph compilation complete.")
    return app
