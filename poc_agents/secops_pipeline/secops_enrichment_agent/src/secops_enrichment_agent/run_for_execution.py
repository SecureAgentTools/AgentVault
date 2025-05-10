#!/usr/bin/env python
"""
Direct script to run enrichment for the specific execution ID shown in the dashboard.
"""

import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("enrichment_fix")

# Import our simple enrichment module
try:
    from simple_enrichment import force_enrichment
except ImportError:
    try:
        from secops_enrichment_agent.simple_enrichment import force_enrichment
    except ImportError:
        from src.secops_enrichment_agent.simple_enrichment import force_enrichment

def run_enrichment(project_id):
    """Run enrichment for a specific project ID"""
    logger.info(f"Running enrichment for {project_id}")
    result = force_enrichment(project_id)
    
    if result["status"] == "success":
        logger.info(f"Successfully generated enrichment data for {project_id}")
        return True
    else:
        logger.error(f"Failed to generate enrichment data: {result['message']}")
        return False

if __name__ == "__main__":
    # Specific execution ID from the dashboard
    execution_id = "secops-20250509205203-e0237c"
    
    # Run enrichment for this execution
    success = run_enrichment(execution_id)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
