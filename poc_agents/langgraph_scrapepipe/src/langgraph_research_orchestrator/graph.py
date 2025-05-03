import logging
import functools
from typing import Dict, Literal, Optional

from langgraph.graph import StateGraph, END

# Import the state definition and node functions
from .state import ResearchState
from .nodes import (
    run_topic_research,
    run_content_crawler,
    run_information_extraction,
    run_fact_verification,
    run_content_synthesis,
    run_editor,
    run_visualization,
    handle_pipeline_error,
    # Import node name constants
    TOPIC_RESEARCH_NODE, CONTENT_CRAWLER_NODE, INFO_EXTRACTION_NODE,
    FACT_VERIFICATION_NODE, CONTENT_SYNTHESIS_NODE, EDITOR_NODE, VISUALIZATION_NODE,
    ERROR_HANDLER_NODE
)
from .a2a_client_wrapper import A2AClientWrapper
from .config.pipeline_config import ResearchPipelineConfig


logger = logging.getLogger(__name__)

def should_continue(state: ResearchState) -> Literal["continue", "handle_error"]:
    """Determines whether to continue the pipeline or handle an error."""
    if state.get("error_message"):
        logger.warning(f"Error detected in state after step '{state.get('current_step', 'unknown')}': {state['error_message']}")
        return "handle_error"
    else:
        return "continue"


def create_research_graph(a2a_wrapper: A2AClientWrapper, config: Optional[ResearchPipelineConfig] = None) -> StateGraph:
    """
    Creates and configures the LangGraph StateGraph for the research pipeline.
    
    Args:
        a2a_wrapper: The A2A client wrapper for agent communication
        config: Optional pipeline configuration (will use default if None)
        
    Returns:
        The compiled StateGraph application
    """
    logger.info("Creating the research pipeline graph with error handling...")
    
    # Use default config if none provided
    if config is None:
        from .config import get_pipeline_config
        config = get_pipeline_config()
        logger.info("No configuration provided to graph, using default configuration")

    workflow = StateGraph(ResearchState)

    # Add nodes, binding the wrapper and config using partial
    workflow.add_node(
        TOPIC_RESEARCH_NODE, 
        functools.partial(run_topic_research, a2a_wrapper=a2a_wrapper, config=config)
    )
    workflow.add_node(
        CONTENT_CRAWLER_NODE, 
        functools.partial(run_content_crawler, a2a_wrapper=a2a_wrapper, config=config)
    )
    workflow.add_node(
        INFO_EXTRACTION_NODE, 
        functools.partial(run_information_extraction, a2a_wrapper=a2a_wrapper, config=config)
    )
    workflow.add_node(
        FACT_VERIFICATION_NODE, 
        functools.partial(run_fact_verification, a2a_wrapper=a2a_wrapper, config=config)
    )
    workflow.add_node(
        CONTENT_SYNTHESIS_NODE, 
        functools.partial(run_content_synthesis, a2a_wrapper=a2a_wrapper, config=config)
    )
    workflow.add_node(
        EDITOR_NODE, 
        functools.partial(run_editor, a2a_wrapper=a2a_wrapper, config=config)
    )
    workflow.add_node(
        VISUALIZATION_NODE, 
        functools.partial(run_visualization, a2a_wrapper=a2a_wrapper, config=config)
    )
    # Error handler node doesn't need the a2a_wrapper
    workflow.add_node(
        ERROR_HANDLER_NODE, 
        functools.partial(handle_pipeline_error, config=config)
    )

    # Define the graph flow with conditional edges
    logger.debug("Defining graph edges with error handling...")
    workflow.set_entry_point(TOPIC_RESEARCH_NODE)

    # Add conditional edge after each main step
    workflow.add_conditional_edges(
        TOPIC_RESEARCH_NODE,
        should_continue,
        {
            "continue": CONTENT_CRAWLER_NODE,
            "handle_error": ERROR_HANDLER_NODE
        }
    )
    workflow.add_conditional_edges(
        CONTENT_CRAWLER_NODE,
        should_continue,
        {
            "continue": INFO_EXTRACTION_NODE,
            "handle_error": ERROR_HANDLER_NODE
        }
    )
    workflow.add_conditional_edges(
        INFO_EXTRACTION_NODE,
        should_continue,
        {
            "continue": FACT_VERIFICATION_NODE,
            "handle_error": ERROR_HANDLER_NODE
        }
    )
    workflow.add_conditional_edges(
        FACT_VERIFICATION_NODE,
        should_continue,
        {
            "continue": CONTENT_SYNTHESIS_NODE,
            "handle_error": ERROR_HANDLER_NODE
        }
    )
    workflow.add_conditional_edges(
        CONTENT_SYNTHESIS_NODE,
        should_continue,
        {
            "continue": EDITOR_NODE,
            "handle_error": ERROR_HANDLER_NODE
        }
    )
    workflow.add_conditional_edges(
        EDITOR_NODE,
        should_continue,
        {
            "continue": VISUALIZATION_NODE,
            "handle_error": ERROR_HANDLER_NODE
        }
    )
    # Final visualization step also needs error check before ending
    workflow.add_conditional_edges(
        VISUALIZATION_NODE,
        should_continue,
        {
            "continue": END, # Go to END if successful
            "handle_error": ERROR_HANDLER_NODE
        }
    )

    # The error handler node always goes to END
    workflow.add_edge(ERROR_HANDLER_NODE, END)

    # Compile the graph
    logger.info("Compiling the research pipeline graph...")
    app = workflow.compile()
    logger.info("Graph compilation complete.")
    return app
