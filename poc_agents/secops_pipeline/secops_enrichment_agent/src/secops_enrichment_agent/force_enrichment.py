"""
Direct force enrichment module to bypass the normal pipeline.
Creates and publishes mock enrichment data directly to Redis.
"""

import json
import redis
import random
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

def determine_ioc_type(ioc: str) -> tuple:
    """Determine the IOC type and generate appropriate verdict and details"""
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ioc):
        ioc_type = "IP"
        verdict = random.choice(["Clean", "Suspicious", "Malicious"])
        details = {"source": "tip_virustotal", "reputation": verdict.lower()}
    elif '.' in ioc and not re.match(r'^[a-fA-F0-9]{32,}$', ioc):
        ioc_type = "Domain"
        verdict = random.choice(["Clean", "Suspicious", "Malicious"])
        details = {"source": "tip_abuseipdb", "reputation": verdict.lower()}
    elif re.match(r'^[a-fA-F0-9]{32,}$', ioc):
        ioc_type = "Hash"
        verdict = random.choice(["Clean", "Suspicious", "Malicious"])
        details = {"source": "tip_virustotal", "reputation": verdict.lower()}
    else:
        ioc_type = "Unknown"
        verdict = "Unknown"
        details = {"source": "unknown", "reputation": "unknown"}
    
    return ioc_type, verdict, details

def create_default_indicators() -> List[Dict[str, Any]]:
    """Create default indicators for testing"""
    return [
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

def create_custom_indicators(iocs: List[str]) -> List[Dict[str, Any]]:
    """Create indicators from custom IOCs"""
    indicators = []
    for ioc in iocs:
        ioc_type, verdict, details = determine_ioc_type(ioc)
        indicators.append({
            "indicator": ioc,
            "type": ioc_type,
            "verdict": verdict,
            "details": details
        })
    return indicators

def get_redis_client() -> Optional[redis.Redis]:
    """Try to get a Redis client from multiple possible hosts"""
    redis_hosts = [
        'secops-redis',     # Docker service name
        'localhost',        # Local development
        'host.docker.internal'  # Docker-to-host communication
    ]
    
    for host in redis_hosts:
        try:
            client = redis.Redis(host=host, port=6379, decode_responses=True)
            if client.ping():
                logger.info(f"Connected to Redis at {host}")
                return client
        except Exception as e:
            logger.debug(f"Failed to connect to Redis at {host}: {e}")
    
    logger.warning("Could not connect to Redis on any host")
    return None

def force_enrichment(project_id: str, custom_iocs: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Force enrichment data generation for a project ID
    
    Args:
        project_id: The project ID to generate enrichment data for
        custom_iocs: Optional list of custom IOCs to use instead of default ones
        
    Returns:
        Dict with status and enrichment event data
    """
    try:
        logger.info(f"Forcing enrichment for project {project_id}")
        
        # Generate indicators
        if custom_iocs:
            indicators = create_custom_indicators(custom_iocs)
        else:
            indicators = create_default_indicators()
        
        # Create the enrichment event
        enrichment_event = {
            "event_type": "enrichment_results",
            "project_id": project_id,
            "results": indicators,
            "timestamp": datetime.now().isoformat()
        }
        
        # Try to store in Redis if available
        redis_client = get_redis_client()
        if redis_client:
            # Store in Redis with the correct key format
            enrichment_key = f"enrichment:results:{project_id}"
            redis_client.set(enrichment_key, json.dumps(enrichment_event), ex=3600)
            
            # Also publish to the Redis channel
            redis_client.publish('secops_events', json.dumps(enrichment_event))
            
            redis_client.close()
            logger.info(f"Stored and published enrichment data for {project_id}")
            status = "success_with_redis"
        else:
            logger.warning(f"Redis unavailable - mock data generated but not stored")
            status = "success_no_redis"
        
        return {
            "status": status,
            "message": f"Generated mock enrichment data for project {project_id}",
            "data": enrichment_event
        }
        
    except Exception as e:
        logger.exception(f"Error forcing enrichment for {project_id}: {e}")
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }

def force_batch_enrichment(project_ids: List[str]) -> Dict[str, Any]:
    """
    Force enrichment data generation for multiple project IDs
    
    Args:
        project_ids: List of project IDs to generate enrichment data for
        
    Returns:
        Dict with status and summary of results
    """
    results = []
    success_count = 0
    error_count = 0
    
    for project_id in project_ids:
        result = force_enrichment(project_id)
        if result["status"].startswith("success"):
            success_count += 1
        else:
            error_count += 1
        results.append({"project_id": project_id, "status": result["status"]})
    
    return {
        "status": "completed",
        "summary": {
            "total": len(project_ids),
            "success": success_count,
            "error": error_count
        },
        "results": results
    }

# Simple CLI interface when run directly
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    import sys
    if len(sys.argv) > 1:
        project_id = sys.argv[1]
        print(f"Forcing enrichment for project {project_id}")
        result = force_enrichment(project_id)
        print(f"Result: {result['status']} - {result['message']}")
    else:
        print("Usage: python force_enrichment.py <project_id>")
        print("Generating for default projects...")
        default_projects = [
            "secops-default1",
            "secops-default2",
            "secops-default3",
            "secops-default4",
            "secops-default5",
            f"secops-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ]
        result = force_batch_enrichment(default_projects)
        print(f"Batch result: {result['summary']}")
