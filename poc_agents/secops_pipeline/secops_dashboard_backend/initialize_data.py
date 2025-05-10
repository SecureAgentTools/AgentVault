"""
This module pre-populates the dashboard with sample data to ensure
users always see populated data in the dashboard.
"""

import logging
import redis
import json
import os
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def initialize_sample_data():
    """Initialize sample data in Redis for dashboard demonstration."""
    redis_url = os.environ.get("REDIS_URL", "redis://secops-redis:6379")
    logger.info(f"Initializing sample data using Redis at {redis_url}")
    
    # Connect to Redis
    try:
        redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        # Test connection
        redis_client.ping()
        logger.info("Connected to Redis successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return False
        
    # Sample execution list data
    execution_list_data = {
        "event_type": "execution_list",
        "executions": [
            {
                "project_id": "secops-demo1",
                "name": "Suspicious Authentication Activity",
                "status": "COMPLETED",
                "timestamp": (datetime.now() - timedelta(minutes=15)).isoformat()
            },
            {
                "project_id": "secops-demo2",
                "name": "Malware Detection",
                "status": "COMPLETED",
                "timestamp": (datetime.now() - timedelta(minutes=30)).isoformat()
            },
            {
                "project_id": "secops-demo3",
                "name": "Firewall Rule Violation",
                "status": "MANUAL_REVIEW",
                "timestamp": (datetime.now() - timedelta(minutes=45)).isoformat()
            }
        ]
    }
    
    # Sample enrichment data
    enrichment_data = {
        "event_type": "enrichment_results",
        "project_id": "secops-demo1",
        "indicators": [
            {
                "value": "192.168.1.100",
                "type": "ip_address",
                "verdict": "Suspicious"
            },
            {
                "value": "malware.exe",
                "type": "file_name",
                "verdict": "Malicious"
            },
            {
                "value": "example.com",
                "type": "domain",
                "verdict": "Clean"
            }
        ],
        "additional_context": {
            "ip_location": "Eastern Europe (Suspicious)",
            "previous_activity": "Multiple failed login attempts",
            "enrichment_source": "Threat Intelligence Platform"
        }
    }
    
    # Sample LLM decision data
    llm_decision_data = {
        "event_type": "llm_decision",
        "project_id": "secops-demo1",
        "severity": "High",
        "confidence_percentage": 85,
        "recommended_action": "ISOLATE_HOST",
        "reasoning": "The combination of suspicious IP access from Eastern Europe, multiple failed login attempts, and malware detection indicates a high probability of compromise. Recommend isolating the host to prevent lateral movement."
    }
    
    # Sample alert details
    alert_details_data = {
        "event_type": "alert_details",
        "project_id": "secops-demo1",
        "alert_id": "SIEM-2025-001",
        "name": "Suspicious Authentication Activity",
        "source": "SIEM",
        "time": (datetime.now() - timedelta(minutes=15)).isoformat(),
        "description": "Multiple failed login attempts followed by successful login from suspicious IP address.",
        "affected_systems": ["workstation-104", "file-server-01"],
        "details": {
            "user": "jsmith",
            "source_ip": "192.168.1.100",
            "login_time": (datetime.now() - timedelta(minutes=15)).isoformat(),
            "geolocation": "Eastern Europe"
        }
    }
    
    # Sample response action data
    response_action_data = {
        "event_type": "response_action",
        "project_id": "secops-demo1",
        "action_type": "ISOLATE_HOST",
        "status": "Success",
        "details": {
            "isolation_id": "ISO98765",
            "isolation_status": "isolated",
            "target_host": "workstation-104"
        },
        "parameters": {
            "hostname": "workstation-104",
            "isolation_level": "full",
            "justification": "Suspicious activity detected"
        }
    }
    
    # Publish all sample data to Redis
    try:
        # First publish execution list
        redis_client.publish("secops_events", json.dumps(execution_list_data))
        logger.info("Published sample execution list data")
        time.sleep(0.5)  # Small delay between events
        
        # Publish enrichment data
        redis_client.publish("secops_events", json.dumps(enrichment_data))
        logger.info("Published sample enrichment data")
        time.sleep(0.5)
        
        # Publish LLM decision
        redis_client.publish("secops_events", json.dumps(llm_decision_data))
        logger.info("Published sample LLM decision data")
        time.sleep(0.5)
        
        # Publish alert details
        redis_client.publish("secops_events", json.dumps(alert_details_data))
        logger.info("Published sample alert details data")
        time.sleep(0.5)
        
        # Publish response action
        redis_client.publish("secops_events", json.dumps(response_action_data))
        logger.info("Published sample response action data")
        
        return True
    except Exception as e:
        logger.error(f"Failed to publish sample data: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    initialize_sample_data()
