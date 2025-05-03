"""
Adapter layer to provide proper FastAPI dependency injection for A2A methods.
"""
import logging
from typing import Dict, Any, Optional, Union

from fastapi import APIRouter, Request, Response, BackgroundTasks, Depends
from fastapi.responses import JSONResponse

from agentvault_server_sdk.agent import BaseA2AAgent

# Create the logger
logger = logging.getLogger(__name__)

def create_injection_router(agent_instance: BaseA2AAgent, prefix: str = "") -> APIRouter:
    """
    Creates a router with endpoints that properly inject BackgroundTasks for agent methods.
    
    Args:
        agent_instance: The agent instance to use
        prefix: URL prefix for the endpoints
        
    Returns:
        A FastAPI APIRouter with the endpoints
    """
    router = APIRouter(prefix=prefix)
    
    @router.post("/task/send")
    async def inject_background_tasks_endpoint(
        request: Request,
        background_tasks: BackgroundTasks
    ) -> JSONResponse:
        """
        Endpoint that properly injects BackgroundTasks into the A2A method call.
        Parses the JSON-RPC request, calls the agent's handle_task_send method with
        proper BackgroundTasks injection, and returns a JSON-RPC response.
        """
        try:
            # Parse the JSON-RPC payload
            payload = await request.json()
            logger.info(f"Received A2A payload: {payload}")
            
            # Basic JSON-RPC validation
            if not all(k in payload for k in ["jsonrpc", "method"]) or payload["jsonrpc"] != "2.0":
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32600, "message": "Invalid Request"},
                    "id": payload.get("id")
                }
                return JSONResponse(content=error_response)
                
            # Check method name (should be tasks/send for this endpoint)
            if payload["method"] != "tasks/send":
                error_response = {
                    "jsonrpc": "2.0", 
                    "error": {"code": -32601, "message": "Method not found"},
                    "id": payload.get("id")
                }
                return JSONResponse(content=error_response)
                
            # Extract parameters
            params = payload.get("params", {})
            task_id = params.get("id")  # ID field in params per A2A protocol
            message = params.get("message")
            
            if not message:
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Invalid params: missing message"},
                    "id": payload.get("id")
                }
                return JSONResponse(content=error_response)
            
            # Call the agent method WITH background_tasks
            logger.info(f"Calling handle_task_send with task_id={task_id}")
            result_task_id = await agent_instance.handle_task_send(
                task_id=task_id,
                message=message,
                background_tasks=background_tasks
            )
            
            # Return successful JSON-RPC response
            success_response = {
                "jsonrpc": "2.0",
                "result": {"id": result_task_id},
                "id": payload.get("id")
            }
            return JSONResponse(content=success_response)
            
        except Exception as e:
            logger.exception(f"Error in injection endpoint: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": f"Server error: {str(e)}"},
                "id": payload.get("id") if "payload" in locals() else None
            }
            return JSONResponse(content=error_response)
    
    return router