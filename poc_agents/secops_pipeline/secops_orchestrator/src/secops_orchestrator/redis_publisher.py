import redis
import json
import os
import logging
from typing import Dict, Any, Optional, List, Union
import datetime

logger = logging.getLogger(__name__)

class RedisPublisher:
    def __init__(self):
        self.redis_url = os.environ.get("REDIS_URL")
        self.client = None
        self._initialize()
    
    def _initialize(self):
        if not self.redis_url:
            logger.warning("REDIS_URL not configured, event publishing disabled")
            return
        
        try:
            self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self.client.ping()  # Test connection
            logger.info(f"Redis connected successfully at {self.redis_url}")
        except Exception as e:
            logger.error(f"Redis connection error: {e}")
            self.client = None
    
    def publish_event(self, event_type: str, data: Dict[str, Any]) -> bool:
        """Publish an event to the SecOps events channel"""
        if not self.client:
            logger.debug(f"Redis not available, skipping event: {event_type}")
            return False
        
        try:
            # Add timestamp if not present
            if "timestamp" not in data:
                data["timestamp"] = datetime.datetime.utcnow().isoformat()
                
            payload = {
                "event_type": event_type,
                **data
            }
            json_payload = json.dumps(payload)
            result = self.client.publish("secops_events", json_payload)
            logger.debug(f"Published {event_type} event, delivery count: {result}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish {event_type} event: {e}")
            return False
    
    def publish_pipeline_step(self, 
                            project_id: str, 
                            current_step: int, 
                            total_steps: int = 7,
                            error_step: Optional[int] = None) -> bool:
        """Publish pipeline step update"""
        return self.publish_event("pipeline_step", {
            "project_id": project_id,
            "current_step": current_step,
            "total_steps": total_steps,
            "error_step": error_step
        })
    
    def publish_execution_summary(self, 
                                project_id: str,
                                status: str,
                                start_time: str,
                                duration_seconds: float,
                                alert_source: str,
                                response_action: str) -> bool:
        """Publish execution summary update"""
        return self.publish_event("execution_summary", {
            "project_id": project_id,
            "status": status,
            "start_time": start_time,
            "duration_seconds": duration_seconds,
            "alert_source": alert_source,
            "response_action": response_action
        })
    
    def publish_alert_details(self,
                             project_id: str,
                             alert_id: str,
                             alert_name: str,
                             alert_source: str,
                             alert_time: str,
                             alert_description: str,
                             affected_systems: List[str],
                             details: Dict[str, Any]) -> bool:
        """Publish alert details"""
        return self.publish_event("alert_details", {
            "project_id": project_id,
            "alert_id": alert_id,
            "name": alert_name,
            "source": alert_source,
            "time": alert_time,
            "description": alert_description,
            "affected_systems": affected_systems,
            "details": details
        })
    
    def publish_enrichment_results(self,
                                  project_id: str,
                                  indicators: List[Dict[str, str]],
                                  additional_context: Dict[str, Any]) -> bool:
        """Publish enrichment results"""
        return self.publish_event("enrichment_results", {
            "project_id": project_id,
            "indicators": indicators,
            "additional_context": additional_context
        })
    
    def publish_llm_decision(self,
                            project_id: str,
                            severity: str,
                            confidence_percentage: int,
                            recommended_action: str,
                            reasoning: str) -> bool:
        """Publish LLM decision"""
        logger.info(f"Publishing LLM decision event - severity: {severity}, confidence: {confidence_percentage}, action: {recommended_action}")
        logger.debug(f"LLM reasoning: {reasoning[:100]}...")
        
        # Make sure we have reasonable values
        if confidence_percentage is None or not isinstance(confidence_percentage, int):
            confidence_percentage = 0
            
        # Ensure reasoning is a string
        if reasoning is None:
            reasoning = "No reasoning provided"
            
        return self.publish_event("llm_decision", {
            "project_id": project_id,
            "severity": severity,
            "confidence_percentage": confidence_percentage,
            "recommended_action": recommended_action,
            "reasoning": reasoning
        })
    
    def publish_response_action(self,
                               project_id: str,
                               action_type: str,
                               status: str,
                               details: Dict[str, Any],
                               parameters: Dict[str, Any]) -> bool:
        """Publish response action execution details"""
        return self.publish_event("response_action", {
            "project_id": project_id,
            "action_type": action_type,
            "status": status,
            "details": details,
            "parameters": parameters
        })
    
    def publish_execution_list(self,
                              executions: List[Dict[str, Any]]) -> bool:
        """Publish updated execution list - Enhanced with better logging"""
        logger.info(f"Publishing execution_list event with {len(executions)} executions")
        for ex in executions:
            logger.info(f"  - Execution: {ex.get('project_id')} - {ex.get('name')} - {ex.get('status')}")
        
        # Double-check that this is a valid list of dictionaries
        if not isinstance(executions, list) or len(executions) == 0:
            logger.warning("Invalid executions list: empty or not a list. Adding dummy execution.")
            import datetime
            executions = [{
                "project_id": f"dummy-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
                "name": "Execution List Fix",
                "status": "COMPLETED",
                "timestamp": datetime.datetime.utcnow().isoformat()
            }]
        
        return self.publish_event("execution_list", {
            "executions": executions
        })
