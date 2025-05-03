#!/usr/bin/env python
"""
Research Pipeline Runner

A convenience script to run the research pipeline with configuration.

Usage:
  python run_pipeline.py --topic "Climate Change Adaptation" --config my_config.json --depth comprehensive

This script is a wrapper around the main module entry point that makes it easier
to run the pipeline from the project root directory.
"""

import asyncio
import sys
import os
import argparse
from pathlib import Path

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

async def main():
    """Parse arguments and run the pipeline with the correct module structure."""
    args = parse_args()
    
    # Import here to ensure the module is found
    try:
        from src.langgraph_research_orchestrator.run import run_pipeline
    except ImportError:
        print("Error: Could not import the research pipeline module.")
        print("Make sure you're running this script from the langgraph_scrapepipe directory.")
        sys.exit(1)
    
    # Run the pipeline
    final_state = await run_pipeline(
        topic=args.topic,
        depth=args.depth,
        focus_areas=args.focus_areas,
        project_id=args.project_id,
        config_path=args.config
    )
    
    # Print a simplified summary
    print("\n=== Research Pipeline Execution Summary ===")
    
    error = final_state.get("error_message")
    if error:
        print(f"Status: FAILED")
        print(f"Error: {error}")
    else:
        print(f"Status: COMPLETED")
        
    # Show artifacts
    final_article = final_state.get("final_article_local_path")
    if final_article:
        print(f"Final article: {final_article}")
        
    final_viz = final_state.get("final_visualization_local_path")
    if final_viz:
        print(f"Visualization data: {final_viz}")
    
    # Show project ID for reference
    print(f"Project ID: {final_state.get('project_id', 'unknown')}")
    
    # Return code
    if error:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)
