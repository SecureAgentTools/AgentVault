import logging
from typing import Dict, Literal, Optional, List, Any, TypedDict # Import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver # Example checkpoint saver

# --- MODIFIED: Use absolute imports from package root ---
# Import node functions using absolute paths
from ecommerce_orchestrator.nodes import (
    start_pipeline,
    fetch_user_profile,
    fetch_product_catalog,
    fetch_trends,
    aggregate_fetch_results,
    generate_recommendations,
    handle_pipeline_error,
    # Import node name constants
    START_PIPELINE_NODE, FETCH_USER_PROFILE_NODE, FETCH_PRODUCT_CATALOG_NODE,
    FETCH_TRENDS_NODE, AGGREGATE_FETCH_NODE, GENERATE_RECOMMENDATIONS_NODE,
    ERROR_HANDLER_NODE
)
# Import types needed for RecommendationState definition using absolute paths
from ecommerce_orchestrator.models import UserProfile, ProductDetail, TrendingData, ProductRecommendation
from ecommerce_orchestrator.config import EcommercePipelineConfig
from ecommerce_orchestrator.a2a_client_wrapper import A2AClientWrapper
# Import the state definition using absolute path
from ecommerce_orchestrator.state_definition import RecommendationState
# --- END MODIFIED ---

logger = logging.getLogger(__name__)

# --- Graph Definition ---

def should_continue(state: RecommendationState) -> Literal["continue", "handle_error"]:
    """Determines whether to continue the pipeline or handle an error."""
    if state.get("error_message"):
        # Special case: if this is just a product details error but we still have user profile and trending data,
        # we can continue the pipeline
        error_msg = state.get("error_message", "")
        if "Product details artifact path not found" in error_msg and state.get("user_profile") and state.get("trending_data"):
            logger.warning("Product details missing but user profile and trending data available - continuing pipeline")
            return "continue"
            
        logger.warning(f"Error detected in state after step '{state.get('current_step', 'unknown')}': {state['error_message']}")
        return "handle_error"
    else:
        logger.debug(f"Step '{state.get('current_step', 'unknown')}' completed successfully. Continuing.")
        return "continue"

def create_ecommerce_graph() -> StateGraph:
    """
    Creates and configures the LangGraph StateGraph for the e-commerce recommendation pipeline.
    Nodes now expect config and wrapper to be present in the state dictionary.

    Returns:
        The compiled StateGraph application.
    """
    logger.info("Creating the e-commerce recommendation pipeline graph...")

    # StateGraph uses the imported RecommendationState
    workflow = StateGraph(RecommendationState)

    # --- Add Nodes ---
    workflow.add_node(START_PIPELINE_NODE, start_pipeline)
    workflow.add_node(FETCH_USER_PROFILE_NODE, fetch_user_profile)
    workflow.add_node(FETCH_PRODUCT_CATALOG_NODE, fetch_product_catalog)
    workflow.add_node(FETCH_TRENDS_NODE, fetch_trends)
    workflow.add_node(AGGREGATE_FETCH_NODE, aggregate_fetch_results)
    workflow.add_node(GENERATE_RECOMMENDATIONS_NODE, generate_recommendations)
    workflow.add_node(ERROR_HANDLER_NODE, handle_pipeline_error)

    # --- Define Graph Flow ---
    logger.debug("Defining graph edges...")
    workflow.set_entry_point(START_PIPELINE_NODE)

    workflow.add_edge(START_PIPELINE_NODE, FETCH_USER_PROFILE_NODE)
    workflow.add_edge(FETCH_USER_PROFILE_NODE, FETCH_PRODUCT_CATALOG_NODE)
    workflow.add_edge(FETCH_PRODUCT_CATALOG_NODE, FETCH_TRENDS_NODE)
    workflow.add_edge(FETCH_TRENDS_NODE, AGGREGATE_FETCH_NODE)

    workflow.add_conditional_edges(
        AGGREGATE_FETCH_NODE,
        should_continue,
        {"continue": GENERATE_RECOMMENDATIONS_NODE, "handle_error": ERROR_HANDLER_NODE}
    )
    workflow.add_conditional_edges(
        GENERATE_RECOMMENDATIONS_NODE,
        should_continue,
        {"continue": END, "handle_error": ERROR_HANDLER_NODE}
    )
    workflow.add_edge(ERROR_HANDLER_NODE, END)

    logger.info("Compiling the e-commerce pipeline graph...")
    app = workflow.compile()
    logger.info("E-commerce graph compilation complete.")
    return app
