"""
Simple, direct fix for the enrichment agent to properly format enrichment results
"""

import json
import redis
import datetime
import logging
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fix_enrichment")

# Sample IOCs and enrichment results
sample_iocs = [
    "192.168.1.1",
    "malicious-domain.com",
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
]

sample_project_id = f"secops-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

# Format enrichment results correctly
def format_enrichment_results(iocs):
    """Format IOCs in the correct structure for the dashboard"""
    results = []
    
    for ioc in iocs:
        # Determine the indicator type
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ioc):
            indicator_type = "IP"
            raw_data = {"source": "sample", "reputation": "clean"}
            verdict = "Clean"
        elif '.' in ioc and not re.match(r'^[a-fA-F0-9]{32,}$', ioc):
            indicator_type = "Domain"
            raw_data = {"source": "sample", "reputation": "suspicious"}
            verdict = "Suspicious"
        else:
            indicator_type = "Hash"
            raw_data = {"source": "sample", "reputation": "malicious"}
            verdict = "Malicious"
        
        # Add to results
        results.append({
            "indicator": ioc,
            "type": indicator_type,
            "verdict": verdict,
            "details": raw_data
        })
        
    return results

# Connect to Redis
def publish_to_redis(project_id, formatted_results):
    """Publish the enrichment results to Redis"""
    try:
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        
        # Create the event
        enrichment_event = {
            "event_type": "enrichment_results",
            "project_id": project_id,
            "results": formatted_results,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Publish to channel
        logger.info(f"Publishing enrichment results for project {project_id}")
        result = redis_client.publish('secops_events', json.dumps(enrichment_event))
        logger.info(f"Published to Redis: {result}")
        
        # Also store in Redis
        redis_client.set(f"enrichment:{project_id}", json.dumps(enrichment_event), ex=3600)
        redis_client.close()
        
        return True
    except Exception as e:
        logger.error(f"Error publishing to Redis: {e}")
        return False

if __name__ == "__main__":
    # Format the enrichment results
    formatted_results = format_enrichment_results(sample_iocs)
    
    # Publish to Redis
    success = publish_to_redis(sample_project_id, formatted_results)
    
    if success:
        print(f"Successfully published enrichment results to Redis for project {sample_project_id}")
    else:
        print("Failed to publish enrichment results to Redis")
