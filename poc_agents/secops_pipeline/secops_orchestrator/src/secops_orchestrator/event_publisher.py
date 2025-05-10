"""
Integration for Redis publisher to emit events during orchestration.
"""

import logging
from typing import Dict, Any, Optional, List, Union

# Import Redis publisher
try:
    from .redis_publisher import RedisPublisher
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis publisher not available. Real-time updates will be disabled.")

logger = logging.getLogger(__name__)

# Singleton publisher instance
_publisher = None

def get_publisher() -> Optional['RedisPublisher']:
    """Get or create the publisher instance"""
    global _publisher
    if _publisher is None and REDIS_AVAILABLE:
        try:
            _publisher = RedisPublisher()
            logger.info("Event publisher initialized")
        except Exception as e:
            logger.error(f"Failed to initialize event publisher: {e}")
            return None
    return _publisher

def publish_pipeline_step(project_id: str, step: int, total_steps: int = 7, error_step: Optional[int] = None) -> bool:
    """Publish pipeline step update"""
    publisher = get_publisher()
    if not publisher:
        return False
    
    return publisher.publish_pipeline_step(project_id, step, total_steps, error_step)

def publish_execution_summary(project_id: str, status: str, start_time: str, 
                             duration_seconds: float, alert_source: str, 
                             response_action: str) -> bool:
    """Publish execution summary"""
    publisher = get_publisher()
    if not publisher:
        return False
    
    return publisher.publish_execution_summary(
        project_id, status, start_time, duration_seconds, alert_source, response_action
    )

def publish_alert_details(project_id: str, alert_id: str, alert_name: str,
                         alert_source: str, alert_time: str, alert_description: str,
                         affected_systems: List[str], details: Dict[str, Any]) -> bool:
    """Publish alert details"""
    publisher = get_publisher()
    if not publisher:
        return False
    
    return publisher.publish_alert_details(
        project_id, alert_id, alert_name, alert_source, alert_time,
        alert_description, affected_systems, details
    )

def publish_enrichment_results(project_id: str, indicators: List[Dict[str, str]],
                              additional_context: Dict[str, Any]) -> bool:
    """Publish enrichment results"""
    publisher = get_publisher()
    if not publisher:
        return False
    
    return publisher.publish_enrichment_results(project_id, indicators, additional_context)

def publish_llm_decision(project_id: str, severity: str, confidence_percentage: int,
                        recommended_action: str, reasoning: str) -> bool:
    """Publish LLM decision"""
    publisher = get_publisher()
    if not publisher:
        return False
    
    return publisher.publish_llm_decision(
        project_id, severity, confidence_percentage, recommended_action, reasoning
    )

def publish_response_action(project_id: str, action_type: str, status: str,
                           details: Dict[str, Any], parameters: Dict[str, Any]) -> bool:
    """Publish response action execution details"""
    publisher = get_publisher()
    if not publisher:
        return False
    
    return publisher.publish_response_action(project_id, action_type, status, details, parameters)

def publish_execution_list(executions: List[Dict[str, Any]]) -> bool:
    """Publish updated execution list"""
    publisher = get_publisher()
    if not publisher:
        return False
    
    # FIX: If we only got a single execution, fetch the full list
    if len(executions) <= 1:
        logger.info("Received single execution for execution_list, fetching full history...")
        # Try to import storage helpers here to avoid circular imports
        try:
            import sys
            sys.path.append('/app/dashboard')
            from execution_storage import get_executions
            all_executions = get_executions()
            logger.info(f"Using full execution list from storage with {len(all_executions)} entries")
            # If this execution is new, add it to the list
            if executions and len(executions) > 0:
                current_execution = executions[0]
                project_ids = [ex.get("project_id") for ex in all_executions]
                if current_execution.get("project_id") not in project_ids:
                    all_executions.insert(0, current_execution)
                    logger.info(f"Added new execution {current_execution.get('project_id')} to history")
            return publisher.publish_execution_list(all_executions)
        except ImportError as e:
            logger.warning(f"Could not import dashboard execution_storage: {e}")
            logger.info("Falling back to default behavior with single execution")
            pass
    
    return publisher.publish_execution_list(executions)
