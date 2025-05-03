"""
Provides the AgentVaultClient for interacting with remote agents via the A2A protocol.

Note: Assumes a baseline A2A protocol version inspired by early drafts.
Future versions will need more robust version handling based on AgentCard capabilities.
"""

import asyncio
import json
import logging
import httpx
import typing
import uuid
# --- ADDED: Import pydantic_core ---
import pydantic
from pydantic_core import ValidationError as PydanticCoreValidationError
# --- END ADDED ---
import time
# --- ADDED: Import urlparse ---
from urllib.parse import urlparse, urlunparse
# --- END ADDED ---
from typing import Optional, Dict, Any, Union, AsyncGenerator, Tuple, List

# Import local models
from agentvault.models import (
    AgentCard, AgentAuthentication, Message, Task, TaskState, TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent, TaskMessageEvent, TaskSendParams, TaskSendResult,
    TaskGetParams, GetTaskResult, TaskCancelParams, TaskCancelResult, A2AEvent,
    TextPart, DataPart # Added DataPart
)
# Import local exceptions
from agentvault.exceptions import (
    AgentVaultError, A2AError, A2AConnectionError, A2AAuthenticationError,
    A2ARemoteAgentError, A2ATimeoutError, A2AMessageError, KeyManagementError
)
# Import KeyManager
from agentvault.key_manager import KeyManager
# Import MCP Utils
from agentvault.mcp_utils import format_mcp_context
# --- ADDED: Import respx for type hinting in _make_request ---
try:
    import respx
except ImportError:
    respx = None # type: ignore
# --- END ADDED ---


logger = logging.getLogger(__name__)

SSE_EVENT_TYPE_MAP = {
    "task_status": TaskStatusUpdateEvent,
    "task_message": TaskMessageEvent,
    "task_artifact": TaskArtifactUpdateEvent,
    "message": TaskMessageEvent, # Allow 'message' as an alias for task_message
    "error": dict
}


CACHE_EXPIRY_BUFFER_SECONDS = 60

class AgentVaultClient:
    """ Client for interacting with remote agents... """
    def __init__(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
        default_timeout: float = 30.0
    ):
        """Initializes the AgentVaultClient."""
        self.default_timeout = default_timeout
        if http_client:
            self._http_client = http_client
            self._should_close_client = False
            logger.debug("Using provided httpx.AsyncClient instance.")
        else:
            logger.debug(f"Creating internal httpx.AsyncClient instance with timeout {default_timeout}s.")
            self._http_client = httpx.AsyncClient(
                timeout=default_timeout,
                http2=True,
                follow_redirects=True # Ensure redirects are followed by default
            )
            self._should_close_client = True
        self._token_cache: Dict[str, Tuple[str, Optional[float]]] = {}


    async def close(self) -> None:
        """Closes the underlying HTTP client if it was created internally."""
        if self._should_close_client and hasattr(self, '_http_client') and self._http_client and not self._http_client.is_closed:
            logger.debug("Closing internally managed httpx.AsyncClient instance.")
            await self._http_client.aclose()
        elif not self._should_close_client:
             logger.debug("Using externally managed httpx.AsyncClient, not closing.")

    async def __aenter__(self) -> "AgentVaultClient":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager, ensuring the client is closed."""
        await self.close()

    # --- Public A2A Methods ---
    async def initiate_task(
        self, agent_card: AgentCard, initial_message: Message, key_manager: KeyManager,
        mcp_context: Optional[Dict[str, Any]] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        logger.info(f"Initiating task with agent: {agent_card.human_readable_id}")
        if webhook_url: logger.info(f"Webhook URL provided for push notifications: {webhook_url}")
        try:
            auth_headers = await self._get_auth_headers(agent_card, key_manager)
            message_to_send = initial_message
            if mcp_context:
                formatted_mcp = format_mcp_context(mcp_context)
                if formatted_mcp is not None:
                    current_metadata = message_to_send.metadata or {}
                    updated_metadata = {**current_metadata, "mcp_context": formatted_mcp}
                    # Use model_copy for immutable models if available
                    if hasattr(message_to_send, 'model_copy'):
                        message_to_send = message_to_send.model_copy(update={'metadata': updated_metadata})
                    else: # Fallback for mutable or older Pydantic
                         message_to_send.metadata = updated_metadata # type: ignore
                    logger.debug("Successfully formatted and embedded MCP context into message metadata.")
                else: logger.warning("Failed to format provided MCP context data. Proceeding without embedding it.")

            task_send_params = TaskSendParams(message=message_to_send, id=None)
            request_id = f"req-init-{uuid.uuid4()}"
            request_params_dict = task_send_params.model_dump(mode='json', exclude_none=True, by_alias=True)
            if webhook_url: request_params_dict['webhookUrl'] = webhook_url; logger.debug(f"Adding webhookUrl='{webhook_url}' to initiate task params.")
            request_payload = {"jsonrpc": "2.0", "method": "tasks/send", "params": request_params_dict, "id": request_id}
            logger.debug(f"Initiate task request payload (id: {request_id})")
            # Pass the original agent_card, _make_request handles URL conversion
            response_data = await self._make_request('POST', agent_card.url, headers=auth_headers, json_payload=request_payload, stream=False)
            try: result_obj = TaskSendResult.model_validate(response_data)
            except pydantic.ValidationError as e: raise A2AMessageError(f"Failed to validate task initiation result structure: {e}") from e
            task_id = result_obj.id
            if not task_id or not isinstance(task_id, str): raise A2AMessageError("Invalid response format: 'result.id' is missing, empty, or not a string.")
            logger.info(f"Task successfully initiated with agent {agent_card.human_readable_id}. Task ID: {task_id}")
            return task_id
        except (A2AAuthenticationError, A2AConnectionError, A2ARemoteAgentError, A2AMessageError, A2ATimeoutError) as e: logger.error(f"A2A error during task initiation: {type(e).__name__}: {e}"); raise
        except KeyManagementError as e: logger.error(f"Key management error during task initiation: {e}"); raise A2AAuthenticationError(f"Authentication failed due to key management error: {e}") from e
        except Exception as e: logger.exception(f"Unexpected error during task initiation with agent {agent_card.human_readable_id}: {e}"); raise A2AError(f"An unexpected error occurred during task initiation: {e}") from e

    async def send_message(
        self, agent_card: AgentCard, task_id: str, message: Message, key_manager: KeyManager,
        mcp_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        logger.info(f"Sending message to task {task_id} on agent: {agent_card.human_readable_id}")
        if not task_id or not isinstance(task_id, str): raise ValueError("Invalid task_id provided for send_message.")
        try:
            auth_headers = await self._get_auth_headers(agent_card, key_manager)
            message_to_send = message
            if mcp_context:
                formatted_mcp = format_mcp_context(mcp_context)
                if formatted_mcp is not None:
                    current_metadata = message_to_send.metadata or {}; updated_metadata = {**current_metadata, "mcp_context": formatted_mcp}
                    if hasattr(message_to_send, 'model_copy'):
                        message_to_send = message_to_send.model_copy(update={'metadata': updated_metadata})
                    else:
                         message_to_send.metadata = updated_metadata # type: ignore
                    logger.debug("Successfully formatted and embedded MCP context into message metadata.")
                else: logger.warning("Failed to format provided MCP context data. Proceeding without embedding it.")
            task_send_params = TaskSendParams(message=message_to_send, id=task_id)
            request_id = f"req-send-{uuid.uuid4()}"; request_params_dict = task_send_params.model_dump(mode='json', exclude_none=True, by_alias=True)
            request_payload = {"jsonrpc": "2.0", "method": "tasks/send", "params": request_params_dict, "id": request_id}
            logger.debug(f"Send message request payload (id: {request_id})")
            # Pass the original agent_card
            response_data = await self._make_request('POST', agent_card.url, headers=auth_headers, json_payload=request_payload, stream=False)
            try: TaskSendResult.model_validate(response_data)
            except pydantic.ValidationError as e: raise A2AMessageError(f"Failed to validate send message result structure: {e}") from e
            logger.info(f"Message successfully sent to task {task_id} on agent {agent_card.human_readable_id}.")
            return True
        except (A2AAuthenticationError, A2AConnectionError, A2ARemoteAgentError, A2AMessageError, A2ATimeoutError) as e: logger.error(f"A2A error sending message to task {task_id}: {type(e).__name__}: {e}"); raise
        except KeyManagementError as e: logger.error(f"Key management error sending message to task {task_id}: {e}"); raise A2AAuthenticationError(f"Authentication failed due to key management error: {e}") from e
        except Exception as e: logger.exception(f"Unexpected error sending message to task {task_id} on agent {agent_card.human_readable_id}: {e}"); raise A2AError(f"An unexpected error occurred sending message: {e}") from e

    async def get_task_status(
        self, agent_card: AgentCard, task_id: str, key_manager: KeyManager
    ) -> Task:
        logger.info(f"Getting status for task {task_id} on agent: {agent_card.human_readable_id}")
        if not task_id or not isinstance(task_id, str): raise ValueError("Invalid task_id provided for get_task_status.")
        try:
            auth_headers = await self._get_auth_headers(agent_card, key_manager)
            task_get_params = TaskGetParams(id=task_id)
            request_id = f"req-get-{uuid.uuid4()}"; request_params_dict = task_get_params.model_dump(mode='json', by_alias=True)
            request_payload = {"jsonrpc": "2.0", "method": "tasks/get", "params": request_params_dict, "id": request_id}
            logger.debug(f"Get task status request payload (id: {request_id})")
            # Pass the original agent_card
            response_data = await self._make_request('POST', agent_card.url, headers=auth_headers, json_payload=request_payload, stream=False)
            try:
                task_object = GetTaskResult.model_validate(response_data)
                logger.info(f"Successfully retrieved status for task {task_id}. State: {task_object.state}")
                return task_object
            except pydantic.ValidationError as e:
                raise A2AMessageError(f"Failed to validate task status result (Task model): {e}") from e
        except (A2AAuthenticationError, A2AConnectionError, A2ARemoteAgentError, A2AMessageError, A2ATimeoutError) as e: logger.error(f"A2A error getting status for task {task_id}: {type(e).__name__}: {e}"); raise
        except KeyManagementError as e: logger.error(f"Key management error getting status for task {task_id}: {e}"); raise A2AAuthenticationError(f"Authentication failed due to key management error: {e}") from e
        except Exception as e: logger.exception(f"Unexpected error getting status for task {task_id} on agent {agent_card.human_readable_id}: {e}"); raise A2AError(f"An unexpected error occurred getting task status: {e}") from e

    async def terminate_task(
        self, agent_card: AgentCard, task_id: str, key_manager: KeyManager
    ) -> bool:
        logger.info(f"Requesting termination for task {task_id} on agent: {agent_card.human_readable_id}")
        if not task_id or not isinstance(task_id, str): raise ValueError("Invalid task_id provided for terminate_task.")
        try:
            auth_headers = await self._get_auth_headers(agent_card, key_manager)
            task_cancel_params = TaskCancelParams(id=task_id)
            request_id = f"req-cancel-{uuid.uuid4()}"; request_params_dict = task_cancel_params.model_dump(mode='json', by_alias=True)
            request_payload = {"jsonrpc": "2.0", "method": "tasks/cancel", "params": request_params_dict, "id": request_id}
            logger.debug(f"Terminate task request payload (id: {request_id})")
            # Pass the original agent_card
            response_data = await self._make_request('POST', agent_card.url, headers=auth_headers, json_payload=request_payload, stream=False)
            try:
                result_obj = TaskCancelResult.model_validate(response_data)
                if not result_obj.success: logger.warning(f"Agent acknowledged termination request for task {task_id} but indicated failure (success=false). Message: {result_obj.message}")
            except pydantic.ValidationError as e: raise A2AMessageError(f"Failed to validate terminate task result structure: {e}") from e
            logger.info(f"Termination request for task {task_id} acknowledged by agent {agent_card.human_readable_id}.")
            return True
        except (A2AAuthenticationError, A2AConnectionError, A2ARemoteAgentError, A2AMessageError, A2ATimeoutError) as e: logger.error(f"A2A error terminating task {task_id}: {type(e).__name__}: {e}"); raise
        except KeyManagementError as e: logger.error(f"Key management error terminating task {task_id}: {e}"); raise A2AAuthenticationError(f"Authentication failed due to key management error: {e}") from e
        except Exception as e: logger.exception(f"Unexpected error terminating task {task_id} on agent {agent_card.human_readable_id}: {e}"); raise A2AError(f"An unexpected error occurred terminating task: {e}") from e


    async def receive_messages(
        self, agent_card: AgentCard, task_id: str, key_manager: KeyManager
    ) -> AsyncGenerator[A2AEvent, None]:
        """ Subscribes to Server-Sent Events (SSE)... """
        logger.info(f"Subscribing to events for task {task_id} on agent: {agent_card.human_readable_id}")
        if not task_id or not isinstance(task_id, str):
             raise ValueError("Invalid task_id provided for receive_messages.")

        # --- MODIFIED: Ensure trailing slash for SSE URL ---
        url_obj = urlparse(str(agent_card.url))
        path = url_obj.path
        if not path.endswith('/'):
            path += '/'
        url_str = urlunparse(url_obj._replace(path=path))
        logger.debug(f"Ensured SSE URL ends with slash: {url_str}")
        # --- END MODIFIED ---

        request_id = f"req-sub-{uuid.uuid4()}"
        request_payload = {
            "jsonrpc": "2.0",
            "method": "tasks/sendSubscribe",
            "params": {"id": task_id},
            "id": request_id
        }
        log_context = f"POST {url_str} (SSE Stream)"

        try:
            auth_headers = await self._get_auth_headers(agent_card, key_manager)
            auth_headers["Accept"] = "text/event-stream"
            auth_headers["Connection"] = "keep-alive"
            logger.debug(f"Subscribe request payload (id: {request_id})")

            # Initiate the streaming request
            async with self._http_client.stream(
                'POST', url_str, headers=auth_headers, json=request_payload, timeout=None # Use longer/no timeout for streams
            ) as response:
                response.raise_for_status()
                logger.info(f"SSE stream connection successful ({response.status_code}) for {log_context}. Reading lines...")

                async for event_dict in self._process_sse_stream_lines(response, log_context):
                    event_type = event_dict.get("event_type")
                    event_data = event_dict.get("data")

                    if not event_type or not isinstance(event_data, dict):
                        logger.warning(f"Skipping malformed event from SSE stream: {event_dict}")
                        continue

                    if event_type == "error":
                        err_msg = event_data.get('message', 'Unknown SSE error from agent')
                        logger.error(f"Received SSE error event from agent for task {task_id}: {err_msg}")
                        raise A2ARemoteAgentError(message=f"SSE error event received: {err_msg}", response_body=event_data)

                    event_model = SSE_EVENT_TYPE_MAP.get(event_type)
                    if not event_model:
                        logger.warning(f"Received unknown SSE event type: '{event_type}'. Data: {event_data}")
                        continue

                    try:
                        validated_event = event_model.model_validate(event_data)
                        logger.debug(f"Yielding validated event: {validated_event!r}")
                        yield validated_event
                    except (pydantic.ValidationError, PydanticCoreValidationError) as e:
                        logger.error(f"Failed to validate SSE event type '{event_type}': {e}. Data: {event_data}")
                        continue
                    except Exception as yield_err:
                        logger.error(f"Unexpected error yielding event type '{event_type}': {yield_err}", exc_info=True)
                        raise A2AError(f"Error processing received event: {yield_err}") from yield_err

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error establishing or during SSE stream {log_context}: {e.response.status_code}")
            try: error_body = e.response.json()
            except json.JSONDecodeError: error_body = e.response.text
            raise A2ARemoteAgentError(message=f"HTTP error {e.response.status_code} for {log_context}: {e.response.text}", status_code=e.response.status_code, response_body=error_body) from e
        except httpx.RequestError as e:
            logger.error(f"Network error during SSE stream {log_context}: {e}")
            raise A2AConnectionError(f"Network error during SSE stream: {e}") from e
        except (A2AAuthenticationError, A2ARemoteAgentError, A2AMessageError, A2ATimeoutError, A2AConnectionError) as e:
            logger.error(f"A2A error during event subscription or processing for task {task_id}: {type(e).__name__}: {e}")
            raise e
        except KeyManagementError as e:
             logger.error(f"Key management error during event subscription for task {task_id}: {e}")
             raise A2AAuthenticationError(f"Authentication failed due to key management error: {e}") from e
        except A2AError as e:
             logger.error(f"A2AError during event subscription processing for task {task_id}: {e}", exc_info=True)
             raise e
        except Exception as e:
            logger.exception(f"Unexpected error during event subscription for task {task_id} on agent {agent_card.human_readable_id}: {e}")
            raise A2AError(f"An unexpected error occurred during event subscription: {e}") from e
        finally:
             logger.debug(f"Finished receiving messages for task {task_id}.")


    # --- Private Helper Methods ---
    async def _get_auth_headers(self, agent_card: AgentCard, key_manager: KeyManager) -> Dict[str, str]:
        agent_schemes = agent_card.auth_schemes; supported_schemes_str = [s.scheme for s in agent_schemes]; logger.debug(f"Agent supports auth schemes: {supported_schemes_str}")
        api_key_scheme = next((s for s in agent_schemes if s.scheme == 'apiKey'), None)
        if api_key_scheme:
            service_id = api_key_scheme.service_identifier or agent_card.human_readable_id;
            if not service_id: raise A2AAuthenticationError(f"Cannot determine service identifier for apiKey scheme on agent {agent_card.human_readable_id}.")
            logger.debug(f"Attempting to retrieve key for service_id '{service_id}' using apiKey scheme.")
            api_key = key_manager.get_key(service_id)
            if not api_key: raise A2AAuthenticationError(f"Missing API key for service '{service_id}' required by agent '{agent_card.human_readable_id}' (scheme: apiKey). Check local configuration.")
            logger.debug(f"Using apiKey scheme for service_id '{service_id}'."); return {"X-Api-Key": api_key}
        oauth2_scheme = next((s for s in agent_schemes if s.scheme == 'oauth2'), None)
        if oauth2_scheme:
            logger.debug("Found 'oauth2' authentication scheme. Attempting Client Credentials Grant.")
            service_id = oauth2_scheme.service_identifier or agent_card.human_readable_id
            if not service_id: raise A2AAuthenticationError(f"Cannot determine service identifier for oauth2 scheme on agent {agent_card.human_readable_id}.")
            if not oauth2_scheme.token_url: raise A2AAuthenticationError(f"Agent card specifies oauth2 scheme but is missing 'tokenUrl' for agent {agent_card.human_readable_id}.")
            now = time.time(); cached_token_info = self._token_cache.get(service_id)
            if cached_token_info:
                token, expiry = cached_token_info
                if expiry is None or expiry > now: logger.debug(f"Using cached OAuth token for service '{service_id}'."); return {"Authorization": f"Bearer {token}"}
                else: logger.debug(f"Cached OAuth token for service '{service_id}' expired. Fetching new token.")
            logger.debug(f"Retrieving OAuth credentials for service_id '{service_id}'.")
            client_id = key_manager.get_oauth_client_id(service_id); client_secret = key_manager.get_oauth_client_secret(service_id)
            if not client_id or not client_secret: raise A2AAuthenticationError(f"Missing OAuth Client ID or Client Secret for service '{service_id}'. Check local configuration.")
            token_url_str = str(oauth2_scheme.token_url); token_data = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret,}
            if oauth2_scheme.scopes: token_data["scope"] = " ".join(oauth2_scheme.scopes)
            token_headers = {"Content-Type": "application/x-www-form-urlencoded"}; logger.debug(f"Requesting OAuth token from {token_url_str} for service '{service_id}'.")
            try:
                # Use the client's internal httpx client instance
                response = await self._http_client.request(method="POST", url=token_url_str, data=token_data, headers=token_headers, timeout=self.default_timeout); response.raise_for_status()
                try: token_response_data = response.json()
                except json.JSONDecodeError as e: logger.error(f"Failed to decode JSON response from token endpoint {token_url_str}: {e}. Response: {response.text[:200]}..."); raise A2AAuthenticationError(f"Invalid JSON response from token endpoint {token_url_str}: {e}") from e
                access_token = token_response_data.get("access_token"); token_type = token_response_data.get("token_type", "bearer")
                if not access_token or not isinstance(access_token, str): logger.error(f"Token response from {token_url_str} missing 'access_token'. Response: {token_response_data}"); raise A2AAuthenticationError(f"Invalid token response from {token_url_str}: missing 'access_token'.")
                if token_type.lower() != "bearer": logger.warning(f"Token response from {token_url_str} has non-Bearer token_type: '{token_type}'. Proceeding anyway.")
                logger.info(f"Successfully obtained OAuth token for service '{service_id}'.")
                expires_in = token_response_data.get("expires_in"); expiry_timestamp: Optional[float] = None
                if isinstance(expires_in, (int, float)) and expires_in > 0: expiry_timestamp = time.time() + expires_in - CACHE_EXPIRY_BUFFER_SECONDS; logger.debug(f"Caching token for service '{service_id}' with expiry {expiry_timestamp} (expires_in={expires_in}s).")
                else: logger.debug(f"Caching token for service '{service_id}' without expiry.")
                self._token_cache[service_id] = (access_token, expiry_timestamp); return {"Authorization": f"Bearer {access_token}"}
            except httpx.TimeoutException as e: logger.error(f"Timeout requesting OAuth token from {token_url_str}: {e}"); raise A2AAuthenticationError(f"Timeout connecting to token endpoint {token_url_str}.") from e
            except httpx.ConnectError as e: logger.error(f"Connection error requesting OAuth token from {token_url_str}: {e}"); raise A2AAuthenticationError(f"Could not connect to token endpoint {token_url_str}.") from e
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code; error_detail = e.response.text[:200]; logger.error(f"HTTP error {status_code} from token endpoint {token_url_str}: {error_detail}")
                if status_code in [400, 401, 403]: raise A2AAuthenticationError(f"Invalid credentials or request for token endpoint {token_url_str} (HTTP {status_code}): {error_detail}") from e
                else: raise A2AAuthenticationError(f"Token endpoint {token_url_str} returned server error (HTTP {status_code}): {error_detail}") from e
            except httpx.RequestError as e: logger.error(f"Network error requesting OAuth token from {token_url_str}: {e}"); raise A2AAuthenticationError(f"Network error communicating with token endpoint {token_url_str}: {e}") from e
            except Exception as e: logger.exception(f"Unexpected error during OAuth token request to {token_url_str}: {e}"); raise A2AAuthenticationError(f"Unexpected error during OAuth token request: {e}") from e
        none_scheme_present = any(s.scheme == 'none' for s in agent_schemes)
        if none_scheme_present: logger.debug("Using 'none' authentication scheme."); return {}
        client_supported = ['apiKey', 'oauth2', 'none']; log_msg = (f"No compatible authentication scheme found for agent {agent_card.human_readable_id}. Agent supports: {supported_schemes_str}. Client supports: {client_supported}."); logger.error(log_msg); raise A2AAuthenticationError(log_msg)


    async def _make_request(
        self, method: str, url: Union[str, httpx.URL], headers: Optional[Dict[str, str]] = None,
        json_payload: Optional[Dict[str, Any]] = None, stream: bool = False
    ) -> Union[Dict[str, Any], AsyncGenerator[Dict[str, Any], None]]: # Return type hint changed
        if stream:
            raise NotImplementedError("_make_request should not be called with stream=True")

        # --- MODIFIED: Ensure URL ends with slash if it's a base path ---
        url_str = str(url)
        parsed_url = urlparse(url_str)
        # Add trailing slash only if path is non-empty, has no extension, and no query/fragment
        if parsed_url.path and not parsed_url.path.endswith('/') and '.' not in parsed_url.path.split('/')[-1] and not parsed_url.query and not parsed_url.fragment:
             original_path = parsed_url.path
             new_path = original_path + '/'
             url_str = urlunparse(parsed_url._replace(path=new_path))
             logger.debug(f"Ensured URL path ends with slash: {original_path} -> {new_path}")
        # --- END MODIFIED ---

        request_kwargs = {"method": method, "url": url_str, "headers": headers or {}, "json": json_payload}
        log_context = f"{method} {url_str}"

        logger.debug(f"Making non-stream request: {log_context}");
        if json_payload: logger.debug(f"Request payload keys: {list(json_payload.keys())}")
        try:
            # --- MODIFIED: Explicitly follow redirects here ---
            response = await self._http_client.request(**request_kwargs, follow_redirects=True)
            # --- END MODIFIED ---
            response.raise_for_status() # Can raise httpx.HTTPStatusError
            try:
                response_data = response.json() # Can raise json.JSONDecodeError
                if not isinstance(response_data, dict): raise A2AMessageError(f"Invalid response format from {url_str}: Expected dictionary, got {type(response_data)}. Body: {response.text[:200]}...")
                if "error" in response_data:
                    error_obj = response_data["error"]
                    if isinstance(error_obj, dict): err_code = error_obj.get("code", -1); err_msg = error_obj.get("message", "Unknown remote agent error"); err_details = error_obj.get("data"); logger.error(f"Agent returned JSON-RPC error for {log_context}: code={err_code}, msg='{err_msg}', data={err_details}"); raise A2ARemoteAgentError(message=err_msg, status_code=err_code, response_body=err_details)
                    else: raise A2AMessageError(f"Invalid JSON-RPC error format from {url_str}: 'error' field is not a dictionary. Body: {response.text[:200]}...")
                elif "result" in response_data:
                    log_resp_str = f"size={len(response.content)} bytes, keys={list(response_data.get('result').keys())}" if isinstance(response_data.get('result'), dict) else f"size={len(response.content)} bytes"; logger.debug(f"Request successful ({response.status_code}) for {log_context}. Response: {log_resp_str}"); return response_data["result"]
                else: raise A2AMessageError(f"Invalid JSON-RPC response from {url_str}: Missing 'result' or 'error' key. Body: {response.text[:200]}...")
            except json.JSONDecodeError as e: logger.error(f"Failed to decode JSON response from {log_context}. Status: {response.status_code}. Response text: {response.text[:200]}..."); raise A2AMessageError(f"Failed to decode JSON response from {url_str}. Status: {response.status_code}. Body: {response.text[:200]}...") from e

        except httpx.TimeoutException as e: logger.error(f"Request timeout for {log_context}: {e}"); raise A2ATimeoutError(f"Request timed out for {url_str}: {e}") from e
        except httpx.ConnectError as e: logger.error(f"Connection error for {log_context}: {e}"); raise A2AConnectionError(f"Connection failed for {url_str}: {e}") from e
        except httpx.HTTPStatusError as e: logger.error(f"HTTP error on request {log_context}: {e.response.status_code}"); raise A2ARemoteAgentError(message=f"HTTP error {e.response.status_code} for {url_str}: {e.response.text}", status_code=e.response.status_code, response_body=e.response.text) from e
        except httpx.RequestError as e: logger.error(f"HTTP request error for {log_context}: {e}"); raise A2AConnectionError(f"HTTP request failed for {url_str}: {e}") from e
        except (A2AMessageError, A2AAuthenticationError, A2ARemoteAgentError) as e: logger.error(f"A2A error during request processing for {log_context}: {e}"); raise
        except respx.mock.MockError as e: # Use qualified name if respx is imported
             logger.warning(f"Respx mock error caught: {e}") # Log for debugging
             raise e
        except Exception as e: logger.exception(f"Unexpected error during request {log_context}: {e}"); raise A2AError(f"An unexpected error occurred during the request for {url_str}: {e}") from e

    async def _process_sse_stream_lines(self, response: httpx.Response, log_context: str) -> AsyncGenerator[Dict[str, Any], None]:
        """ Processes a Server-Sent Event line stream from an HTTP response. """
        current_event_type = None
        data_lines: List[str] = []
        processed_event_count = 0
        logger.info(f"Starting SSE stream line processing for: {log_context}")

        try:
            try:
                async for line in response.aiter_lines():
                    logger.debug(f"SSE Line Received: {line!r}")

                    if not line: # Empty line signifies end of an event
                        if data_lines:
                            event_type = current_event_type or "message"
                            full_data_str = '\n'.join(data_lines)
                            logger.debug(f"Dispatching SSE event: type='{event_type}', data_len={len(full_data_str)}")
                            parsed_data = None # Initialize for error logging
                            try:
                                parsed_data = json.loads(full_data_str) # Parse here
                                logger.debug(f"Yielding parsed data: {parsed_data}")
                                try:
                                    if event_type == "error":
                                        logger.error(f"Received SSE error event from agent: {parsed_data}")
                                        yield {"event_type": event_type, "data": parsed_data}
                                    elif event_type in SSE_EVENT_TYPE_MAP:
                                        yield {"event_type": event_type, "data": parsed_data} # Yield parsed data
                                    else:
                                        logger.warning(f"Ignoring unknown SSE event type before yield: '{event_type}'. Data: {parsed_data}")
                                except Exception as yield_err:
                                    logger.error(f"Error yielding parsed SSE event (type: {event_type}, data: {parsed_data}): {yield_err}", exc_info=True)
                                    raise A2AError(f"Error processing received event: {yield_err}") from yield_err
                                processed_event_count += 1
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to decode JSON data for SSE event type '{event_type}': {e}. Data: {full_data_str[:200]}...")
                                raise A2AMessageError(f"Invalid JSON in SSE data for event '{event_type}'") from e

                        data_lines = []
                        current_event_type = None
                        continue

                    if line.startswith(':'):
                        logger.debug("Ignoring SSE comment line.")
                        continue

                    try:
                        colon_pos = line.find(':')
                        if colon_pos == -1: logger.warning(f"Ignoring malformed SSE line (no colon): {line!r}"); continue
                        field = line[:colon_pos].strip()
                        value_start = colon_pos + 1
                        if value_start < len(line) and line[value_start] == ' ': value_start += 1
                        value = line[value_start:]

                        if field == "event": current_event_type = value
                        elif field == "data": data_lines.append(value)
                        else: logger.debug(f"Ignoring unknown SSE field: '{field}'")
                    except Exception as line_err:
                        logger.warning(f"Error processing SSE line '{line!r}': {line_err}")

            except httpx.RemoteProtocolError as e:
                 logger.error(f"Remote protocol error during SSE stream reading {log_context}: {e}")
                 raise A2AConnectionError(f"Stream connection error: {e}") from e
            except httpx.DecodingError as e:
                 logger.error(f"Decoding error during SSE stream reading {log_context}: {e}")
                 raise A2AMessageError(f"Stream decoding error: {e}") from e

            logger.debug("Finished iterating through SSE lines.")

            if data_lines: # Check for buffered data after loop finishes
                 logger.warning(f"Stream ended with non-empty data buffer, attempting dispatch: {data_lines}")
                 event_type = current_event_type or "message"; full_data_str = '\n'.join(data_lines)
                 try:
                     parsed_data = json.loads(full_data_str)
                     if event_type == "error":
                         logger.error(f"Received final SSE error event from agent: {parsed_data}")
                         yield {"event_type": event_type, "data": parsed_data}
                     elif event_type in SSE_EVENT_TYPE_MAP:
                         yield {"event_type": event_type, "data": parsed_data};
                     else:
                          logger.warning(f"Ignoring unknown final SSE event type: '{event_type}'. Data: {parsed_data}")
                     processed_event_count += 1
                 except json.JSONDecodeError as e: logger.error(f"Failed to decode JSON data for final SSE event type '{event_type}': {e}. Data: {full_data_str[:200]}...")

        except httpx.RequestError as e:
            logger.error(f"Network error during SSE stream reading {log_context}: {e}")
            raise A2AConnectionError(f"Network error during SSE stream: {e}") from e
        except json.JSONDecodeError as e:
             logger.error(f"Fatal JSON decode error processing SSE stream {log_context}: {e}", exc_info=True)
             raise A2AMessageError(f"Invalid JSON structure in SSE stream: {e}") from e
        except (pydantic.ValidationError, PydanticCoreValidationError) as e:
            logger.error(f"Pydantic validation error processing SSE stream {log_context}: {e}", exc_info=True)
            raise A2AMessageError(f"Invalid event data structure received in SSE stream: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error processing SSE stream lines {log_context}: {e}", exc_info=True)
            try:
                error_data = {"error": "stream_processing_error", "message": f"Error processing stream: {type(e).__name__}"}
                yield {"event_type": "error", "data": error_data}
                processed_event_count += 1
            except Exception as format_err:
                 logger.error(f"Failed to yield SSE processing error event: {format_err}")
            if isinstance(e, A2AError): raise e
            else: raise A2AError(f"An unexpected error occurred during SSE stream processing: {e}") from e
        finally:
            logger.info(f"SSE line stream processing finished for {log_context}. Processed {processed_event_count} events.")
