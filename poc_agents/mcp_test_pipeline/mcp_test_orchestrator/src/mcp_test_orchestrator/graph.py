import logging
from typing import Literal, Optional

from langgraph.graph import StateGraph, END

# Import node functions and constants
from .nodes import (
    start_mcp_test, read_code_file_via_proxy, execute_python_code_via_proxy,
    handle_mcp_test_error,
    START_NODE, READ_FILE_NODE, EXECUTE_CODE_NODE, ERROR_HANDLER_NODE
    # WRITE_RESULT_NODE can be added later if needed
)
# Import the state definition
from .state_definition import McpTestState

logger = logging.getLogger(__name__)

# --- Graph Definition ---

def should_continue(state: McpTestState) -> Literal["continue", "handle_error"]:
    """Determines whether to continue the pipeline or handle an error."""
    step = state.get('current_step', 'unknown')
    error = state.get('error_message')
    logger.debug(f"Checking continuation after step: {step}, Error: {error}")
    return "handle_error" if error else "continue"

def route_after_start(state: McpTestState) -> Literal["read_file", "execute_code", "handle_error"]:
    """Routes based on whether input file path is provided."""
    if state.get("error_message"): return "handle_error"
    if state.get("input_file_path"):
        logger.debug("Routing to read file node.")
        return "read_file"
    elif state.get("input_python_code"):
         logger.debug("Routing directly to execute code node (no file path).")
         return "execute_code"
    else:
         # This case should be caught by start node validation, but handle defensively
         logger.error("Routing error: No input file path or direct code provided.")
         # Update state directly here is tricky in router, better to let next node handle?
         # For now, route to error handler.
         return "handle_error"


def create_mcp_test_graph() -> StateGraph:
    """Creates the LangGraph StateGraph for the MCP Test pipeline."""
    logger.info("Creating the MCP Test pipeline graph...")

    workflow = StateGraph(McpTestState)

    # --- Add Nodes ---
    workflow.add_node(START_NODE, start_mcp_test)
    workflow.add_node(READ_FILE_NODE, read_code_file_via_proxy)
    workflow.add_node(EXECUTE_CODE_NODE, execute_python_code_via_proxy)
    # workflow.add_node(WRITE_RESULT_NODE, write_result_file_via_proxy) # Add later if needed
    workflow.add_node(ERROR_HANDLER_NODE, handle_mcp_test_error)

    # --- Define Graph Flow ---
    logger.debug("Defining MCP Test graph edges...")
    workflow.set_entry_point(START_NODE)

    # Route from start based on input
    workflow.add_conditional_edges(
        START_NODE,
        route_after_start,
        {
            "read_file": READ_FILE_NODE,
            "execute_code": EXECUTE_CODE_NODE,
            "handle_error": ERROR_HANDLER_NODE
        }
    )

    # After reading file, execute code
    workflow.add_conditional_edges(
        READ_FILE_NODE,
        should_continue,
        {
            "continue": EXECUTE_CODE_NODE,
            "handle_error": ERROR_HANDLER_NODE
        }
    )

    # After executing code, end the pipeline (or write result later)
    workflow.add_conditional_edges(
        EXECUTE_CODE_NODE,
        should_continue,
        {
            "continue": END, # End after execution for now
            # "continue": WRITE_RESULT_NODE, # Future: Write result
            "handle_error": ERROR_HANDLER_NODE
        }
    )

    # Error handler always goes to end
    workflow.add_edge(ERROR_HANDLER_NODE, END)

    logger.info("Compiling the MCP Test pipeline graph...")
    app = workflow.compile(checkpointer=None)
    logger.info("MCP Test pipeline graph compilation complete.")
    return app
