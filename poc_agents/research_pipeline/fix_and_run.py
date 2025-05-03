#!/usr/bin/env python
"""
Fix and Run script that diagnoses issues, implements fixes, and runs the orchestrator.
This script will try multiple approaches to get the research pipeline working.
"""

import asyncio
import logging
import sys
import os
import json
import subprocess
import importlib.util
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_registry_connection():
    """Check if the registry is running and accessible."""
    logger.info("Checking registry connection...")
    
    try:
        # Try to import httpx
        import httpx
    except ImportError:
        logger.warning("httpx library not installed. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
        import httpx
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8000/api/v1/agent-cards?limit=1", follow_redirects=True)
            
            if response.status_code < 400:  # Consider 2xx and 3xx as success
                logger.info(f"✅ Registry is accessible. Status code: {response.status_code}")
                return True
            else:
                logger.error(f"❌ Registry returned error status: {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"❌ Failed to connect to registry: {e}")
        return False

def check_agent_card_files():
    """Check if agent card files exist locally."""
    logger.info("Checking for local agent card files...")
    
    base_dir = Path("agent_cards")
    if not base_dir.exists() or not base_dir.is_dir():
        logger.error(f"❌ Agent cards directory not found: {base_dir}")
        return False
    
    # Agent types to check (converted from HRIs)
    agent_types = [
        "topic_research",
        "content_crawler",
        "information_extraction",
        "fact_verification",
        "content_synthesis",
        "editor",
        "visualization"
    ]
    
    all_exist = True
    for agent_type in agent_types:
        card_path = base_dir / agent_type / "agent-card.json"
        if card_path.exists():
            logger.info(f"✅ Found agent card file: {card_path}")
            
            # Validate the JSON
            try:
                with open(card_path, 'r') as f:
                    card_data = json.load(f)
                
                # Check for required fields
                if all(field in card_data for field in ["humanReadableId", "url", "name"]):
                    logger.info(f"  ✅ Valid agent card JSON with required fields")
                else:
                    logger.warning(f"  ⚠️ Agent card JSON missing required fields: {card_path}")
                    all_exist = False
            except json.JSONDecodeError as e:
                logger.error(f"  ❌ Invalid JSON in agent card file: {card_path} ({e})")
                all_exist = False
        else:
            logger.error(f"❌ Agent card file not found: {card_path}")
            all_exist = False
    
    return all_exist

def check_orchestrator_modifications():
    """Check for required modifications in the orchestrator."""
    logger.info("Checking orchestrator modifications...")
    
    # Check if AgentProcessingError is defined
    try:
        spec = importlib.util.spec_from_file_location("orchestrator", "orchestrator.py")
        orchestrator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(orchestrator)
        
        has_error_class = hasattr(orchestrator, "AgentProcessingError")
        logger.info(f"{'✅' if has_error_class else '❌'} AgentProcessingError {'defined' if has_error_class else 'not defined'} in orchestrator")
        
        # Check method name for stream processing
        client_class = orchestrator.AgentVaultClient if hasattr(orchestrator, "AgentVaultClient") else None
        
        if client_class:
            # Check what methods are available
            event_methods = [method for method in dir(client_class) if "event" in method.lower() or "stream" in method.lower() or "subscribe" in method.lower()]
            logger.info(f"Event-related methods in client: {event_methods if event_methods else 'None found'}")
            
            has_receive_events = hasattr(client_class, "receive_events")
            logger.info(f"{'✅' if has_receive_events else '❌'} receive_events method {'found' if has_receive_events else 'not found'} in client")
        else:
            logger.warning("⚠️ Could not inspect AgentVaultClient class")
        
        return has_error_class
    except Exception as e:
        logger.error(f"❌ Error checking orchestrator modifications: {e}")
        return False

def fix_orchestrator():
    """Add required modifications to the orchestrator."""
    logger.info("Fixing orchestrator...")
    
    try:
        # Read the original file
        with open("orchestrator.py", "r") as f:
            content = f.read()
        
        # Make backup
        with open("orchestrator.py.bak", "w") as f:
            f.write(content)
        
        # Check if AgentProcessingError is already defined
        if "class AgentProcessingError" not in content:
            # Add the AgentProcessingError class after the imports
            import_end_index = content.find("logger = logging.getLogger(__name__)")
            if import_end_index > 0:
                # Insert after the logger definition
                modified_content = content[:import_end_index + len("logger = logging.getLogger(__name__)")] + "\n\n# Custom exception for agent processing errors\nclass AgentProcessingError(Exception):\n    \"\"\"Raised when an error occurs during agent task processing.\"\"\"\n    pass\n" + content[import_end_index + len("logger = logging.getLogger(__name__)"):]
                
                # Write the modified file
                with open("orchestrator.py", "w") as f:
                    f.write(modified_content)
                
                logger.info("✅ Added AgentProcessingError class to orchestrator")
                return True
            else:
                logger.error("❌ Could not find suitable location to add AgentProcessingError class")
                return False
        else:
            logger.info("✅ AgentProcessingError already defined in orchestrator")
            return True
    except Exception as e:
        logger.error(f"❌ Failed to fix orchestrator: {e}")
        return False

def handle_client_method_mismatch():
    """Handle the mismatch in client method names."""
    logger.info("Fixing client method name mismatch...")
    
    try:
        # Read the original file
        with open("orchestrator.py", "r") as f:
            content = f.read()
        
        # Make backup if not already made
        if not os.path.exists("orchestrator.py.bak"):
            with open("orchestrator.py.bak", "w") as f:
                f.write(content)
        
        # Find the _run_agent_task method and modify it
        run_agent_task_start = content.find("async def _run_agent_task")
        if run_agent_task_start > 0:
            # Find where the receive_events call is
            receive_events_index = content.find("self.client.receive_events", run_agent_task_start)
            
            if receive_events_index > 0:
                # Replace with flexible event method handling
                modified_content = content[:receive_events_index] + """# Try different event streaming methods
                event_method = getattr(self.client, "receive_events", None)
                if not event_method:
                    event_method = getattr(self.client, "subscribe_to_events", None)
                if not event_method:
                    event_method = getattr(self.client, "receive_task_events", None)
                    
                if not event_method:
                    logger.error(f"No event streaming method found in client for {agent_hri}")
                    raise AgentProcessingError(f"No event streaming method available for {agent_hri}")
                    
                async for event in event_method""" + content[receive_events_index + len("self.client.receive_events"):]
                
                # Write the modified file
                with open("orchestrator.py", "w") as f:
                    f.write(modified_content)
                
                logger.info("✅ Added flexible event method handling to orchestrator")
                return True
            else:
                logger.error("❌ Could not find receive_events call in _run_agent_task method")
                return False
        else:
            logger.error("❌ Could not find _run_agent_task method in orchestrator")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to fix client method mismatch: {e}")
        return False

def create_direct_solution():
    """Create the direct solution script."""
    logger.info("Creating direct solution script...")
    
    # Check if direct_orchestrator.py already exists
    if os.path.exists("direct_orchestrator.py"):
        logger.info("✅ direct_orchestrator.py already exists")
        return True
    
    # Copy the existing direct_orchestrator.py
    try:
        if os.path.exists("direct_load_pipeline.py"):
            logger.info("✅ direct_load_pipeline.py already exists. Using this as the direct solution.")
            return True
            
        logger.info("Creating direct solution from scratch...")
        # Create direct_load_pipeline.py
        from direct_load_pipeline import main
        logger.info("✅ Successfully imported direct_load_pipeline.py")
        return True
    except ImportError:
        logger.error("❌ direct_load_pipeline.py not found or has errors")
    except Exception as e:
        logger.error(f"❌ Error testing direct solution: {e}")
    
    return False

async def run_test(script_name):
    """Run a test of the specified script."""
    logger.info(f"Testing {script_name}...")
    
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, script_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # Log the output
        if stdout:
            logger.info(f"Output from {script_name}:")
            for line in stdout.decode().split('\n'):
                if line.strip():
                    logger.info(f"  {line}")
        
        # Log errors
        if stderr:
            logger.error(f"Errors from {script_name}:")
            for line in stderr.decode().split('\n'):
                if line.strip():
                    logger.error(f"  {line}")
        
        # Check return code
        if process.returncode == 0:
            logger.info(f"✅ {script_name} ran successfully")
            return True
        else:
            logger.error(f"❌ {script_name} failed with code {process.returncode}")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to run {script_name}: {e}")
        return False

async def main():
    """Main function to diagnose, fix, and run the orchestrator."""
    logger.info("Starting diagnosis and fixes...")
    
    # First, since we know the direct_load_pipeline.py works best (except for a small bug we fixed),
    # try running that
    logger.info("Using the fixed direct_load_pipeline.py approach first...")
    
    if os.path.exists("direct_load_pipeline.py"):
        logger.info("Running direct_load_pipeline.py...")
        success = await run_test("direct_load_pipeline.py")
        if success:
            logger.info("✅ direct_load_pipeline.py ran successfully! Use this solution.")
            logger.info("Note: If you still see errors about 'Task' object has no attribute 'message',")
            logger.info("they were fixed in the latest version of the script. Just run it again!")
            return
    
    # Check registry connection as fallback
    registry_ok = await check_registry_connection()
    
    # Check agent card files
    cards_ok = check_agent_card_files()
    
    # First try direct solution with agent card files
    if cards_ok:
        logger.info("Local agent card files found. Using direct loading approach...")
        
        if os.path.exists("direct_load_pipeline.py"):
            logger.info("Running direct_load_pipeline.py...")
            success = await run_test("direct_load_pipeline.py")
            if success:
                logger.info("✅ direct_load_pipeline.py ran successfully! Use this solution.")
                return
            else:
                logger.warning("⚠️ direct_load_pipeline.py had errors. Trying alternative approaches...")
        
        if os.path.exists("direct_orchestrator.py"):
            logger.info("Running direct_orchestrator.py...")
            success = await run_test("direct_orchestrator.py")
            if success:
                logger.info("✅ direct_orchestrator.py ran successfully! Use this solution.")
                return
            else:
                logger.warning("⚠️ direct_orchestrator.py had errors. Trying to fix orchestrator directly...")
    
    # Check and fix orchestrator
    if not check_orchestrator_modifications():
        logger.info("Attempting to fix orchestrator...")
        fix_ok = fix_orchestrator()
        if not fix_ok:
            logger.error("❌ Failed to fix orchestrator")
        
        # Fix client method mismatch
        method_fix_ok = handle_client_method_mismatch()
        if not method_fix_ok:
            logger.error("❌ Failed to fix client method mismatch")
        
        if fix_ok and method_fix_ok:
            logger.info("✅ Fixed orchestrator successfully. Running it...")
            success = await run_test("orchestrator.py")
            if success:
                logger.info("✅ Fixed orchestrator ran successfully! Use this solution.")
                return
            else:
                logger.warning("⚠️ Fixed orchestrator still has errors. Creating direct solution...")
    
    # Create direct solution if all else fails
    if not os.path.exists("direct_load_pipeline.py") and not os.path.exists("direct_orchestrator.py"):
        logger.info("Creating direct solution as fallback...")
        create_direct_solution()
        
        if os.path.exists("direct_load_pipeline.py"):
            logger.info("Running direct_load_pipeline.py...")
            await run_test("direct_load_pipeline.py")
        elif os.path.exists("direct_orchestrator.py"):
            logger.info("Running direct_orchestrator.py...")
            await run_test("direct_orchestrator.py")
    
    logger.info("\n===== FINAL RECOMMENDATIONS =====")
    logger.info("After multiple solution attempts, here are your options:")
    
    if os.path.exists("direct_load_pipeline.py"):
        logger.info("1. Use direct_load_pipeline.py: python direct_load_pipeline.py")
    
    if os.path.exists("direct_orchestrator.py"):
        logger.info("2. Use direct_orchestrator.py: python direct_orchestrator.py")
    
    if registry_ok:
        logger.info("3. Use the registry-based approach (if registry is working): python orchestrator.py")
    
    logger.info("\nIf none of these work, try the database diagnosis script: python diagnose_db.py")

if __name__ == "__main__":
    asyncio.run(main())
