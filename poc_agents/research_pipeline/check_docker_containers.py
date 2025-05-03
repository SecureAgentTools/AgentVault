#!/usr/bin/env python
"""
Tool to check if all required Docker containers for the pipeline agents are running.
"""

import subprocess
import logging
import json
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Expected container names
EXPECTED_CONTAINERS = [
    "topic-research-agent",
    "content-crawler-agent",
    "information-extraction-agent",
    "fact-verification-agent",
    "content-synthesis-agent",
    "editor-agent",
    "visualization-agent",
    "mypg"  # PostgreSQL database
]

def check_docker_running():
    """Check if Docker is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            logger.info("✅ Docker is running")
            return True
        else:
            logger.error("❌ Docker is not running or not responding")
            logger.error(f"Error: {result.stderr}")
            return False
    except FileNotFoundError:
        logger.error("❌ Docker command not found. Is Docker installed?")
        return False
    except Exception as e:
        logger.error(f"❌ Error checking Docker: {e}")
        return False

def get_running_containers():
    """Get list of all running Docker containers."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True
        )
        
        containers = [name.strip() for name in result.stdout.splitlines() if name.strip()]
        logger.info(f"Found {len(containers)} running containers")
        return containers
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Error getting container list: {e.stderr}")
        return []
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return []

def check_containers_status():
    """Check which expected containers are running."""
    if not check_docker_running():
        logger.error("Docker is not available. Cannot check containers.")
        return
    
    running_containers = get_running_containers()
    
    logger.info("\n=== Container Status ===")
    results = []
    
    for container in EXPECTED_CONTAINERS:
        status = container in running_containers
        results.append({
            "container": container,
            "running": status
        })
        logger.info(f"{container}: {'✅ RUNNING' if status else '❌ NOT RUNNING'}")
    
    # Show any unexpected but running containers
    unexpected = [c for c in running_containers if c not in EXPECTED_CONTAINERS]
    if unexpected:
        logger.info("\n=== Other Running Containers ===")
        for container in unexpected:
            logger.info(f"{container}: RUNNING (not part of expected set)")
    
    # Print summary
    running_count = sum(1 for r in results if r['running'])
    logger.info(f"\nRunning {running_count}/{len(EXPECTED_CONTAINERS)} expected containers")
    
    # Provide recommendations
    if running_count < len(EXPECTED_CONTAINERS):
        missing = [r['container'] for r in results if not r['running']]
        logger.info("\nRecommendations:")
        logger.info(f"1. Start missing containers: {', '.join(missing)}")
        logger.info("2. Use 'docker-compose up -d' to start all containers")
        logger.info("3. Check docker-compose.yml to ensure all required services are defined")
        logger.info("4. Run 'docker logs <container-name>' to check for startup errors")

def start_missing_containers():
    """Start any missing containers using docker-compose."""
    logger.info("Attempting to start any missing containers with docker-compose...")
    
    try:
        result = subprocess.run(
            ["docker-compose", "up", "-d"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            logger.info("✅ Successfully started containers")
            logger.info(result.stdout)
        else:
            logger.error("❌ Error starting containers")
            logger.error(result.stderr)
            return False
        
        # Verify containers are now running
        check_containers_status()
        return True
    except FileNotFoundError:
        logger.error("❌ docker-compose command not found. Is it installed?")
        return False
    except Exception as e:
        logger.error(f"❌ Error running docker-compose: {e}")
        return False

def main():
    """Main function to check Docker container status."""
    logger.info("Checking Docker container status for pipeline agents...")
    
    # Check container status
    check_containers_status()
    
    # Ask if user wants to start missing containers
    if "--start" in sys.argv:
        start_missing_containers()

if __name__ == "__main__":
    main()
