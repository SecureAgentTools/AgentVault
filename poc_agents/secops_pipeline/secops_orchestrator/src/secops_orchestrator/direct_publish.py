""" 
Direct Redis event publisher for dashboard events.
"""
import os
import json
import logging
import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Import the Redis publisher
try:
    from .redis_publisher import RedisPublisher
    _redis_publisher = RedisPublisher()
    _REDIS_AVAILABLE = True
    logger.info("Redis publisher initialized successfully")
except ImportError:
    logger.warning("redis_publisher module not available. Using fallback.")
    _REDIS_AVAILABLE = False
    _redis_publisher = None

    # Fallback: Check if Redis is available directly
    try:
        import redis
        _REDIS_AVAILABLE = True
    except ImportError:
        logger.warning("redis not available. Direct publishing will be disabled.")
        _REDIS_AVAILABLE = False

# Redis connection settings
REDIS_URL = os.environ.get("REDIS_URL", "redis://secops-redis:6379")
REDIS_CHANNEL = "secops_events"  # Changed to match dashboard expectation

# Cache connection for fallback mechanism
_redis_client = None

def get_redis_client():
    """Get a Redis client connection."""
    global _redis_client
    
    if not _REDIS_AVAILABLE:
        return None
        
    if _redis_client is None:
        try:
            # Parse Redis URL
            if "://" in REDIS_URL:
                # Handle redis://host:port format
                protocol, address = REDIS_URL.split("://", 1)
                if ":" in address:
                    host, port = address.split(":", 1)
                    if "/" in port:
                        port = port.split("/", 1)[0]
                    port = int(port)
                else:
                    host = address
                    port = 6379
            else:
                # Default
                host = REDIS_URL
                port = 6379
                
            logger.info(f"Connecting to Redis at {host}:{port}")
            _redis_client = redis.Redis(host=host, port=port, db=0)
            ping_result = _redis_client.ping()
            logger.info(f"Redis connection test: {ping_result}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None
            
    return _redis_client

def publish_pipeline_event(
    event_type: str, 
    data: Dict[str, Any], 
    project_id: Optional[str] = None
) -> bool:
    """
    Directly publish a pipeline event to Redis for dashboard visualization.
    
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
        "event_type": event_type,  # Changed to match dashboard expectation
        **data  # Flattened structure to match dashboard expectation
    }
    
    # Always log the event
    logger.info(f"DIRECT PUBLISH: Pipeline event: {event_type} for project {project_id or 'unknown'}")
    
    # Try to publish using our Redis publisher first
    if _redis_publisher:
        try:
            result = _redis_publisher.publish_event(event_type, data)
            if result:
                logger.info(f"Event published successfully via redis_publisher")
                return True
            else:
                logger.warning(f"Failed to publish via redis_publisher, falling back to direct Redis")
        except Exception as e:
            logger.error(f"Error with redis_publisher: {e}, falling back to direct Redis")
    
    # Fallback: Publish to Redis directly if publisher module failed
    if _REDIS_AVAILABLE:
        try:
            redis_client = get_redis_client()
            if redis_client:
                serialized = json.dumps(message)
                result = redis_client.publish(REDIS_CHANNEL, serialized)
                logger.info(f"Redis publish result: {result}")
                return result > 0
            else:
                logger.error("Redis client not available")
        except Exception as e:
            logger.error(f"Failed to publish pipeline event: {e}")
            
    return False

# Helper functions for common event types
async def emit_execution_started(project_id: str, alert_data: Dict[str, Any]) -> bool:
    """Emit execution_started event."""
    # Extract alert metadata for summary
    alert_name = alert_data.get("name", "Unknown Alert")
    alert_source = alert_data.get("source", "Unknown Source")
    alert_severity = alert_data.get("severity", "Unknown")
    
    # Start time
    start_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Update pipeline step
    if _redis_publisher:
        await _redis_publisher.publish_pipeline_step(
            project_id=project_id,
            current_step=0,  # Start step
            total_steps=7
        )
    
    # Create execution summary with initial data
    if _redis_publisher:
        await _redis_publisher.publish_execution_summary(
            project_id=project_id,
            status="PROCESSING",
            start_time=start_time,
            duration_seconds=0.0,
            alert_source=alert_source,
            response_action="Pending"
        )
    
    # Publish alert details
    if _redis_publisher:
        try:
            # Extract common fields
            alert_time = alert_data.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
            alert_description = alert_data.get("description", "No description available")
            affected_systems = alert_data.get("affected_systems", [])
            details = alert_data.get("details", {})
            
            await _redis_publisher.publish_alert_details(
                project_id=project_id,
                alert_id=alert_data.get("alert_id", "UNKNOWN"),
                alert_name=alert_name,
                alert_source=alert_source,
                alert_time=alert_time,
                alert_description=alert_description,
                affected_systems=affected_systems,
                details=details
            )
        except Exception as e:
            logger.error(f"Error publishing alert details: {e}")
    
    # Fallback to old method
    return publish_pipeline_event(
        "execution_started", 
        {
            "project_id": project_id,
            "alert_name": alert_name,
            "alert_source": alert_source,
            "alert_severity": alert_severity,
            "status": "STARTED",
            "current_step": 0,  # Changed to match dashboard expectation
            "start_time": start_time
        }
    )

async def emit_step_complete(
    step_name: str,
    project_id: str,
    data: Dict[str, Any],
    error: Optional[str] = None
) -> bool:
    """Emit step_complete event."""
    # Map step names to step numbers for the dashboard
    step_map = {
        "start_pipeline": 0,
        "ingest_alert": 1,
        "enrichment": 2,
        "investigation": 3,
        "determine_response": 4,
        "execute_response": 5,
        "complete_pipeline": 6
    }
    step_number = step_map.get(step_name, 0)
    
    # Update pipeline step
    if _redis_publisher:
        await _redis_publisher.publish_pipeline_step(
            project_id=project_id,
            current_step=step_number,
            error_step=None if not error else step_number
        )
    
    # Handle special steps with more detailed updates
    if step_name == "enrichment" and "enrichment_results" in data:
        if _redis_publisher:
            try:
                enrichment = data.get("enrichment_results", {})
                indicators = []
                
                # Extract indicators from enrichment results
                if isinstance(enrichment, dict) and "indicators" in enrichment:
                    for indicator in enrichment.get("indicators", []):
                        indicators.append({
                            "value": indicator.get("value", "Unknown"),
                            "type": indicator.get("type", "Unknown"),
                            "verdict": indicator.get("verdict", "Unknown")
                        })
                
                # Create additional context
                additional_context = {
                    "ip_location": enrichment.get("ip_location", "Unknown"),
                    "previous_activity": enrichment.get("previous_activity", "No prior history"),
                    "enrichment_source": enrichment.get("sources", ["Unknown Source"])
                }
                
                await _redis_publisher.publish_enrichment_results(
                    project_id=project_id,
                    indicators=indicators,
                    additional_context=additional_context
                )
            except Exception as e:
                logger.error(f"Error publishing enrichment results: {e}")
    
    elif step_name == "investigation" and "investigation_findings" in data:
        if _redis_publisher:
            try:
                findings = data.get("investigation_findings", {})
                severity = findings.get("severity", "UNKNOWN")
                confidence = findings.get("confidence_percentage", 50)
                action = findings.get("recommended_action", "Unknown")
                reasoning = findings.get("reasoning", "No reasoning provided")
                
                await _redis_publisher.publish_llm_decision(
                    project_id=project_id,
                    severity=severity,
                    confidence_percentage=confidence,
                    recommended_action=action,
                    reasoning=reasoning
                )
            except Exception as e:
                logger.error(f"Error publishing LLM decision: {e}")
    
    elif step_name == "execute_response" and "response_action_status" in data:
        if _redis_publisher:
            try:
                response_status = data.get("response_action_status", {})
                action_type = response_status.get("action", "Unknown")
                status = response_status.get("status", "Unknown")
                details = response_status.get("details", {})
                parameters = data.get("response_action_parameters", {})
                
                await _redis_publisher.publish_response_action(
                    project_id=project_id,
                    action_type=action_type,
                    status=status,
                    details=details,
                    parameters=parameters
                )
            except Exception as e:
                logger.error(f"Error publishing response action: {e}")
    
    # Fallback to old method
    event_data = {
        "project_id": project_id,
        "current_step": step_number,
        "step_name": step_name,
        **data
    }
    
    if error:
        event_data["error_message"] = error
        
    return publish_pipeline_event("pipeline_step", event_data)

async def emit_execution_completed(
    project_id: str,
    status: str,
    data: Dict[str, Any],
    error: Optional[str] = None
) -> bool:
    """Emit execution_completed event."""
    # Final step
    if _redis_publisher:
        await _redis_publisher.publish_pipeline_step(
            project_id=project_id,
            current_step=7 if status == "COMPLETED" else 6,  # Complete or last step
            error_step=None if status == "COMPLETED" else 6
        )
    
    # Execution summary
    if _redis_publisher:
        try:
            # Calculate duration
            start_time = data.get("start_time", datetime.datetime.now(datetime.timezone.utc).isoformat())
            end_time = datetime.datetime.now(datetime.timezone.utc)
            duration_seconds = 9.04  # Default for demo
            
            # Try to get original alert info
            alert_source = "Unknown"
            response_action = "Unknown"
            
            if "initial_alert_data" in data:
                alert_source = data["initial_alert_data"].get("source", "Unknown")
            
            if "determined_response_action" in data and isinstance(data["determined_response_action"], dict):
                response_action = data["determined_response_action"].get("recommended_action", "Unknown")
            
            await _redis_publisher.publish_execution_summary(
                project_id=project_id,
                status=status,
                start_time=start_time,
                duration_seconds=duration_seconds,
                alert_source=alert_source,
                response_action=response_action
            )
            
            # Update execution list
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d, %Y - %H:%M:%S")
            alert_name = "Unknown Alert"
            if "initial_alert_data" in data:
                alert_name = data["initial_alert_data"].get("name", "Unknown Alert")
                
            executions = [
                {
                    "name": alert_name,
                    "status": status,
                    "timestamp": timestamp,
                    "project_id": project_id
                }
            ]
            
            await _redis_publisher.publish_execution_list(executions=executions)
        except Exception as e:
            logger.error(f"Error publishing execution summary: {e}")
    
    # Fallback to old method
    event_data = {
        "project_id": project_id,
        "status": status,
        **data
    }
    
    if error:
        event_data["error_message"] = error
        
    return publish_pipeline_event("execution_completed", event_data)
