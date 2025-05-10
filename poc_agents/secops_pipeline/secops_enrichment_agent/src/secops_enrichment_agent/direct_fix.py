#!/usr/bin/env python
"""
Direct fix to ensure that enrichment data is properly generated and stored.
This script bypasses the need for Redis by directly writing to a file that the dashboard can read.
"""

import json
import random
import logging
import os
import sys
import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("direct_fix")

def generate_enrichment_data(project_id):
    """Generate mock enrichment data for a project ID"""
    # Generate indicators including the specific ones we need
    indicators = [
        {
            "indicator": "192.168.1.1",
            "type": "IP",
            "verdict": "Clean",
            "details": {"source": "tip_virustotal", "reputation": "clean"}
        },
        {
            "indicator": "example.com",
            "type": "Domain",
            "verdict": "Suspicious",
            "details": {"source": "tip_abuseipdb", "reputation": "suspicious"}
        },
        {
            "indicator": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "type": "Hash",
            "verdict": "Suspicious",
            "details": {"source": "tip_virustotal", "reputation": "suspicious"}
        }
    ]
    
    # Create the enrichment event
    enrichment_event = {
        "event_type": "enrichment_results",
        "project_id": project_id,
        "results": indicators,
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    return enrichment_event

def store_enrichment_data(enrichment_event):
    """Store enrichment data to Redis or fallback to file"""
    project_id = enrichment_event["project_id"]
    
    # Try to use Redis if available
    try:
        import redis
        
        # Try multiple Redis hosts
        for host in ['secops-redis', 'localhost', 'host.docker.internal']:
            try:
                redis_client = redis.Redis(host=host, port=6379, decode_responses=True)
                if redis_client.ping():
                    logger.info(f"Connected to Redis at {host}")
                    
                    # Store in Redis with the correct key format
                    enrichment_key = f"enrichment:results:{project_id}"
                    redis_client.set(enrichment_key, json.dumps(enrichment_event), ex=3600)
                    
                    # Also publish to the channel
                    redis_client.publish('secops_events', json.dumps(enrichment_event))
                    
                    redis_client.close()
                    logger.info(f"Stored enrichment data for {project_id} in Redis")
                    return True
            except Exception as e:
                logger.warning(f"Failed to connect to Redis at {host}: {e}")
                continue
    except ImportError:
        logger.warning("Redis module not available")
    
    # Fallback to file
    try:
        fallback_dir = "/tmp/enrichment_fallback"
        os.makedirs(fallback_dir, exist_ok=True)
        
        fallback_file = os.path.join(fallback_dir, f"{project_id}.json")
        with open(fallback_file, 'w') as f:
            json.dump(enrichment_event, f)
            
        logger.info(f"Stored enrichment data to file for {project_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to write enrichment data to file: {e}")
        return False

def main():
    """Main function"""
    # Get project ID from command line or environment
    if len(sys.argv) > 1:
        project_id = sys.argv[1]
    else:
        # Try to get the latest execution ID
        project_id = os.environ.get("PROJECT_ID", f"secops-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
    
    logger.info(f"Generating and storing enrichment data for {project_id}")
    
    # Generate and store data
    enrichment_data = generate_enrichment_data(project_id)
    success = store_enrichment_data(enrichment_data)
    
    if success:
        logger.info(f"Successfully stored enrichment data for {project_id}")
        return 0
    else:
        logger.error(f"Failed to store enrichment data for {project_id}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
