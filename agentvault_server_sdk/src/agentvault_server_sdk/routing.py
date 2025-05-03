# ... other imports ...
import logging
from typing import Any, Dict, Optional, List, Union, AsyncGenerator, Callable, TypeVar # Added AsyncGenerator, Callable, TypeVar
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks # Import BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
import json
import inspect # Added inspect
import pydantic # Added pydantic
from pydantic_core import ValidationError # Added pydantic_core

from .models import (
    JsonRpcRequest, JsonRpcResponse, JsonRpcError, ErrorCode,
    TaskSendParams, TaskGetParams, TaskCancelParams, SubscribeParams,
    A2AEvent, TaskStatusUpdateEvent # Ensure relevant models are imported
)
from .interfaces import BaseA2AAgent # Changed from .agent import BaseA2AAgent
from .state import BaseTaskStore
from .exceptions import AgentServerError, TaskNotFoundError, AgentProcessingError, ConfigurationError, A2AValidationError

# Assume models like Message are imported from agentvault core or defined here
try:
    from agentvault.models import Message, Task, TaskState, TaskSendResult, GetTaskResult, TaskCancelResult, TaskMessageEvent, TaskArtifactUpdateEvent, Artifact, TextPart # Added more core models
    _CORE_MODELS = True
except ImportError:
    # Define fallbacks if core library isn't available during SDK development/use
    class Message: pass # type: ignore
    class Task: pass # type: ignore
    class TaskState: pass # type: ignore
    class TaskSendResult: pass # type: ignore
    class GetTaskResult: pass # type: ignore
    class TaskCancelResult: pass # type: ignore
    class TaskMessageEvent: pass # type: ignore
    class TaskArtifactUpdateEvent: pass # type: ignore
    class Artifact: pass # type: ignore
    class TextPart: pass # type: ignore
    _CORE_MODELS = False


logger = logging.getLogger(__name__)

# --- Helper Function for JSON-RPC Response ---
def create_json_rpc_response(request_id: Optional[Union[str, int]], result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "result": result, "id": request_id}

def create_json_rpc_error(request_id: Optional[Union[str, int]], code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    error_obj = {"code": code, "message": message}
    if data:
        error_obj["data"] = data
    return {"jsonrpc": "2.0", "error": error_obj, "id": request_id}


# --- Router Creation Function ---
def create_a2a_router(
    agent: BaseA2AAgent,
    task_store: Optional[BaseTaskStore] = None,
    prefix: str = "",
    tags: Optional[List[str]] = None,
    dependencies: Optional[List[Depends]] = None,
) -> APIRouter:
    """
    Creates a FastAPI router with standard A2A endpoints, delegating logic to the provided agent instance.
    """
    effective_task_store = task_store or getattr(agent, 'task_store', None)
    if not effective_task_store:
         logger.warning("No task store provided or found on agent. SSE/Task management might be limited.")

    router = APIRouter(prefix=prefix, tags=tags, dependencies=dependencies or [])

    @router.post("", response_model=Dict[str, Any])
    @router.post("/", response_model=Dict[str, Any], include_in_schema=False)
    async def handle_a2a_request(
        request_body: JsonRpcRequest,
        request: Request,
        background_tasks: BackgroundTasks # Injected dependency
    ):
        """Handles incoming JSON-RPC requests for the A2A protocol."""
        request_id = request_body.id
        method = request_body.method
        params_dict = request_body.params or {}

        logger.info(f"Received A2A request: method='{method}', id='{request_id}'")
        logger.debug(f"Request params: {params_dict}")

        try:
            if method == "tasks/send":
                logger.warning("DEBUG: Entering tasks/send block in SDK router.") # Add log
                # --- TEMPORARY DEBUG ---
                # Bypass validation and complex logic, call directly
                mock_message = Message(role="debug", parts=[TextPart(content="debug_content")]) # Use real model if available
                logger.warning(f"DEBUG: Calling handle_task_send with background_tasks type: {type(background_tasks)}") # Add log
                try:
                    task_id_result: str = await agent.handle_task_send(
                        task_id=None, # Simulate new task
                        message=mock_message,
                        background_tasks=background_tasks # Pass the injected dependency
                    )
                    logger.warning(f"DEBUG: Call to handle_task_send returned: {task_id_result}") # Add log
                    response_data = {"id": task_id_result}
                    return create_json_rpc_response(request_id, response_data)
                except Exception as call_err:
                     logger.exception(f"DEBUG: Error calling handle_task_send directly: {call_err}") # Add log
                     # Let the generic error handlers below catch this
                     raise call_err
                # --- END TEMPORARY DEBUG ---

            elif method == "tasks/get":
                # ... (tasks/get logic - unchanged) ...
                if not effective_task_store:
                     raise ConfigurationError("TaskStore required for tasks/get")
                try:
                    validated_params = TaskGetParams.model_validate(params_dict)
                except Exception as e:
                    logger.error(f"Validation error for tasks/get params: {e}", exc_info=True)
                    raise A2AValidationError(f"Invalid params for tasks/get: {e}")

                task_result = await agent.handle_task_get(task_id=validated_params.id)
                return create_json_rpc_response(request_id, task_result)


            elif method == "tasks/cancel":
                # ... (tasks/cancel logic - unchanged) ...
                if not effective_task_store:
                     raise ConfigurationError("TaskStore required for tasks/cancel")
                try:
                    validated_params = TaskCancelParams.model_validate(params_dict)
                except Exception as e:
                    logger.error(f"Validation error for tasks/cancel params: {e}", exc_info=True)
                    raise A2AValidationError(f"Invalid params for tasks/cancel: {e}")

                success: bool = await agent.handle_task_cancel(task_id=validated_params.id)
                return create_json_rpc_response(request_id, {"success": success})


            elif method == "tasks/sendSubscribe":
                 # ... (tasks/sendSubscribe logic - unchanged, but uses the modified handle_task_send call) ...
                 try:
                     validated_params = TaskSendParams.model_validate(params_dict) # Reuse send params
                 except Exception as e:
                     logger.error(f"Validation error for tasks/sendSubscribe params: {e}", exc_info=True)
                     raise A2AValidationError(f"Invalid params for tasks/sendSubscribe: {e}")

                 task_id_result: str = await agent.handle_task_send(
                     task_id=validated_params.id,
                     message=validated_params.message,
                     background_tasks=background_tasks
                 )
                 response_data = {"id": task_id_result}
                 return create_json_rpc_response(request_id, response_data)

            else:
                logger.warning(f"Unsupported A2A method received: {method}")
                raise AgentProcessingError(f"Method '{method}' not supported.", code=ErrorCode.METHOD_NOT_FOUND)

        # --- Exception Handling (unchanged) ---
        except A2AValidationError as e:
             logger.error(f"A2A Validation Error: {e}", exc_info=True)
             return JSONResponse(status_code=400, content=create_json_rpc_error(request_id, ErrorCode.INVALID_PARAMS, str(e)))
        except TaskNotFoundError as e:
            logger.warning(f"Task not found: {e.task_id}")
            return JSONResponse(status_code=404, content=create_json_rpc_error(request_id, ErrorCode.RESOURCE_NOT_FOUND, str(e)))
        except ConfigurationError as e:
             logger.error(f"Agent Configuration Error: {e}", exc_info=True)
             return JSONResponse(status_code=500, content=create_json_rpc_error(request_id, ErrorCode.INTERNAL_ERROR, f"Agent configuration error: {e}"))
        except AgentProcessingError as e:
            logger.error(f"Agent Processing Error: {e}", exc_info=True)
            error_code = getattr(e, 'code', ErrorCode.INTERNAL_ERROR)
            return JSONResponse(status_code=500, content=create_json_rpc_error(request_id, error_code, f"Agent error: {e}"))
        except Exception as e:
            logger.exception(f"Unexpected internal server error processing A2A request id={request_id}")
            return JSONResponse(status_code=500, content=create_json_rpc_error(request_id, ErrorCode.INTERNAL_ERROR, f"Internal server error: {type(e).__name__}"))

    # --- SSE Endpoint (/subscribe) - unchanged ---
    @router.get("/subscribe", response_class=StreamingResponse)
    async def subscribe_to_task_events(task_id: str):
        # ... (SSE logic remains the same) ...
        if not effective_task_store:
            raise HTTPException(status_code=501, detail="SSE subscriptions not supported without a TaskStore.")

        logger.info(f"Received SSE subscription request for task_id: {task_id}")

        async def event_stream():
            try:
                async for event in agent.handle_subscribe_request(task_id):
                    event_type = getattr(event, 'event_type', 'message')
                    try:
                        if hasattr(event, 'model_dump_json'):
                             event_data_json = event.model_dump_json()
                        elif isinstance(event, dict):
                             event_data_json = json.dumps(event.get("data", {}))
                        elif isinstance(event, bytes) and event.startswith(b':'):
                             yield event
                             continue
                        else:
                             event_data_json = json.dumps(event)
                    except Exception as serial_err:
                         logger.error(f"SSE Error serializing event for task {task_id}: {serial_err}. Event: {event!r}")
                         event_type = "error"
                         event_data_json = json.dumps({"error": "Failed to serialize event data", "detail": str(serial_err)})

                    sse_message = f"event: {event_type}\ndata: {event_data_json}\n\n"
                    yield sse_message.encode('utf-8')
                    await asyncio.sleep(0.01)
            except TaskNotFoundError:
                 error_event = {"event_type": "error", "data": {"code": ErrorCode.RESOURCE_NOT_FOUND, "message": f"Task {task_id} not found or finished."}}
                 yield f"event: error\ndata: {json.dumps(error_event['data'])}\n\n".encode('utf-8')
            except asyncio.CancelledError:
                 logger.info(f"SSE stream cancelled by client for task {task_id}.")
            except Exception as e:
                 logger.exception(f"Unexpected error in SSE stream for task {task_id}")
                 try:
                     error_event = {"event_type": "error", "data": {"code": ErrorCode.INTERNAL_ERROR, "message": f"SSE stream error: {type(e).__name__}"}}
                     yield f"event: error\ndata: {json.dumps(error_event['data'])}\n\n".encode('utf-8')
                 except Exception:
                     pass
            finally:
                 logger.info(f"SSE event stream closing for task_id: {task_id}")

        return StreamingResponse(event_stream(), media_type="text/event-stream")


    return router
