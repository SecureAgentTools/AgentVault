import asyncio
import logging
import uuid
import json
import sys
import os
import argparse
from typing import Dict, Any, List, Optional

# Import the compiled graph application and state definition
try:
    from .graph import create_research_graph
    from .state import ResearchState
    from .config import settings
    from .config import get_pipeline_config, ResearchDepth
    from .a2a_client_wrapper import A2AClientWrapper, AgentProcessingError, ConfigurationError
except ImportError:
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    from langgraph_research_orchestrator.graph import create_research_graph
    from langgraph_research_orchestrator.state import ResearchState
    from langgraph_research_orchestrator.config import settings
    from langgraph_research_orchestrator.config import get_pipeline_config, ResearchDepth
    from langgraph_research_orchestrator.a2a_client_wrapper import A2AClientWrapper, AgentProcessingError, ConfigurationError


# Setup logger for this script
logger = logging.getLogger(__name__)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run the LangGraph Research Pipeline with a specified topic.'
    )
    parser.add_argument(
        '--topic', 
        type=str, 
        required=True,
        help='The research topic to investigate'
    )
    parser.add_argument(
        '--focus-areas', 
        type=str, 
        nargs='+', 
        help='Optional list of focus areas for the research'
    )
    parser.add_argument(
        '--depth', 
        type=str, 
        choices=['brief', 'standard', 'comprehensive'], 
        default='standard',
        help='Research depth (brief, standard, comprehensive)'
    )
    parser.add_argument(
        '--log-level', 
        type=str, 
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
        default='INFO',
        help='Logging level'
    )
    parser.add_argument(
        '--project-id', 
        type=str, 
        help='Optional custom project ID (default: auto-generated)'
    )
    parser.add_argument(
        '--config', 
        type=str, 
        help='Path to a custom pipeline configuration JSON file'
    )
    
    return parser.parse_args()

async def run_pipeline(
    topic: str, 
    depth: str = "standard", 
    focus_areas: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    config_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run the research pipeline with the specified parameters.
    
    Args:
        topic: The research topic to investigate
        depth: Research depth (brief, standard, comprehensive)
        focus_areas: Optional list of focus areas
        project_id: Optional custom project ID
        config_path: Optional path to custom configuration file
        
    Returns:
        The final state dictionary from the pipeline
    """
    logger.info(f"--- Starting LangGraph Research Pipeline Run for '{topic}' ---")
    
    # Load pipeline configuration
    pipeline_config = get_pipeline_config(config_path)
    logger.info(f"Loaded pipeline configuration with scraper.max_total_urls={pipeline_config.scraper.max_total_urls}")
    
    if not project_id:
        project_id = f"proj_{uuid.uuid4().hex[:8]}"
        
    if not focus_areas:
        focus_areas = []

    a2a_wrapper_instance = None
    try:
        # Instantiate and Initialize A2A Wrapper
        a2a_wrapper_instance = A2AClientWrapper()
        await a2a_wrapper_instance.initialize()
        logger.info("A2A Client Wrapper initialized successfully.")
    except ConfigurationError as e:
        logger.error(f"Configuration error initializing A2A Wrapper: {e}. Cannot proceed.")
        return {"error_message": f"Configuration error: {e}"}
    except Exception as e:
        logger.exception("Failed to initialize A2A Client Wrapper.")
        return {"error_message": f"Failed to initialize: {e}"}

    # 1. Create the compiled graph application
    try:
        # Pass the loaded configuration to the graph creation function
        app = create_research_graph(a2a_wrapper_instance, pipeline_config)
        logger.info("Research graph compiled successfully.")
    except Exception as e:
        logger.exception("Failed to create or compile the research graph.")
        if a2a_wrapper_instance: 
            await a2a_wrapper_instance.close()
        return {"error_message": f"Graph compilation failed: {e}"}

    # 2. Define Initial Input
    initial_input: ResearchState = {
        "initial_topic": topic,
        "initial_config": {
            "depth": depth,
            "focus_areas": focus_areas,
            "pipeline_config_path": config_path  # Store the config path for reference
        },
        "project_id": project_id,
        "current_step": None,
        "error_message": None,
        "research_plan": None,
        "search_queries": None,
        "local_artifact_references": {},
        "final_article_local_path": None,
        "final_visualization_local_path": None,
    }
    logger.info(f"Initial input prepared for Project ID: {project_id}, Topic: '{topic}'")
    logger.debug(f"Initial State Input: {initial_input}")

    # 3. Invoke the Graph
    final_state = None
    try:
        logger.info("Invoking the research graph asynchronously...")
        # Use the recursion_limit from configuration
        recursion_limit = pipeline_config.orchestration.recursion_limit
        final_state = await app.ainvoke(initial_input, {"recursion_limit": recursion_limit})
        logger.info("Graph invocation finished.")

    except Exception as e:
        logger.exception("An error occurred during graph execution.")
        final_state = {"error_message": f"Graph execution error: {e}"}
    finally:
        # Ensure wrapper client is closed
        if a2a_wrapper_instance:
            logger.info("Closing A2A Client Wrapper...")
            await a2a_wrapper_instance.close()
            logger.info("A2A Client Wrapper closed.")

    # 4. Print Final State
    logger.info("--- Pipeline Run Finished ---")
    if final_state:
        error = final_state.get("error_message")
        if error:
            logger.error(f"Pipeline failed: {error}")
        else:
            logger.info(f"Pipeline completed successfully for topic '{topic}'")
            
        # Print summary of results
        final_article = final_state.get("final_article_local_path")
        if final_article:
            logger.info(f"Final article saved to: {final_article}")
            
        final_viz = final_state.get("final_visualization_local_path")
        if final_viz:
            logger.info(f"Visualization data saved to: {final_viz}")
            
        # Print all artifact paths
        artifacts = final_state.get("local_artifact_references", {})
        if artifacts:
            logger.info("All generated artifacts:")
            for artifact_type, path in artifacts.items():
                logger.info(f"  - {artifact_type}: {path}")
    else:
        logger.warning("Graph execution did not complete or failed to return a final state.")
        
    return final_state or {"error_message": "No final state returned"}

async def main():
    """Parse arguments and run the pipeline."""
    args = parse_args()
    
    # Configure logging based on the provided log level
    log_level = args.log_level
    logging.basicConfig(
        level=getattr(logging, log_level), 
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
        force=True
    )
    
    # Run the pipeline
    final_state = await run_pipeline(
        topic=args.topic,
        depth=args.depth,
        focus_areas=args.focus_areas,
        project_id=args.project_id,
        config_path=args.config
    )
    
    # Print final state as JSON
    try:
        print(json.dumps(final_state, indent=2, default=str))
    except Exception as print_err:
        logger.error(f"Could not serialize final state for printing: {print_err}")
        print(final_state)
    
    # Return non-zero exit code if there was an error
    if final_state.get("error_message"):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
