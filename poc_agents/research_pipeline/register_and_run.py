#!/usr/bin/env python
"""
Script to register agent cards and run the orchestrator.
"""

import os
import sys
import json
import logging
import subprocess
import time
import requests
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API key for registry
API_KEY = "avreg__BoAh2jnG9UnvUmtFAmOKenNuFvkb9LEPbLQIJ0gcr0"
REGISTRY_URL = "http://localhost:8000"

def check_registry_running():
    """Check if the registry is running."""
    logger.info(f"Checking if registry is running at {REGISTRY_URL}...")
    try:
        response = requests.head(REGISTRY_URL, timeout=5)
        if response.status_code < 500:  # Any response other than server error
            logger.info("Registry is running.")
            return True
        else:
            logger.error(f"Registry returned error: {response.status_code}")
            return False
    except requests.RequestException as e:
        logger.error(f"Registry is not running: {str(e)}")
        logger.info("Please start the registry with:")
        logger.info("uvicorn agentvault_registry.main:app --reload --port 8000 --host 0.0.0.0")
        return False

def register_agent_card(card_path):
    """Register an agent card with the registry."""
    logger.info(f"Registering agent card: {card_path}")
    try:
        # Read the card file
        with open(card_path, 'r') as f:
            card_data = json.load(f)
        
        # Extract the humanReadableId for logging
        hri = card_data.get('humanReadableId', 'unknown')
        
        # Register the card using the agentvault CLI
        cmd = [
            "agentvault_cli",
            "register",
            "--registry", REGISTRY_URL,
            "--api-key", API_KEY,
            "--card-file", str(card_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Successfully registered agent: {hri}")
            return True
        else:
            logger.error(f"Failed to register agent {hri}: {result.stderr}")
            # Check if it failed because the card was already registered
            if "already exists" in result.stderr:
                logger.info(f"Agent {hri} already registered.")
                return True
            return False
    
    except Exception as e:
        logger.exception(f"Error registering agent card {card_path}: {e}")
        return False

def register_all_agent_cards():
    """Register all agent cards in the agent_cards directory."""
    logger.info("Registering all agent cards...")
    
    base_dir = Path("agent_cards")
    if not base_dir.exists() or not base_dir.is_dir():
        logger.error(f"Agent cards directory not found: {base_dir}")
        return False
    
    success = True
    
    # Iterate through all subdirectories
    for agent_dir in base_dir.iterdir():
        if agent_dir.is_dir():
            card_path = agent_dir / "agent-card.json"
            if card_path.exists():
                if not register_agent_card(card_path):
                    success = False
            else:
                logger.warning(f"No agent-card.json found in {agent_dir}")
    
    return success

def run_orchestrator():
    """Run the orchestrator script."""
    logger.info("Running orchestrator...")
    try:
        result = subprocess.run(["python", "orchestrator.py"], check=True)
        logger.info("Orchestrator completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Orchestrator failed with error code {e.returncode}")
        return False
    except Exception as e:
        logger.exception(f"Error running orchestrator: {e}")
        return False

def main():
    """Main function."""
    logger.info("Starting setup and run process...")
    
    # Check if registry is running
    if not check_registry_running():
        logger.error("Registry is not running. Exiting.")
        sys.exit(1)
    
    # Register all agent cards
    if not register_all_agent_cards():
        logger.warning("Some agent cards failed to register. Continuing anyway...")
    
    # Run the orchestrator
    if not run_orchestrator():
        logger.error("Orchestrator failed.")
        sys.exit(1)
    
    logger.info("Process completed successfully.")

if __name__ == "__main__":
    main()
