import asyncio
import json
import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import subprocess to run the CLI commands
import subprocess

def register_agent_card(card_path, api_key):
    """Register a single agent card using the agentvault CLI."""
    try:
        # Read the card file
        with open(card_path, 'r') as f:
            card_data = json.load(f)
        
        # Extract the humanReadableId from the card
        hri = card_data.get('humanReadableId')
        if not hri:
            logger.error(f"Missing humanReadableId in card: {card_path}")
            return False
            
        logger.info(f"Registering agent card {hri} from {card_path}")
        
        # Create a temporary file with the card data for CLI to read
        temp_file = f"temp_{hri.replace('/', '_')}.json"
        with open(temp_file, 'w') as f:
            json.dump(card_data, f)
        
        # Use subprocess to call the agentvault CLI
        # Example: agentvault register --registry http://localhost:8000 --api-key KEY --card-file temp_file.json
        cmd = [
            "agentvault_cli", 
            "register", 
            "--registry", "http://localhost:8000",
            "--api-key", api_key,
            "--card-file", temp_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Cleanup temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        # Check result
        if result.returncode == 0:
            logger.info(f"Successfully registered agent {hri}")
            return True
        else:
            logger.error(f"Failed to register agent {hri}: {result.stderr}")
            return False
            
    except Exception as e:
        logger.exception(f"Error registering agent card {card_path}: {e}")
        return False

def main():
    """Main function to register all agent cards."""
    # Check if API key was provided
    if len(sys.argv) < 2:
        print("Usage: python register_cards.py API_KEY")
        return
        
    api_key = sys.argv[1]
    logger.info("Starting agent card registration process...")
    
    # Base directory for agent cards
    cards_dir = os.path.join("agent_cards")
    
    # Check if directory exists
    if not os.path.isdir(cards_dir):
        logger.error(f"Agent cards directory not found: {cards_dir}")
        return
        
    # Get all subdirectories (agent types)
    agent_types = [d for d in os.listdir(cards_dir) if os.path.isdir(os.path.join(cards_dir, d))]
    
    success_count = 0
    failure_count = 0
    
    for agent_type in agent_types:
        card_path = os.path.join(cards_dir, agent_type, "agent-card.json")
        if os.path.exists(card_path):
            if register_agent_card(card_path, api_key):
                success_count += 1
            else:
                failure_count += 1
        else:
            logger.warning(f"No agent-card.json found for {agent_type}")
            failure_count += 1
    
    logger.info(f"Registration complete. Success: {success_count}, Failure: {failure_count}")

if __name__ == "__main__":
    main()
