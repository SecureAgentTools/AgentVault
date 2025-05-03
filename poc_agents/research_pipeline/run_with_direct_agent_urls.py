#!/usr/bin/env python
"""
Alternative orchestrator runner that bypasses the registry lookup
and uses direct agent URLs from local agent card files.
"""

import asyncio
import logging
import json
import os
import sys
from pathlib import Path
import urllib.parse
from typing import Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the orchestrator (gets from parent dir)
try:
    from orchestrator import ResearchPipelineOrchestrator, AgentCard
except ImportError:
    logger.error("Failed to import ResearchPipelineOrchestrator. Make sure you're running from the correct directory.")
    sys.exit(1)

class DirectAgentOrchestrator(ResearchPipelineOrchestrator):
    """
    Modified orchestrator that loads agent cards directly from files
    instead of looking them up in the registry.
    """
    
    async def initialize(self):
        """
        Override the initialize method to load agent cards directly from files.
        """
        logger.info("Initializing orchestrator: Loading agent cards directly from files...")
        self.agent_cards = {}
        discovered_count = 0
        
        base_dir = Path("agent_cards")
        if not base_dir.exists() or not base_dir.is_dir():
            raise ValueError(f"Agent cards directory not found: {base_dir}")
        
        # For each agent HRI, try to load its card from the corresponding file
        for agent_hri in self.AGENT_HRIS:
            logger.info(f"Loading agent card for: {agent_hri}")
            
            # Extract agent type from HRI (e.g., "topic-research" from "local-poc/topic-research")
            parts = agent_hri.split('/')
            if len(parts) != 2:
                logger.error(f"Invalid HRI format: {agent_hri}. Expected format: 'namespace/name'")
                continue
            
            agent_type = parts[1]
            agent_dir = base_dir / agent_type.replace('-', '_')
            card_path = agent_dir / "agent-card.json"
            
            if not card_path.exists():
                logger.error(f"Agent card file not found: {card_path}")
                continue
            
            try:
                with open(card_path, 'r') as f:
                    card_data = json.load(f)
                
                # Validate the HRI matches
                card_hri = card_data.get("humanReadableId")
                if card_hri != agent_hri:
                    logger.warning(f"HRI mismatch: expected '{agent_hri}', got '{card_hri}' in {card_path}")
                
                # Create an AgentCard object
                agent_card = AgentCard.model_validate(card_data)
                self.agent_cards[agent_hri] = agent_card
                logger.info(f"Successfully loaded card for agent: {agent_hri} at {agent_card.url}")
                discovered_count += 1
                
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in agent card file: {card_path}")
                continue
            except Exception as e:
                logger.error(f"Error loading agent card from {card_path}: {e}")
                continue
        
        if len(self.agent_cards) != len(self.AGENT_HRIS):
            missing = set(self.AGENT_HRIS) - set(self.agent_cards.keys())
            logger.error(f"Failed to load all required agents. Missing: {missing}")
            raise ValueError(f"Could not load all pipeline agents. Missing: {missing}")
        
        logger.info(f"Orchestrator initialization complete. Loaded {discovered_count} required agents.")

async def main():
    """Run the research pipeline using the direct agent orchestrator."""
    logger.info("Starting research pipeline with direct agent loading...")
    
    try:
        # Create and initialize the orchestrator
        orchestrator = DirectAgentOrchestrator(registry_url="http://localhost:8000")
        
        # Set the AGENT_HRIS attribute (needed for our modified class)
        orchestrator.AGENT_HRIS = [
            "local-poc/topic-research",
            "local-poc/content-crawler",
            "local-poc/information-extraction",
            "local-poc/fact-verification",
            "local-poc/content-synthesis",
            "local-poc/editor",
            "local-poc/visualization"
        ]
        
        # Initialize (loading agent cards from files)
        await orchestrator.initialize()
        
        # Run the pipeline
        topic_to_research = "Impact of AI on Healthcare"
        pipeline_config = {"depth": "comprehensive", "focus_areas": ["ethics", "diagnosis"]}
        final_result = await orchestrator.run_pipeline(topic_to_research, pipeline_config)
        
        # Print the result
        print("\n--- Pipeline Final Result ---")
        print(json.dumps(final_result, indent=2))
        
    except Exception as e:
        logger.exception(f"Error running pipeline: {e}")
        print("\n--- Pipeline Error ---")
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
