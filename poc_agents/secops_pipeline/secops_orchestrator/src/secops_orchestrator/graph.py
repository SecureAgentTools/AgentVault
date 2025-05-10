import logging
from typing import Literal, Optional

from langgraph.graph import StateGraph, END # Import END

# Import node functions and constants (REQ-SECOPS-ORCH-1.5)
from .nodes import (
    start_pipeline,
    ingest_alert, # Assuming a dedicated node, might combine with start
    enrich_alert,
    investigate_alert,
    determine_response,
    execute_response,
    handle_error,
    # Node name constants
    START_NODE,
    INGEST_ALERT_NODE,
    ENRICH_ALERT_NODE,
    INVESTIGATE_ALERT_NODE,
    DETERMINE_RESPONSE_NODE,
    EXECUTE_RESPONSE_NODE,
    HANDLE_ERROR_NODE,
    # FINAL_NODE # Using LangGraph END directly
)
# Import the state definition (REQ-SECOPS-ORCH-1.5)
from .state_definition import SecopsPipelineState

logger = logging.getLogger(__name__)

# --- Graph Definition ---

# Conditional Edge Logic (REQ-SECOPS-ORCH-1.5)
def should_continue(state: SecopsPipelineState) -> Literal["continue", "handle_error"]:
    """Determines routing based on presence of error."""
    error = state.get('error_message')
    step = state.get('current_step', 'unknown')
    logger.debug(f"Routing check after step '{step}'. Error present: {bool(error)}")
    # If error_message is set, route to the error handler
    if error:
        return "handle_error"
    # Otherwise, continue to the next logical step
    return "continue"

# Conditional Edge Logic (REQ-SECOPS-ORCH-1.5)
def route_after_determination(state: SecopsPipelineState) -> Literal["execute_response", END, "handle_error"]:
    """Routes based on whether a response action was determined."""
    if state.get("error_message"):
        return "handle_error" # Prioritize error handling

    response_action = state.get("determined_response_action") # Check state field set by determine_response
    logger.debug(f"Routing check after determination. Action: '{response_action}'")

    # Actions requiring the Response Agent
    if response_action in ["CREATE_TICKET", "BLOCK_IP", "RUN_SCRIPT"]: # Example actions
        logger.info(f"Routing to execute response action: {response_action}")
        return "execute_response"
    # Actions handled internally or no action needed
    elif response_action in ["CLOSE_FALSE_POSITIVE", "MANUAL_REVIEW", None]:
        logger.info(f"No external execution needed for action '{response_action}'. Ending pipeline.")
        return END # Use LangGraph's END sentinel
    else:
         logger.warning(f"Unknown determined response action '{response_action}'. Routing to error handler.")
         # Set error message in state for clarity if needed (mutate state carefully in routers)
         # state["error_message"] = f"Unknown action determined: {response_action}" # Be cautious modifying state here
         return "handle_error" # Route unknown actions to error handler

# Graph Creation Function (REQ-SECOPS-ORCH-1.5)
def create_secops_graph() -> StateGraph:
    """Creates the LangGraph StateGraph for the SecOps pipeline."""
    logger.info("Creating the SecOps pipeline graph workflow...")

    workflow = StateGraph(SecopsPipelineState)

    # --- Add Nodes ---
    # Using constants imported from nodes.py
    workflow.add_node(START_NODE, start_pipeline)
    workflow.add_node(INGEST_ALERT_NODE, ingest_alert)
    workflow.add_node(ENRICH_ALERT_NODE, enrich_alert)
    workflow.add_node(INVESTIGATE_ALERT_NODE, investigate_alert)
    workflow.add_node(DETERMINE_RESPONSE_NODE, determine_response)
    workflow.add_node(EXECUTE_RESPONSE_NODE, execute_response)
    workflow.add_node(HANDLE_ERROR_NODE, handle_error)
    logger.debug("Nodes added to the graph.")

    # --- Define Graph Flow (Edges) ---
    logger.debug("Defining SecOps graph edges...")
    # Set the entry point
    workflow.set_entry_point(START_NODE)
    logger.debug(f"Entry point set to: {START_NODE}")

    # Define transitions using conditional edges based on 'should_continue'
    workflow.add_conditional_edges(
        START_NODE,
        should_continue,
        {"continue": INGEST_ALERT_NODE, "handle_error": HANDLE_ERROR_NODE}
    )
    logger.debug(f"Edges added from {START_NODE}")

    workflow.add_conditional_edges(
        INGEST_ALERT_NODE,
        should_continue,
        {"continue": ENRICH_ALERT_NODE, "handle_error": HANDLE_ERROR_NODE}
    )
    logger.debug(f"Edges added from {INGEST_ALERT_NODE}")

    workflow.add_conditional_edges(
        ENRICH_ALERT_NODE,
        should_continue,
        {"continue": INVESTIGATE_ALERT_NODE, "handle_error": HANDLE_ERROR_NODE}
    )
    logger.debug(f"Edges added from {ENRICH_ALERT_NODE}")

    workflow.add_conditional_edges(
        INVESTIGATE_ALERT_NODE,
        should_continue,
        {"continue": DETERMINE_RESPONSE_NODE, "handle_error": HANDLE_ERROR_NODE}
    )
    logger.debug(f"Edges added from {INVESTIGATE_ALERT_NODE}")

    # Use the specific routing logic after response determination
    workflow.add_conditional_edges(
        DETERMINE_RESPONSE_NODE,
        route_after_determination, # Use the custom router
        {
            "execute_response": EXECUTE_RESPONSE_NODE,
            END: END, # Route directly to END if no action needed
            "handle_error": HANDLE_ERROR_NODE
        }
    )
    logger.debug(f"Conditional edges added from {DETERMINE_RESPONSE_NODE}")

    # After executing a response, always end (or go to error handler)
    workflow.add_conditional_edges(
        EXECUTE_RESPONSE_NODE,
        should_continue, # Still check for errors during execution node
        {"continue": END, "handle_error": HANDLE_ERROR_NODE}
    )
    logger.debug(f"Edges added from {EXECUTE_RESPONSE_NODE}")

    # Error handler node always terminates the graph
    workflow.add_edge(HANDLE_ERROR_NODE, END)
    logger.debug(f"Edge added from {HANDLE_ERROR_NODE} to END")

    logger.info("Compiling the SecOps pipeline graph...")
    # Compile the graph
    app = workflow.compile(checkpointer=None) # No checkpointer for this skeleton
    logger.info("SecOps pipeline graph compilation complete.")
    return app
