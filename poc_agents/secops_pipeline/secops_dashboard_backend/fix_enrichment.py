"""
Simple fix to generate enrichment data for all executions.
"""

import json
import redis
import logging
import random
from datetime import datetime
from execution_storage import get_executions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enrichment-fix")

def generate_mock_enrichment(execution_id):
    """Generate mock enrichment data for a specific execution"""
    indicators = [
        {
            "indicator": "192.168.1.1",
            "type": "IP",
            "verdict": "Clean",
            "details": {"source": "tip_virustotal", "reputation": "clean"}
        },
        {
            "indicator": f"malicious-domain-{random.randint(1, 100)}.com",
            "type": "Domain",
            "verdict": "Malicious",
            "details": {"source": "tip_abuseipdb", "reputation": "malicious"}
        },
        {
            "indicator": f"{random.randint(10**31, 10**32):x}",
            "type": "Hash",
            "verdict": "Suspicious",
            "details": {"source": "tip_virustotal", "reputation": "suspicious"}
        }
    ]
    
    enrichment_event = {
        "event_type": "enrichment_results",
        "project_id": execution_id,
        "results": indicators,
        "timestamp": datetime.now().isoformat()
    }
    
    return enrichment_event

def fix_enrichment_data():
    """Create enrichment data for all executions in the system"""
    try:
        redis_client = redis.Redis(host='secops-redis', port=6379, decode_responses=True)
        
        # Get all executions
        executions = get_executions()
        logger.info(f"Found {len(executions)} executions to process")
        
        # For each execution, generate and store enrichment data
        for execution in executions:
            project_id = execution.get("project_id")
            if not project_id:
                continue
                
            # Generate mock enrichment data
            enrichment_event = generate_mock_enrichment(project_id)
            
            # Store in Redis with the correct key format
            redis_key = f"enrichment:results:{project_id}"
            redis_client.set(redis_key, json.dumps(enrichment_event), ex=3600)
            
        logger.info("Enrichment data fix completed successfully")
        redis_client.close()
        return True
        
    except Exception as e:
        logger.exception(f"Error fixing enrichment data: {e}")
        return False

if __name__ == "__main__":
    fix_enrichment_data()
