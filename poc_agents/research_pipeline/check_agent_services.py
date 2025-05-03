#!/usr/bin/env python
"""
Tool to check if all agent services in the pipeline are running and accessible.
"""

import asyncio
import logging
import json
from pathlib import Path
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agent service info
AGENT_SERVICES = [
    {"name": "topic-research", "url": "http://localhost:8010/a2a", "hri": "local-poc/topic-research"},
    {"name": "content-crawler", "url": "http://localhost:8011/a2a", "hri": "local-poc/content-crawler"},
    {"name": "information-extraction", "url": "http://localhost:8012/a2a", "hri": "local-poc/information-extraction"},
    {"name": "fact-verification", "url": "http://localhost:8013/a2a", "hri": "local-poc/fact-verification"},
    {"name": "content-synthesis", "url": "http://localhost:8014/a2a", "hri": "local-poc/content-synthesis"},
    {"name": "editor", "url": "http://localhost:8015/a2a", "hri": "local-poc/editor"},
    {"name": "visualization", "url": "http://localhost:8016/a2a", "hri": "local-poc/visualization"},
]

async def check_service(service):
    """Check if an agent service is running and accessible."""
    logger.info(f"Checking service: {service['name']} at {service['url']}")
    
    try:
        # Use POST instead of HEAD since these endpoints only accept POST
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Create a minimal JSON-RPC request
            test_data = {
                "jsonrpc": "2.0",
                "method": "tasks/get",  # Using tasks/get as it's likely to be supported
                "id": "health-check",
                "params": {"taskId": "test-task-id"}
            }
            
            response = await client.post(
                service['url'],
                json=test_data,
                follow_redirects=True
            )
            
            # 404 or 400 are actually OK here - it means the endpoint exists but the task doesn't
            if response.status_code < 500:  # Any non-server error means the endpoint is accessible
                logger.info(f"✅ Service {service['name']} is accessible (status: {response.status_code})")
                return True
            else:
                logger.error(f"❌ Service {service['name']} returned server error: {response.status_code}")
                return False
    except httpx.RequestError as e:
        logger.error(f"❌ Connection error to {service['name']}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error checking {service['name']}: {e}")
        return False

async def check_all_services():
    """Check all agent services."""
    results = []
    
    for service in AGENT_SERVICES:
        result = await check_service(service)
        results.append({
            "name": service['name'],
            "url": service['url'],
            "accessible": result
        })
    
    # Print summary
    logger.info("\n=== Agent Services Summary ===")
    accessible_count = sum(1 for r in results if r['accessible'])
    logger.info(f"Accessible Services: {accessible_count}/{len(AGENT_SERVICES)}")
    
    for result in results:
        status = "✅ ONLINE" if result['accessible'] else "❌ OFFLINE"
        logger.info(f"{result['name']}: {status} ({result['url']})")
    
    # Provide recommendations
    if accessible_count < len(AGENT_SERVICES):
        logger.info("\nRecommendations:")
        logger.info("1. Make sure all agent services are running")
        logger.info("2. Check docker-compose.yml to ensure all services are defined correctly")
        logger.info("3. Try running 'docker-compose up -d' to start all services")
        logger.info("4. If specific services are failing, check their logs with:")
        logger.info("   docker logs <container-name>")
        
    return results

async def send_test_message(service):
    """Try to send a simple test message to the agent."""
    logger.info(f"Sending test message to: {service['name']}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Construct a minimal JSON-RPC request for the agent
            test_data = {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "test-request-1",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [
                            {
                                "content": "Hello, this is a test message.",
                                "type": "text"
                            }
                        ]
                    }
                }
            }
            
            response = await client.post(
                service['url'], 
                json=test_data,
                follow_redirects=True
            )
            
            if response.status_code < 300:
                response_data = response.json()
                logger.info(f"✅ Received response from {service['name']}: {response_data}")
                return True, response_data
            else:
                logger.error(f"❌ Error response from {service['name']}: {response.status_code}, {response.text}")
                return False, None
    except Exception as e:
        logger.error(f"❌ Error sending test message to {service['name']}: {e}")
        return False, None

async def send_test_messages():
    """Send test messages to all accessible services."""
    logger.info("Sending test messages to accessible services...")
    
    # First check which services are accessible
    accessible_services = []
    for service in AGENT_SERVICES:
        if await check_service(service):
            accessible_services.append(service)
    
    if not accessible_services:
        logger.error("No accessible services found. Cannot send test messages.")
        return
    
    # Send test messages to accessible services
    for service in accessible_services:
        await send_test_message(service)

async def main():
    """Main function."""
    logger.info("Starting agent services check...")
    
    # Check service accessibility
    results = await check_all_services()
    
    # If at least one service is accessible, try sending test messages
    if any(r['accessible'] for r in results):
        await send_test_messages()

if __name__ == "__main__":
    asyncio.run(main())
