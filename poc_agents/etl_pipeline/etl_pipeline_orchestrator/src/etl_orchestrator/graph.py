import logging
from typing import Dict, Literal

from langgraph.graph import StateGraph, END

# Import node functions and constants from this package
from etl_orchestrator.nodes import (
    start_etl_pipeline, extract_data, transform_data, validate_data, load_data, handle_pipeline_error,
    START_PIPELINE_NODE, EXTRACT_DATA_NODE, TRANSFORM_DATA_NODE, VALIDATE_DATA_NODE, LOAD_DATA_NODE, ERROR_HANDLER_NODE
)
# Import the state definition
from etl_orchestrator.state_definition import EtlProcessingState

logger = logging.getLogger(__name__)

# --- Graph Definition (REQ-ETL-ORCH-005) ---

def should_continue(state: EtlProcessingState) -> Literal["continue", "handle_error"]:
    """Determines whether to continue the pipeline or handle an error."""
    if state.get("error_message"):
        logger.error(f"Error detected after step '{state.get('current_step', 'unknown')}': {state['error_message']}")
        return "handle_error"
    else:
        logger.debug(f"Step '{state.get('current_step', 'unknown')}' completed successfully. Continuing.")
        return "continue"

def create_etl_graph() -> StateGraph:
    """
    Creates and configures the LangGraph StateGraph for the ETL pipeline.
    """
    logger.info("Creating the ETL pipeline graph...")

    workflow = StateGraph(EtlProcessingState)

    # --- Add Nodes (REQ-ETL-ORCH-004) ---
    workflow.add_node(START_PIPELINE_NODE, start_etl_pipeline)
    workflow.add_node(EXTRACT_DATA_NODE, extract_data)
    workflow.add_node(TRANSFORM_DATA_NODE, transform_data)
    workflow.add_node(VALIDATE_DATA_NODE, validate_data)
    workflow.add_node(LOAD_DATA_NODE, load_data)
    workflow.add_node(ERROR_HANDLER_NODE, handle_pipeline_error)

    # --- Define Graph Flow (REQ-ETL-ORCH-005) ---
    logger.debug("Defining ETL graph edges...")
    workflow.set_entry_point(START_PIPELINE_NODE)

    # Sequential flow with error checking after each agent call
    workflow.add_conditional_edges(START_PIPELINE_NODE, should_continue, {"continue": EXTRACT_DATA_NODE, "handle_error": ERROR_HANDLER_NODE})
    workflow.add_conditional_edges(EXTRACT_DATA_NODE, should_continue, {"continue": TRANSFORM_DATA_NODE, "handle_error": ERROR_HANDLER_NODE})
    workflow.add_conditional_edges(TRANSFORM_DATA_NODE, should_continue, {"continue": VALIDATE_DATA_NODE, "handle_error": ERROR_HANDLER_NODE})
    workflow.add_conditional_edges(VALIDATE_DATA_NODE, should_continue, {"continue": LOAD_DATA_NODE, "handle_error": ERROR_HANDLER_NODE})
    workflow.add_conditional_edges(LOAD_DATA_NODE, should_continue, {"continue": END, "handle_error": ERROR_HANDLER_NODE})

    # Error handler always goes to END
    workflow.add_edge(ERROR_HANDLER_NODE, END)

    logger.info("Compiling the ETL pipeline graph...")
    # No checkpointer needed for this simple ETL PoC unless state inspection is desired
    app = workflow.compile()
    logger.info("ETL pipeline graph compilation complete.")
    return app
