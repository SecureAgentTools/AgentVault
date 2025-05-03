#!/usr/bin/env python
"""
Comprehensive test and fix script for the research pipeline orchestrator.
This script tries multiple approaches to fix the agent discovery issue.
"""

import asyncio
import logging
import json
import os
import sys
import subprocess
import httpx
import urllib.parse
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Registry URL
REGISTRY_URL = "http://localhost:8000"

# Agent HRIs
AGENT_HRIS = [
    "local-poc/topic-research",
    "local-poc/content-crawler",
    "local-poc/information-extraction",
    "local-poc/fact-verification",
    "local-poc/content-synthesis",
    "local-poc/editor",
    "local-poc/visualization"
]

async def check_registry_alive():
    """Check if the registry is running and responding."""
    logger.info(f"Checking if registry is alive at {REGISTRY_URL}...")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{REGISTRY_URL}/api/v1/agent-cards?limit=1")
            if response.status_code < 300:
                logger.info("✅ Registry is alive and responding.")
                return True
            else:
                logger.error(f"❌ Registry returned error status: {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"❌ Registry is not responding: {e}")
        return False

async def test_by_hri_query_endpoint():
    """Test the /by-hri query parameter endpoint."""
    logger.info("Testing /by-hri query parameter endpoint...")
    
    success_count = 0
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for hri in AGENT_HRIS:
            url = f"{REGISTRY_URL}/api/v1/agent-cards/by-hri?hri={hri}"
            logger.info(f"Testing URL: {url}")
            
            try:
                response = await client.get(url)
                
                if response.status_code == 404:
                    logger.error(f"❌ Agent card for '{hri}' not found via query parameter endpoint.")
                    continue
                    
                if response.status_code < 300:
                    logger.info(f"✅ Successfully retrieved agent card for '{hri}' via query parameter endpoint.")
                    success_count += 1
                else:
                    logger.error(f"❌ Error response ({response.status_code}) for '{hri}' via query parameter endpoint.")
            except Exception as e:
                logger.error(f"❌ Error testing query parameter endpoint for '{hri}': {e}")
    
    logger.info(f"Query parameter endpoint test results: {success_count}/{len(AGENT_HRIS)} agent cards retrieved.")
    return success_count == len(AGENT_HRIS)

async def test_id_path_endpoint():
    """Test the /id/{hri} path parameter endpoint."""
    logger.info("Testing /id/{hri} path parameter endpoint...")
    
    success_count = 0
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for hri in AGENT_HRIS:
            encoded_hri = urllib.parse.quote(hri, safe='')
            url = f"{REGISTRY_URL}/api/v1/agent-cards/id/{encoded_hri}"
            logger.info(f"Testing URL: {url}")
            
            try:
                response = await client.get(url)
                
                if response.status_code == 404:
                    logger.error(f"❌ Agent card for '{hri}' not found via path parameter endpoint.")
                    continue
                    
                if response.status_code < 300:
                    logger.info(f"✅ Successfully retrieved agent card for '{hri}' via path parameter endpoint.")
                    success_count += 1
                else:
                    logger.error(f"❌ Error response ({response.status_code}) for '{hri}' via path parameter endpoint.")
            except Exception as e:
                logger.error(f"❌ Error testing path parameter endpoint for '{hri}': {e}")
    
    logger.info(f"Path parameter endpoint test results: {success_count}/{len(AGENT_HRIS)} agent cards retrieved.")
    return success_count == len(AGENT_HRIS)

def modify_orchestrator_to_use_query_endpoint():
    """Modify the orchestrator.py file to use the query parameter endpoint."""
    logger.info("Modifying orchestrator.py to use query parameter endpoint...")
    
    try:
        # Read the original file
        with open("orchestrator.py", "r") as f:
            content = f.read()
        
        # Make backup of original file
        with open("orchestrator.py.bak", "w") as f:
            f.write(content)
        
        # Replace the lookup URL construction
        modified_content = content.replace(
            "encoded_hri = urllib.parse.quote(agent_hri, safe='') # Encode '/' -> %2F\n                lookup_url = f\"{self.registry_url.rstrip('/')}/api/v1/agent-cards/id/{encoded_hri}\"",
            "encoded_hri = urllib.parse.quote(agent_hri, safe='') # Encode '/' -> %2F\n                lookup_url = f\"{self.registry_url.rstrip('/')}/api/v1/agent-cards/by-hri?hri={agent_hri}\""
        )
        
        # Replace error message
        modified_content = modified_content.replace(
            "logger.error(f\"Agent card for HRI '{agent_hri}' (encoded: {encoded_hri}) not found in registry at {lookup_url}. Is the HRI correct and registered?\")",
            "logger.error(f\"Agent card for HRI '{agent_hri}' not found in registry at {lookup_url}. Is the HRI correct and registered?\")"
        )
        
        # Write the modified file
        with open("orchestrator.py", "w") as f:
            f.write(modified_content)
        
        logger.info("✅ Successfully modified orchestrator.py")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to modify orchestrator.py: {e}")
        return False

async def test_orchestrator_initialization():
    """Test the orchestrator initialization."""
    logger.info("Testing orchestrator initialization...")
    
    try:
        # Import the orchestrator
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from orchestrator import ResearchPipelineOrchestrator
        
        # Create and initialize the orchestrator
        orchestrator = ResearchPipelineOrchestrator(registry_url=REGISTRY_URL)
        
        try:
            await orchestrator.initialize()
            logger.info("✅ Orchestrator initialization successful!")
            return True
        except Exception as e:
            logger.error(f"❌ Orchestrator initialization failed: {e}")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to import orchestrator: {e}")
        return False

def create_direct_agent_script():
    """Create a script that loads agent cards directly from files."""
    logger.info("Creating script to load agent cards directly...")
    
    try:
        script_content = """#!/usr/bin/env python
\"\"\"
Modified orchestrator that loads agent cards directly from files.
\"\"\"

import asyncio
import sys
import json
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import from the original orchestrator
try:
    from orchestrator import ResearchPipelineOrchestrator, AgentCard, ConfigurationError
except ImportError:
    logger.error("Failed to import ResearchPipelineOrchestrator. Make sure you're running from the correct directory.")
    sys.exit(1)

class DirectResearchPipelineOrchestrator(ResearchPipelineOrchestrator):
    \"\"\"
    Modified version of the orchestrator that loads agent cards directly from files.
    \"\"\"
    
    async def initialize(self):
        \"\"\"
        Load agent cards directly from local files instead of from the registry.
        \"\"\"
        logger.info("Initializing orchestrator: Loading agent cards directly from files...")
        self.agent_cards = {}
        
        # Base directory for agent cards
        base_dir = Path("agent_cards")
        if not base_dir.exists() or not base_dir.is_dir():
            raise ConfigurationError(f"Agent cards directory not found: {base_dir}")
        
        # For each agent HRI in AGENT_HRIS, load the corresponding file
        for agent_hri in AGENT_HRIS:
            logger.info(f"Loading agent card for: {agent_hri}")
            
            # Extract agent type from HRI (e.g., "topic-research" from "local-poc/topic-research")
            agent_type = agent_hri.split('/')[-1]
            agent_dir = base_dir / agent_type.replace('-', '_')
            card_path = agent_dir / "agent-card.json"
            
            if not card_path.exists():
                logger.error(f"Agent card file not found: {card_path}")
                continue
            
            try:
                # Load the card data from file
                with open(card_path, 'r') as f:
                    card_data = json.load(f)
                
                # Convert to AgentCard object
                agent_card = AgentCard.model_validate(card_data)
                self.agent_cards[agent_hri] = agent_card
                logger.info(f"Successfully loaded card for agent: {agent_hri} at {agent_card.url}")
            except Exception as e:
                logger.error(f"Error loading agent card from {card_path}: {e}")
        
        # Check if all required agents were loaded
        if len(self.agent_cards) != len(AGENT_HRIS):
            missing = set(AGENT_HRIS) - set(self.agent_cards.keys())
            logger.error(f"Failed to load all required agents. Missing: {missing}")
            raise ConfigurationError(f"Could not load all pipeline agents. Missing: {missing}")
        
        logger.info(f"Orchestrator initialization complete. Loaded {len(self.agent_cards)} agent cards.")

async def main():
    \"\"\"Run the pipeline with direct agent loading.\"\"\"
    orchestrator = DirectResearchPipelineOrchestrator(registry_url="http://localhost:8000")
    
    try:
        await orchestrator.initialize()
        
        topic_to_research = "Impact of AI on Healthcare"
        pipeline_config = {"depth": "comprehensive", "focus_areas": ["ethics", "diagnosis"]}
        final_result = await orchestrator.run_pipeline(topic_to_research, pipeline_config)
        
        print("\\n--- Pipeline Final Result ---")
        print(json.dumps(final_result, indent=2, ensure_ascii=False))
    except ConfigurationError as e:
        print(f"\\n--- Orchestrator Configuration Error ---")
        print(f"Error: {e}")
        final_result = {"status": "FAILED", "error": f"ConfigurationError: {e}"}
    except Exception as e:
        print(f"\\n--- An Unexpected Error Occurred ---")
        print(f"Error: {e}")
        final_result = {"status": "FAILED", "error": f"UnexpectedError: {e}"}
    
    print("\\n--- Pipeline Final Result ---")
    print(json.dumps(final_result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
"""
        
        with open("direct_agent_orchestrator.py", "w") as f:
            f.write(script_content)
        
        logger.info("✅ Successfully created direct_agent_orchestrator.py")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create direct_agent_orchestrator.py: {e}")
        return False

async def main():
    """Main function to run comprehensive fixes."""
    logger.info("Starting comprehensive fix process...")
    
    # Step 1: Check if registry is alive
    registry_alive = await check_registry_alive()
    if not registry_alive:
        logger.error("Registry is not responding. Please make sure it's running.")
        logger.info("Try running: uvicorn agentvault_registry.main:app --reload --port 8000 --host 0.0.0.0")
        return
    
    # Step 2: Test both endpoints
    query_endpoint_works = await test_by_hri_query_endpoint()
    path_endpoint_works = await test_id_path_endpoint()
    
    if query_endpoint_works:
        logger.info("✅ Query parameter endpoint works! Modifying orchestrator to use it...")
        modify_orchestrator_to_use_query_endpoint()
    elif path_endpoint_works:
        logger.info("✅ Path parameter endpoint works! The orchestrator should already be using it.")
    else:
        logger.warning("❌ Neither endpoint works directly. Creating a script to use local agent cards...")
        create_direct_agent_script()
        
        logger.info("To run the pipeline with direct agent loading, use:")
        logger.info("python direct_agent_orchestrator.py")
        return
    
    # Step 3: Test orchestrator initialization
    init_works = await test_orchestrator_initialization()
    
    if init_works:
        logger.info("✅ Orchestrator initialization works! You can now run:")
        logger.info("python orchestrator.py")
    else:
        logger.warning("❌ Orchestrator initialization still fails. Creating a fallback solution...")
        create_direct_agent_script()
        
        logger.info("To run the pipeline with direct agent loading, use:")
        logger.info("python direct_agent_orchestrator.py")

if __name__ == "__main__":
    asyncio.run(main())
