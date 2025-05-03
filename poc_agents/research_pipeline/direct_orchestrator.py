#!/usr/bin/env python
"""
Modified orchestrator that bypasses registry lookup completely
and loads agent cards directly from local files.
"""

import asyncio
import json
import logging
import uuid
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the original orchestrator to extend it
try:
    from orchestrator import ResearchPipelineOrchestrator, AgentCard, Message, TextPart, ConfigurationError, AgentVaultError
    
    # Define the missing AgentProcessingError exception
    class AgentProcessingError(Exception):
        """Raised when an error occurs during agent task processing."""
        pass
    
    # Monkey patch the exception into the orchestrator module
    import sys
    sys.modules['orchestrator'].AgentProcessingError = AgentProcessingError
    
except ImportError:
    logger.error("Failed to import the original orchestrator module.")
    sys.exit(1)

class DirectResearchPipelineOrchestrator(ResearchPipelineOrchestrator):
    """
    Extends the original orchestrator to load agent cards directly from local files
    instead of looking them up from the registry.
    """
    
    async def initialize(self):
        """
        Override to load agent cards from local files instead of from the registry.
        """
        logger.info("Initializing DirectResearchPipelineOrchestrator: Loading agent cards from local files...")
        self.agent_cards = {}
        discovered_count = 0
        
        # Check if the agent_cards directory exists
        base_dir = Path("agent_cards")
        if not base_dir.exists() or not base_dir.is_dir():
            logger.error(f"Agent cards directory not found: {base_dir}")
            raise ConfigurationError(f"Agent cards directory not found: {base_dir}")
        
        # Load each agent card from its local file
        from orchestrator import AGENT_HRIS
        for agent_hri in AGENT_HRIS:
            logger.info(f"Loading agent card for: {agent_hri}")
            
            # Extract agent type from the HRI (local-poc/topic-research → topic_research)
            parts = agent_hri.split('/')
            if len(parts) != 2:
                logger.error(f"Invalid HRI format: {agent_hri}. Expected 'namespace/name'")
                continue
                
            agent_type = parts[1].replace('-', '_')
            agent_dir = base_dir / agent_type
            card_path = agent_dir / "agent-card.json"
            
            if not card_path.exists():
                logger.error(f"Agent card file not found: {card_path}")
                continue
            
            try:
                # Load and parse the agent card JSON
                with open(card_path, 'r') as f:
                    card_data = json.load(f)
                
                # Create an AgentCard object
                agent_card = AgentCard.model_validate(card_data)
                self.agent_cards[agent_hri] = agent_card
                logger.info(f"Successfully loaded card for agent: {agent_hri} at {agent_card.url}")
                discovered_count += 1
                
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in agent card file {card_path}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error loading agent card from {card_path}: {e}")
                continue
        
        # Ensure all required agents were loaded
        if len(self.agent_cards) != len(AGENT_HRIS):
            missing = set(AGENT_HRIS) - set(self.agent_cards.keys())
            logger.error(f"Failed to load all required agent cards. Missing: {missing}")
            raise ConfigurationError(f"Could not load all pipeline agents. Missing: {missing}")
        
        logger.info(f"DirectResearchPipelineOrchestrator initialization complete. Loaded {discovered_count} required agents.")

async def main():
    """Run the research pipeline with direct agent loading."""
    logger.info("Starting research pipeline with direct agent loading...")
    
    orchestrator = DirectResearchPipelineOrchestrator(registry_url="http://localhost:8000")
    final_result = {}
    
    try:
        # Initialize the orchestrator (loads agent cards from files)
        await orchestrator.initialize()
        
        # Run the pipeline
        topic_to_research = "Impact of AI on Healthcare"
        pipeline_config = {"depth": "comprehensive", "focus_areas": ["ethics", "diagnosis"]}
        
        logger.info(f"Running pipeline for topic: {topic_to_research}")
        final_result = await orchestrator.run_pipeline(topic_to_research, pipeline_config)
        
    except ConfigurationError as e:
        print(f"\n--- Orchestrator Configuration Error ---")
        print(f"Error: {e}")
        final_result = {"status": "FAILED", "error": f"ConfigurationError: {e}"}
    except Exception as e:
        print(f"\n--- An Unexpected Error Occurred ---")
        print(f"Error: {e}")
        import traceback
        print(traceback.format_exc())
        final_result = {"status": "FAILED", "error": f"UnexpectedError: {e}"}
    
    print("\n--- Pipeline Final Result ---")
    print(json.dumps(final_result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
