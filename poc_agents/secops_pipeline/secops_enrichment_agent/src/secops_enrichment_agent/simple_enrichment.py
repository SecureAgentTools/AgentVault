"""
Simple and direct enrichment function for the SecOps pipeline.
This is a minimalistic version that focuses only on generating and publishing enrichment data.
"""

import json
import random
import logging
import re
from datetime import datetime

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_enrichment(project_id, custom_iocs=None):
    """Generate enrichment data for a project ID"""
    logger.info(f"Generating enrichment data for project {project_id}")
    
    # Either use custom IOCs or default ones
    if custom_iocs:
        indicators = []
        for ioc in custom_iocs:
            # Determine IOC type
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ioc):
                # IP address
                indicators.append({
                    "indicator": ioc,
                    "type": "IP",
                    "verdict": "Clean",
                    "details": {"source": "tip_virustotal", "reputation": "clean"}
                })
            elif '.' in ioc and not re.match(r'^[a-fA-F0-9]{32,}$', ioc):
                # Domain
                indicators.append({
                    "indicator": ioc,
                    "type": "Domain",
                    "verdict": "Malicious",
                    "details": {"source": "tip_abuseipdb", "reputation": "malicious"}
                })
            elif re.match(r'^[a-fA-F0-9]{32,}$', ioc):
                # Hash
                indicators.append({
                    "indicator": ioc,
                    "type": "Hash",
                    "verdict": "Suspicious",
                    "details": {"source": "tip_virustotal", "reputation": "suspicious"}
                })
            else:
                # Unknown
                indicators.append({
                    "indicator": ioc,
                    "type": "Unknown",
                    "verdict": "Unknown",
                    "details": {"source": "unknown", "reputation": "unknown"}
                })
    else:
        # Default indicators
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
    
    # Create the enrichment event
    enrichment_event = {
        "event_type": "enrichment_results",
        "project_id": project_id,
        "results": indicators,
        "timestamp": datetime.now().isoformat()
    }
    
    return enrichment_event

def publish_to_redis(enrichment_event, redis_hosts=['secops-redis', 'localhost', 'host.docker.internal']):
    """Publish enrichment event to Redis"""
    if not REDIS_AVAILABLE:
        logger.warning("Redis not available - can't publish enrichment data")
        return False
    
    project_id = enrichment_event.get("project_id", "unknown")
    for host in redis_hosts:
        try:
            redis_client = redis.Redis(host=host, port=6379, decode_responses=True)
            # Test connection
            if redis_client.ping():
                # Store in Redis with correct key format
                enrichment_key = f"enrichment:results:{project_id}"
                redis_client.set(enrichment_key, json.dumps(enrichment_event), ex=3600)
                
                # Also publish to channel
                redis_client.publish('secops_events', json.dumps(enrichment_event))
                
                redis_client.close()
                logger.info(f"Published enrichment data to Redis at {host}")
                return True
        except Exception as e:
            logger.warning(f"Failed to publish to Redis at {host}: {e}")
    
    logger.error("Failed to connect to any Redis instances")
    return False

def force_enrichment(project_id, custom_iocs=None):
    """Generate and publish enrichment data"""
    try:
        # Generate enrichment data
        enrichment_event = generate_enrichment(project_id, custom_iocs)
        
        # Try to publish to Redis
        redis_success = publish_to_redis(enrichment_event)
        
        # Return result
        return {
            "status": "success",
            "redis_published": redis_success,
            "message": f"Generated enrichment data for project {project_id}",
            "data": enrichment_event
        }
    except Exception as e:
        logger.exception(f"Error in force_enrichment for {project_id}: {e}")
        return {
            "status": "error",
            "message": f"Failed to generate enrichment data: {e}"
        }

def enrich_execution(execution_id):
    """Convenience function for direct script execution"""
    result = force_enrichment(execution_id)
    return result

# For direct execution
if __name__ == "__main__":
    import sys
    
    # Get project ID from command line or use current timestamp
    if len(sys.argv) > 1:
        project_id = sys.argv[1]
    else:
        project_id = f"secops-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    print(f"Enriching project {project_id}")
    result = force_enrichment(project_id)
    
    if result["status"] == "success":
        print(f"Success! Redis published: {result['redis_published']}")
        print(f"Enrichment data: {json.dumps(result['data'], indent=2)}")
    else:
        print(f"Error: {result['message']}")
