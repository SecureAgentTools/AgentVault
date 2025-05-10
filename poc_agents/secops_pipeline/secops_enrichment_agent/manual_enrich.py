#!/usr/bin/env python
"""
Manual script to force enrichment data generation.
Can be run directly or imported and called programmatically.
"""

import argparse
import requests
import json
import sys
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("manual_enrich")

def force_enrichment(host="localhost", port=8071, project_id=None):
    """
    Force enrichment data generation by calling the API endpoint
    
    Args:
        host: Hostname where the enrichment agent is running
        port: Port the enrichment agent is running on
        project_id: Optional specific project ID to enrich
        
    Returns:
        Response from the API
    """
    try:
        base_url = f"http://{host}:{port}"
        
        if project_id:
            # Call endpoint for specific project
            url = f"{base_url}/force-enrichment/{project_id}"
            logger.info(f"Forcing enrichment for specific project {project_id}")
        else:
            # Call endpoint for all default projects
            url = f"{base_url}/force-enrichment"
            logger.info("Forcing enrichment for all default projects")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Enrichment result: {result.get('status')} - {result.get('message')}")
        
        return result
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling enrichment API: {e}")
        # Try the older force-mock endpoint as fallback
        try:
            fallback_url = f"{base_url}/force-mock"
            logger.info(f"Trying fallback endpoint {fallback_url}")
            fallback_response = requests.get(fallback_url, timeout=10)
            fallback_response.raise_for_status()
            fallback_result = fallback_response.json()
            logger.info(f"Fallback result: {fallback_result.get('status')} - {fallback_result.get('message')}")
            return fallback_result
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            return {"status": "error", "message": f"Failed to call enrichment API: {e}"}
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"status": "error", "message": f"Unexpected error: {e}"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manually force enrichment data generation")
    parser.add_argument("--host", default="localhost", help="Hostname where the enrichment agent is running")
    parser.add_argument("--port", type=int, default=8071, help="Port the enrichment agent is running on")
    parser.add_argument("--project", help="Specific project ID to enrich (optional)")
    parser.add_argument("--now", action="store_true", help="Use current timestamp as project ID")
    
    args = parser.parse_args()
    
    project_id = None
    if args.now:
        project_id = f"secops-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"Using current timestamp as project ID: {project_id}")
    elif args.project:
        project_id = args.project
    
    result = force_enrichment(
        host=args.host,
        port=args.port,
        project_id=project_id
    )
    
    # Print the full result as formatted JSON
    print(json.dumps(result, indent=2))
