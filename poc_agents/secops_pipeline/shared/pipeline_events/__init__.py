"""
Pipeline event emitter module for the SecOps Pipeline.
Allows pipeline nodes to emit events for dashboard visualization.
"""
import json
import logging
import os
import asyncio
from typing import Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

# Check if Redis is available
try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    logger.warning("aioredis not available. Pipeline events will be logged but not published.")
    _REDIS_AVAILABLE = False

# Redis connection settings
REDIS_URL = os.environ.get("REDIS_URL", "redis://secops-redis:6379")
REDIS_CHANNEL = "pipeline_events"

# Cache connection
_redis_client = None

async def get_redis_client():
    """Get a Redis client connection."""
    global _redis_client
    
    if not _REDIS_AVAILABLE:
        return None
        
    if _redis_client is None:
        try:
            _redis_client = aioredis.Redis.from_url(REDIS_URL)
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None
            
    return _redis_client

async def publish_pipeline_event(
    event_type: str, 
    data: Dict[str, Any], 
    project_id: Optional[str] = None
) -> bool:
    """
    Publish a pipeline event to Redis for dashboard visualization.
    
    Args:
        event_type: The type of event (e.g., 'step_complete', 'execution_started')
        data: The event data to publish
        project_id: The project ID (will be added to data if not present)
        
    Returns:
        bool: True if published successfully, False otherwise
    """
    if project_id and 'project_id' not in data:
        data['project_id'] = project_id
        
    # Prepare message payload
    message = {
        "type": event_type,
        "data": data
    }
    
    # Always log the event
    logger.debug(f"Pipeline event: {event_type} for project {project_id or 'unknown'}")
    
    # Publish to Redis if available
    if _REDIS_AVAILABLE:
        try:
            redis = await get_redis_client()
            if redis:
                serialized = json.dumps(message)
                result = await redis.publish(REDIS_CHANNEL, serialized)
                return result > 0
        except Exception as e:
            logger.error(f"Failed to publish pipeline event: {e}")
            
    return False

# Helper functions for common event types
async def emit_execution_started(project_id: str, alert_data: Dict[str, Any]) -> bool:
    """Emit execution_started event."""
    return await publish_pipeline_event(
        "execution_started", 
        {
            "project_id": project_id,
            "initial_alert_data": alert_data,
            "status": "STARTED",
            "current_step": "start_pipeline"
        }
    )

async def emit_step_complete(
    step_name: str,
    project_id: str,
    data: Dict[str, Any],
    error: Optional[str] = None
) -> bool:
    """Emit step_complete event."""
    event_data = {
        "project_id": project_id,
        "current_step": step_name,
        **data
    }
    
    if error:
        event_data["error_message"] = error
        
    return await publish_pipeline_event("step_complete", event_data)

async def emit_execution_completed(
    project_id: str,
    status: str,
    data: Dict[str, Any],
    error: Optional[str] = None
) -> bool:
    """Emit execution_completed event."""
    event_data = {
        "project_id": project_id,
        "status": status,
        **data
    }
    
    if error:
        event_data["error_message"] = error
        
    return await publish_pipeline_event("execution_completed", event_data)
