import pytest
import respx
import json
import uuid
import datetime
import asyncio
import re
import httpx
from unittest.mock import patch, MagicMock, ANY, call, AsyncMock
from freezegun import freeze_time
from typing import Optional, Dict, Any, Union, Tuple, List, AsyncGenerator


# Import client, models, exceptions, and KeyManager
from agentvault.client import AgentVaultClient, A2AEvent, CACHE_EXPIRY_BUFFER_SECONDS
from agentvault.key_manager import KeyManager
from agentvault.models import (
    AgentCard, AgentProvider, AgentCapabilities, AgentAuthentication, Message, TextPart,
    Task, TaskState, TaskSendResult, TaskCancelResult,
    TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent, Artifact
)
from agentvault.exceptions import (
    AgentVaultError, A2AError, A2AConnectionError, A2AAuthenticationError,
    A2ARemoteAgentError, A2ATimeoutError, A2AMessageError, KeyManagementError
)
# Import testing utils
from agentvault_testing_utils.fixtures import mock_a2a_server, MockServerInfo
from agentvault_testing_utils.mock_server import (
    create_jsonrpc_error_response,
    create_jsonrpc_success_response,
    setup_mock_a2a_routes,
    DEFAULT_OAUTH_TOKEN_RESPONSE,
    create_default_mock_task,
    JSONRPC_PARSE_ERROR, JSONRPC_INVALID_REQUEST, JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_APP_ERROR, JSONRPC_INVALID_PARAMS, JSONRPC_INTERNAL_ERROR, JSONRPC_TASK_NOT_FOUND
)

import logging

# Check if agentvault models are available
try:
    import agentvault.models
    _AGENTVAULT_IMPORTED = True
except ImportError:
    _AGENTVAULT_IMPORTED = False

# --- Fixtures ---
# Use fixtures defined in conftest.py implicitly

@pytest.fixture
def mock_key_manager(mocker) -> MagicMock:
    """Provides a mock KeyManager instance."""
    mock_km = MagicMock(spec=KeyManager)
    mock_km.get_key.return_value = "test-key-123" # Default API Key for tests
    mock_km.get_oauth_client_id.return_value = "oauth-client-id-123" # Default OAuth ID
    mock_km.get_oauth_client_secret.return_value = "oauth-client-secret-xyz" # Default OAuth Secret
    return mock_km

@pytest.fixture
def sample_message() -> Message:
    """Provides a sample Message object."""
    return Message(role="user", parts=[TextPart(content="Hello Agent")])

@pytest.fixture
def agent_card_apikey(mock_a2a_server: MockServerInfo) -> AgentCard:
    """Provides an AgentCard instance supporting only apiKey."""
    return AgentCard(
        schemaVersion="1.0", humanReadableId="test-org/apikey-agent", agentVersion="1.0.0",
        name="API Key Test Agent", description="Agent for testing api key auth.",
        url=f"{mock_a2a_server.base_url}/a2a", # Use URL from fixture
        provider=AgentProvider(name="Test Suite Inc."), capabilities=AgentCapabilities(a2aVersion="1.0"),
        authSchemes=[AgentAuthentication(scheme="apiKey", service_identifier="test-service-apikey")]
    )

@pytest.fixture
def agent_card_no_auth(mock_a2a_server: MockServerInfo) -> AgentCard:
     """Provides an AgentCard instance supporting only none auth."""
     return AgentCard(
        schemaVersion="1.0", humanReadableId="test-org/no-auth-agent", agentVersion="1.0.0",
        name="No Auth Test Agent", description="Agent for testing no auth.",
        url=f"{mock_a2a_server.base_url}/a2a", # Use URL from fixture
        provider=AgentProvider(name="Test Suite Inc."), capabilities=AgentCapabilities(a2aVersion="1.0"),
        authSchemes=[AgentAuthentication(scheme="none")]
    )

@pytest.fixture
def agent_card_oauth2(mock_a2a_server: MockServerInfo) -> AgentCard:
    """Provides an AgentCard instance supporting only OAuth2."""
    return AgentCard(
        schemaVersion="1.0", humanReadableId="test-org/oauth2-agent", agentVersion="1.0.0",
        name="OAuth2 Test Agent", description="Agent for testing oauth2 auth.",
        url=f"{mock_a2a_server.base_url}/a2a", # Use URL from fixture
        provider=AgentProvider(name="Test Suite Inc."), capabilities=AgentCapabilities(a2aVersion="1.0"),
        authSchemes=[AgentAuthentication(
            scheme="oauth2",
            tokenUrl=f"{mock_a2a_server.base_url}/token", # Use token URL from fixture
            scopes=["tasks:read"],
            service_identifier="test-service-oauth"
        )]
    )


# --- Helper Async Generator Functions ---
async def mock_aiter_lines(lines: List[str]) -> AsyncGenerator[str, None]:
    for line in lines:
        yield line
        await asyncio.sleep(0) # Yield control

async def mock_receive_empty() -> AsyncGenerator[Any, None]:
    if False: yield
    return

async def mock_receive_events(*events) -> AsyncGenerator[Any, None]:
    """Async generator that yields mock events with a delay."""
    test_logger = logging.getLogger("test_mock_receive_events")
    test_logger.info(f"Mock generator starting. Will yield {len(events)} events.")
    for i, event in enumerate(events):
        media_type_to_log = "N/A"
        if _AGENTVAULT_IMPORTED and isinstance(event, TaskArtifactUpdateEvent):
             if hasattr(event, 'artifact') and hasattr(event.artifact, 'media_type'):
                 media_type_to_log = event.artifact.media_type
        test_logger.info(f"Mock generator yielding event {i+1}: type={type(event).__name__}, media_type='{media_type_to_log}'")
        yield event
        await asyncio.sleep(0.01)
    test_logger.info("Mock generator finished yielding events.")

# --- Test Init and Context Manager ---
@pytest.mark.asyncio
async def test_client_init_and_close():
    """Test client initialization and explicit close."""
    client = AgentVaultClient()
    assert isinstance(client._http_client, httpx.AsyncClient)
    assert client._should_close_client is True
    assert not client._http_client.is_closed
    await client.close()
    assert client._http_client.is_closed

@pytest.mark.asyncio
async def test_client_init_with_external_client():
    """Test client initialization with an external httpx client."""
    async with httpx.AsyncClient() as external_client:
        client = AgentVaultClient(http_client=external_client)
        assert client._http_client is external_client
        assert client._should_close_client is False
        await client.close() # Should not close the external client
        assert not external_client.is_closed
    assert external_client.is_closed # Closed by its own context manager

@pytest.mark.asyncio
async def test_client_async_context_manager():
    """Test client usage as an async context manager."""
    async with AgentVaultClient() as client:
        assert isinstance(client._http_client, httpx.AsyncClient)
        assert not client._http_client.is_closed
    assert client._http_client.is_closed # Should be closed on exit

# --- Test _get_auth_headers ---
@pytest.mark.asyncio
async def test_get_auth_headers_none(mock_key_manager, agent_card_no_auth):
    """Test getting headers when agent uses 'none' auth."""
    async with AgentVaultClient() as client:
        headers = await client._get_auth_headers(agent_card_no_auth, mock_key_manager)
    assert headers == {}
    mock_key_manager.get_key.assert_not_called()
    mock_key_manager.get_oauth_client_id.assert_not_called()

@pytest.mark.asyncio
async def test_get_auth_headers_apikey_success(mock_key_manager, agent_card_apikey):
    """Test getting headers when agent uses 'apiKey' and key is found."""
    mock_key_manager.get_key.return_value = "found-api-key"
    async with AgentVaultClient() as client:
        headers = await client._get_auth_headers(agent_card_apikey, mock_key_manager)
    assert headers == {"X-Api-Key": "found-api-key"}
    mock_key_manager.get_key.assert_called_once_with("test-service-apikey")

@pytest.mark.asyncio
async def test_get_auth_headers_apikey_missing(mock_key_manager, agent_card_apikey):
    """Test error when agent uses 'apiKey' and key is missing."""
    mock_key_manager.get_key.return_value = None
    with pytest.raises(A2AAuthenticationError, match="Missing API key"):
        async with AgentVaultClient() as client:
            await client._get_auth_headers(agent_card_apikey, mock_key_manager)
    mock_key_manager.get_key.assert_called_once_with("test-service-apikey")

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_success(mock_key_manager, agent_card_oauth2, mock_a2a_server: MockServerInfo):
    """Test getting headers when agent uses 'oauth2' and token fetch succeeds."""
    mock_key_manager.get_oauth_client_id.return_value = "test-client-id-123"
    mock_key_manager.get_oauth_client_secret.return_value = "test-client-secret-xyz"
    
    token_url = str(agent_card_oauth2.auth_schemes[0].token_url)
    async with respx.mock(using="httpx") as respx_mock_context:
        # Setup the token route *within* the context
        token_route = respx_mock_context.post(token_url).mock(
            return_value=httpx.Response(200, json=DEFAULT_OAUTH_TOKEN_RESPONSE)
        )
        # Instantiate and use the client *within* the context
        async with AgentVaultClient() as client:
            headers = await client._get_auth_headers(agent_card_oauth2, mock_key_manager)

    assert headers == {"Authorization": f"Bearer {DEFAULT_OAUTH_TOKEN_RESPONSE['access_token']}"}
    mock_key_manager.get_oauth_client_id.assert_called_once_with("test-service-oauth")
    mock_key_manager.get_oauth_client_secret.assert_called_once_with("test-service-oauth")
    # Check token endpoint was called via respx
    assert token_route.called

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_missing_creds(mock_key_manager, agent_card_oauth2):
    """Test error when agent uses 'oauth2' and client creds are missing."""
    mock_key_manager.get_oauth_client_id.return_value = "test-client-id-123"
    mock_key_manager.get_oauth_client_secret.return_value = None # Secret missing
    with pytest.raises(A2AAuthenticationError, match="Missing OAuth Client ID or Client Secret"):
        async with AgentVaultClient() as client:
            await client._get_auth_headers(agent_card_oauth2, mock_key_manager)
    mock_key_manager.get_oauth_client_id.assert_called_once_with("test-service-oauth")
    mock_key_manager.get_oauth_client_secret.assert_called_once_with("test-service-oauth")

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_token_endpoint_error(mock_key_manager, agent_card_oauth2, mock_a2a_server: MockServerInfo):
    """Test error when agent uses 'oauth2' and token endpoint returns error."""
    mock_key_manager.get_oauth_client_id.return_value = "test-client-id-123"
    mock_key_manager.get_oauth_client_secret.return_value = "test-client-secret-xyz"
    
    token_url = str(agent_card_oauth2.auth_schemes[0].token_url)
    async with respx.mock(using="httpx") as respx_mock_context:
        # Mock the token endpoint to return 401
        token_route = respx_mock_context.post(token_url).mock(
            return_value=httpx.Response(401, json={"error": "invalid_client"})
        )

        with pytest.raises(A2AAuthenticationError, match="Invalid credentials or request"):
            async with AgentVaultClient() as client:
                await client._get_auth_headers(agent_card_oauth2, mock_key_manager)
    
    assert token_route.called # Verify token endpoint was called

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_cached_token(mock_key_manager, agent_card_oauth2, mock_a2a_server: MockServerInfo):
    """Test using a valid cached OAuth2 token."""
    service_id = agent_card_oauth2.auth_schemes[0].service_identifier
    cached_token = "cached_valid_token"
    # Set expiry far in the future
    expiry = datetime.datetime.now(datetime.timezone.utc).timestamp() + 3600

    async with AgentVaultClient() as client:
        # Manually insert token into client's cache
        client._token_cache[service_id] = (cached_token, expiry)
        headers = await client._get_auth_headers(agent_card_oauth2, mock_key_manager)

    assert headers == {"Authorization": f"Bearer {cached_token}"}
    # Key manager shouldn't be called either if token is cached
    mock_key_manager.get_oauth_client_id.assert_not_called()
    mock_key_manager.get_oauth_client_secret.assert_not_called()

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_expired_token(mock_key_manager, agent_card_oauth2, mock_a2a_server: MockServerInfo):
    """Test fetching a new token when the cached one is expired."""
    token_url = str(agent_card_oauth2.auth_schemes[0].token_url)
    service_id = agent_card_oauth2.auth_schemes[0].service_identifier
    cached_token = "expired_token"
    new_token = "newly_fetched_token"
    # Set expiry in the past
    expiry = datetime.datetime.now(datetime.timezone.utc).timestamp() - 7200

    async with respx.mock(using="httpx") as respx_mock_context:
        # Mock token endpoint to return the new token
        token_route = respx_mock_context.post(token_url).mock(
            return_value=httpx.Response(200, json={"access_token": new_token, "token_type": "Bearer", "expires_in": 3600})
        )
        async with AgentVaultClient() as client:
            # Manually insert expired token into cache
            client._token_cache[service_id] = (cached_token, expiry)
            headers = await client._get_auth_headers(agent_card_oauth2, mock_key_manager)

    assert headers == {"Authorization": f"Bearer {new_token}"}
    assert token_route.called # Ensure token endpoint WAS called
    # Key manager should be called now
    mock_key_manager.get_oauth_client_id.assert_called_once_with(service_id)
    mock_key_manager.get_oauth_client_secret.assert_called_once_with(service_id)
    # Check cache was updated
    assert client._token_cache[service_id][0] == new_token
    assert client._token_cache[service_id][1] > expiry

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_no_token_url(mock_key_manager, agent_card_oauth2):
    """Test error when agent card is missing the tokenUrl for oauth2."""
    import copy
    test_card_copy = copy.deepcopy(agent_card_oauth2)
    test_card_copy.auth_schemes[0].token_url = None # Set token_url to None *after* creation

    with pytest.raises(A2AAuthenticationError, match="missing 'tokenUrl'"):
        async with AgentVaultClient() as client:
            # Pass the modified card object
            await client._get_auth_headers(test_card_copy, mock_key_manager)

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_token_network_error(mock_key_manager, agent_card_oauth2, mock_a2a_server: MockServerInfo):
    """Test network error during token fetch."""
    token_url = str(agent_card_oauth2.auth_schemes[0].token_url)
    async with respx.mock(using="httpx") as respx_mock_context:
        token_route = respx_mock_context.post(token_url).mock(side_effect=httpx.ConnectError("Connection refused"))
        with pytest.raises(A2AAuthenticationError, match="Could not connect to token endpoint"):
            async with AgentVaultClient() as client:
                await client._get_auth_headers(agent_card_oauth2, mock_key_manager)
    assert token_route.called

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_token_timeout(mock_key_manager, agent_card_oauth2, mock_a2a_server: MockServerInfo):
    """Test timeout during token fetch."""
    token_url = str(agent_card_oauth2.auth_schemes[0].token_url)
    async with respx.mock(using="httpx") as respx_mock_context:
        token_route = respx_mock_context.post(token_url).mock(side_effect=httpx.TimeoutException("Timeout occurred", request=None))
        with pytest.raises(A2AAuthenticationError, match="Timeout connecting to token endpoint"):
            async with AgentVaultClient() as client:
                await client._get_auth_headers(agent_card_oauth2, mock_key_manager)
    assert token_route.called

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_token_invalid_json(mock_key_manager, agent_card_oauth2, mock_a2a_server: MockServerInfo):
    """Test invalid JSON response from token endpoint."""
    token_url = str(agent_card_oauth2.auth_schemes[0].token_url)
    async with respx.mock(using="httpx") as respx_mock_context:
        token_route = respx_mock_context.post(token_url).mock(return_value=httpx.Response(200, text="{invalid json"))
        with pytest.raises(A2AAuthenticationError, match="Invalid JSON response from token endpoint"):
            async with AgentVaultClient() as client:
                await client._get_auth_headers(agent_card_oauth2, mock_key_manager)
    assert token_route.called

@pytest.mark.asyncio
async def test_get_auth_headers_oauth2_token_missing_access_token(mock_key_manager, agent_card_oauth2, mock_a2a_server: MockServerInfo):
    """Test token response missing the 'access_token' field."""
    token_url = str(agent_card_oauth2.auth_schemes[0].token_url)
    async with respx.mock(using="httpx") as respx_mock_context:
        token_route = respx_mock_context.post(token_url).mock(return_value=httpx.Response(200, json={"token_type": "Bearer"})) # Missing access_token
        with pytest.raises(A2AAuthenticationError, match="missing 'access_token'"):
            async with AgentVaultClient() as client:
                await client._get_auth_headers(agent_card_oauth2, mock_key_manager)
    assert token_route.called

# --- Test initiate_task ---
@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_initiate_task_success(mock_key_manager, agent_card_no_auth, sample_message, mock_a2a_server: MockServerInfo):
    """Test successful task initiation."""
    task_id = "new-mock-task-1"
    a2a_url = str(agent_card_no_auth.url)
    
    async with respx.mock(using="httpx") as respx_mock:
        a2a_route = respx_mock.post(a2a_url).mock(
            return_value=httpx.Response(200, json=create_jsonrpc_success_response("req-init-uuid", {"id": task_id}))
        )
        async with AgentVaultClient() as client:
            returned_id = await client.initiate_task(agent_card_no_auth, sample_message, mock_key_manager)
        
        assert returned_id == task_id
        assert a2a_route.called

# --- Test send_message ---
@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_send_message_success(mock_key_manager, agent_card_no_auth, sample_message, mock_a2a_server: MockServerInfo):
    """Test successfully sending a message to an existing task."""
    task_id = "existing-task-send"
    a2a_url = str(agent_card_no_auth.url)
    
    async with respx.mock(using="httpx") as respx_mock:
        a2a_route = respx_mock.post(a2a_url).mock(
            return_value=httpx.Response(200, json=create_jsonrpc_success_response("req-send-uuid", {"id": task_id}))
        )
        async with AgentVaultClient() as client:
            result = await client.send_message(agent_card_no_auth, task_id, sample_message, mock_key_manager)
        
        assert result is True
        assert a2a_route.called

# --- Test get_task_status ---
@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_get_task_status_success(mock_key_manager, agent_card_no_auth, mock_a2a_server: MockServerInfo):
    """Test successfully getting task status."""
    task_id = "existing-task-get"
    mock_task_data = create_default_mock_task(task_id, state=TaskState.WORKING)
    a2a_url = str(agent_card_no_auth.url)
    
    async with respx.mock(using="httpx") as respx_mock:
        a2a_route = respx_mock.post(a2a_url).mock(
            return_value=httpx.Response(200, json=create_jsonrpc_success_response("req-get-uuid", mock_task_data))
        )
        async with AgentVaultClient() as client:
            task_result = await client.get_task_status(agent_card_no_auth, task_id, mock_key_manager)
        
        assert isinstance(task_result, Task)
        assert task_result.id == task_id
        assert task_result.state == TaskState.WORKING
        assert a2a_route.called

# --- Test terminate_task ---
@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_terminate_task_success(mock_key_manager, agent_card_no_auth, mock_a2a_server: MockServerInfo):
    """Test successfully terminating a task."""
    task_id = "existing-task-term"
    a2a_url = str(agent_card_no_auth.url)
    
    async with respx.mock(using="httpx") as respx_mock:
        a2a_route = respx_mock.post(a2a_url).mock(
            return_value=httpx.Response(200, json=create_jsonrpc_success_response("req-cancel-uuid", {"success": True}))
        )
        async with AgentVaultClient() as client:
            result = await client.terminate_task(agent_card_no_auth, task_id, mock_key_manager)
        
        assert result is True
        assert a2a_route.called

# --- Test receive_messages ---
@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_receive_messages_success(mock_a2a_server: MockServerInfo, agent_card_apikey: AgentCard, mock_key_manager):
    """Test successful SSE stream processing."""
    task_id = "existing-task-sse"
    mock_a2a_server.task_store[task_id] = {"state": TaskState.WORKING} # Ensure task exists

    # Configure events to be streamed via the fixture's store
    now = datetime.datetime.now(datetime.timezone.utc)
    event1 = TaskStatusUpdateEvent(taskId=task_id, state=TaskState.WORKING, timestamp=now)
    event2 = TaskMessageEvent(taskId=task_id, message=Message(role="assistant", parts=[TextPart(content="SSE Message")]), timestamp=now)
    mock_a2a_server.sse_event_store[task_id] = [event1, event2] # Store events

    received_events = []
    logging.info("Starting test_receive_messages_success loop...")
    
    async with respx.mock(using="httpx") as respx_mock:
        async with AgentVaultClient() as client:
            async for event in client.receive_messages(agent_card_apikey, task_id, mock_key_manager):
                logging.info(f"Test received event: {type(event)} - {event}")
                received_events.append(event)

    logging.info(f"Finished test_receive_messages_success loop. Received {len(received_events)} events.")

    assert len(received_events) == 2, f"Expected 2 events, but received {len(received_events)}"
    assert isinstance(received_events[0], TaskStatusUpdateEvent)
    assert received_events[0].state == TaskState.WORKING
    assert isinstance(received_events[1], TaskMessageEvent)
    assert isinstance(received_events[1].message.parts[0], TextPart)
    assert received_events[1].message.parts[0].content == "SSE Message"

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_receive_messages_stream_error(mock_a2a_server: MockServerInfo, agent_card_apikey: AgentCard, mock_key_manager, mocker):
    """Test handling of error during SSE stream processing."""
    task_id = "existing-task-sse-err"
    mock_a2a_server.task_store[task_id] = {"state": TaskState.WORKING}
    mock_a2a_server.sse_event_store[task_id] = []

    error_message = "Simulated connection error during stream."
    error_to_raise = A2AConnectionError(error_message)

    async def mock_generator_that_raises(*args, **kwargs):
        # This generator immediately raises the exception when iterated
        raise error_to_raise
        if False: # Make it a generator type
             yield

    # Patch the helper method directly
    mock_process_lines = mocker.patch(
        "agentvault.client.AgentVaultClient._process_sse_stream_lines",
        new=mock_generator_that_raises
    )

    received_events = []
    
    async with respx.mock(using="httpx") as respx_mock:
        with pytest.raises(A2AConnectionError) as excinfo:
            async with AgentVaultClient() as client:
                async for event in client.receive_messages(agent_card_apikey, task_id, mock_key_manager):
                    received_events.append(event)

    # Assert the exception is the expected type
    assert isinstance(excinfo.value, A2AConnectionError)
    # Assert the error message is correct
    assert error_message in str(excinfo.value)

    assert len(received_events) == 0

# --- Tests for _process_sse_stream_lines ---
@pytest.mark.asyncio
async def test_process_sse_lines_valid_events():
    """Test parsing multiple valid SSE events."""
    lines = [
        "event: task_status",
        'data: {"taskId": "t1", "state": "WORKING", "timestamp": "2024-01-01T10:00:00Z"}',
        "",
        ": this is a comment",
        'data: {"taskId": "t1", "message": {"role": "assistant", "parts": [{"type": "text", "content": "Hi"}]}}',
        "",
        "event: task_artifact",
        'data: {"taskId": "t1", "artifact": {"id": "a1", "type": "log", "content": "Log line"}}',
        ""
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.aiter_lines.return_value = mock_aiter_lines(lines)
    client = AgentVaultClient()
    results = [item async for item in client._process_sse_stream_lines(mock_response, "test_ctx")]

    assert len(results) == 3
    assert results[0] == {"event_type": "task_status", "data": {"taskId": "t1", "state": "WORKING", "timestamp": "2024-01-01T10:00:00Z"}}
    assert results[1] == {"event_type": "message", "data": {"taskId": "t1", "message": {"role": "assistant", "parts": [{"type": "text", "content": "Hi"}]}}}
    assert results[2] == {"event_type": "task_artifact", "data": {"taskId": "t1", "artifact": {"id": "a1", "type": "log", "content": "Log line"}}}

@pytest.mark.asyncio
async def test_process_sse_lines_multiline_data():
    """Test parsing data split across multiple lines."""
    lines = [
        "event: task_message",
        'data: {"taskId": "t2", "message": {',
        'data: "role": "assistant",',
        'data: "parts": [{"type": "text", "content": "Multi\\\\nline"}]}}',
        ""
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.aiter_lines.return_value = mock_aiter_lines(lines)
    client = AgentVaultClient()
    results = [item async for item in client._process_sse_stream_lines(mock_response, "test_ctx")]

    assert len(results) == 1
    assert results[0]["event_type"] == "task_message"
    assert results[0]["data"]["message"]["parts"][0]["content"] == "Multi\\nline"

@pytest.mark.asyncio
async def test_process_sse_lines_ignore_malformed():
    """Test ignoring lines without colons and unknown fields."""
    lines = [
        "event: task_status",
        'data: {"taskId": "t3", "state": "WORKING"}',
        "",
        "this line has no colon",
        "id: 12345", # Unknown field
        "retry: 10000", # Unknown field
        'data: {"taskId": "t3", "message": {"role": "user"}}', # Valid data after bad lines
        ""
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.aiter_lines.return_value = mock_aiter_lines(lines)
    client = AgentVaultClient()
    results = [item async for item in client._process_sse_stream_lines(mock_response, "test_ctx")]

    assert len(results) == 2 # Only the two valid events should be yielded
    assert results[0]["event_type"] == "task_status"
    assert results[1]["event_type"] == "message" # Default type

@pytest.mark.asyncio
async def test_process_sse_lines_invalid_json_data():
    """Test raising A2AMessageError for invalid JSON in data field."""
    lines = [
        "event: task_status",
        'data: {"taskId": "t4", "state": "WORKING",}', # Invalid JSON (trailing comma)
        ""
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.aiter_lines.return_value = mock_aiter_lines(lines)
    client = AgentVaultClient()

    with pytest.raises(A2AMessageError, match="Invalid JSON in SSE data"):
        async for _ in client._process_sse_stream_lines(mock_response, "test_ctx"):
            pass # Consume generator

@pytest.mark.asyncio
async def test_process_sse_lines_unknown_event_type():
    """Test handling of unknown event types."""
    lines = [
        "event: custom_event",
        'data: {"info": "some custom data"}',
        ""
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.aiter_lines.return_value = mock_aiter_lines(lines)
    client = AgentVaultClient()
    # Should log a warning but not yield or raise error
    results = [item async for item in client._process_sse_stream_lines(mock_response, "test_ctx")]
    assert len(results) == 0 # Corrected code should skip this

@pytest.mark.asyncio
async def test_process_sse_lines_final_data_no_newline():
    """Test handling data buffered when stream ends without final newline."""
    lines = [
        "event: task_status",
        'data: {"taskId": "t5", "state": "COMPLETED"}' # No trailing empty line
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.aiter_lines.return_value = mock_aiter_lines(lines)
    client = AgentVaultClient()
    results = [item async for item in client._process_sse_stream_lines(mock_response, "test_ctx")]

    assert len(results) == 1 # The last event should be processed
    assert results[0]["event_type"] == "task_status"
    assert results[0]["data"]["state"] == "COMPLETED"

@pytest.mark.asyncio
async def test_process_sse_lines_yield_error(caplog):
    """Test handling errors during the yield process itself."""
    lines = [
        "event: task_status",
        'data: {"taskId": "t6", "state": "WORKING"}',
        ""
    ]
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.aiter_lines.return_value = mock_aiter_lines(lines)
    client = AgentVaultClient()

    async def consume_and_raise():
        gen = client._process_sse_stream_lines(mock_response, "test_ctx")
        item = await gen.__anext__() # Get the first item
        raise RuntimeError("Simulated error during consumption")

    with pytest.raises(RuntimeError, match="Simulated error during consumption"):
        await consume_and_raise()

    # Ensure error wasn't logged by the generator's internal handler
    assert "Error yielding parsed SSE event" not in caplog.text

# --- Tests for _make_request ---
@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_make_request_success():
    """Test _make_request successful POST with JSON-RPC result."""
    url = "http://test.com/api"
    req_id = "mkreq-1"
    result_data = {"status": "ok", "value": 123}
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": req_id}
    
    async with respx.mock(using="httpx") as respx_mock:
        mock_route = respx_mock.post(url).mock(
            return_value=httpx.Response(200, json=create_jsonrpc_success_response(req_id, result_data))
        )
        async with AgentVaultClient() as client:
            response_data = await client._make_request("POST", url, json_payload=payload)

        assert response_data == result_data
        assert mock_route.called

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_make_request_timeout():
    """Test _make_request raises A2ATimeoutError on httpx.TimeoutException."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(using="httpx") as respx_mock:
        mock_route = respx_mock.post(url).mock(side_effect=httpx.TimeoutException("Timeout!", request=None))
        async with AgentVaultClient() as client:
            with pytest.raises(A2ATimeoutError, match="Request timed out"):
                await client._make_request("POST", url, json_payload=payload)
        assert mock_route.called

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_make_request_connect_error():
    """Test _make_request raises A2AConnectionError on httpx.ConnectError."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(using="httpx") as respx_mock:
        mock_route = respx_mock.post(url).mock(side_effect=httpx.ConnectError("Connection failed!"))
        async with AgentVaultClient() as client:
            with pytest.raises(A2AConnectionError, match="Connection failed"):
                await client._make_request("POST", url, json_payload=payload)
        assert mock_route.called

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_make_request_http_status_error():
    """Test _make_request raises A2ARemoteAgentError on httpx.HTTPStatusError."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(using="httpx") as respx_mock:
        mock_route = respx_mock.post(url).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        async with AgentVaultClient() as client:
            with pytest.raises(A2ARemoteAgentError) as excinfo:
                await client._make_request("POST", url, json_payload=payload)
        assert excinfo.value.status_code == 500
        assert "Internal Server Error" in str(excinfo.value)
        assert mock_route.called

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_make_request_invalid_json_response():
    """Test _make_request raises A2AMessageError on invalid JSON response."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(using="httpx") as respx_mock:
        mock_route = respx_mock.post(url).mock(return_value=httpx.Response(200, text="{not json"))
        async with AgentVaultClient() as client:
            with pytest.raises(A2AMessageError, match="Failed to decode JSON response"):
                await client._make_request("POST", url, json_payload=payload)
        assert mock_route.called

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_make_request_json_rpc_error_response():
    """Test _make_request raises A2ARemoteAgentError on JSON-RPC error response."""
    url = "http://test.com/api"
    req_id = "err-req-1"
    error_code = JSONRPC_INVALID_PARAMS
    error_message = "Missing required parameter"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": req_id}
    error_response = create_jsonrpc_error_response(req_id, error_code, error_message)
    
    async with respx.mock(using="httpx") as respx_mock:
        mock_route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=error_response))
        async with AgentVaultClient() as client:
            with pytest.raises(A2ARemoteAgentError) as excinfo:
                await client._make_request("POST", url, json_payload=payload)
        assert excinfo.value.status_code == error_code
        assert error_message in str(excinfo.value)
        assert mock_route.called

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_make_request_response_not_dict():
    """Test _make_request raises A2AMessageError if JSON response is not a dict."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(using="httpx") as respx_mock:
        mock_route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=[1, 2, 3])) # Return list
        async with AgentVaultClient() as client:
            with pytest.raises(A2AMessageError, match="Expected dictionary"):
                await client._make_request("POST", url, json_payload=payload)
        assert mock_route.called

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_make_request_response_missing_result_or_error():
    """Test _make_request raises A2AMessageError if response lacks result/error."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(using="httpx") as respx_mock:
        mock_route = respx_mock.post(url).mock(return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1})) # Missing result/error
        async with AgentVaultClient() as client:
            with pytest.raises(A2AMessageError, match="Missing 'result' or 'error' key"):
                await client._make_request("POST", url, json_payload=payload)
        assert mock_route.called

# --- Tests for Public Method Error Handling ---
@pytest.mark.asyncio
async def test_initiate_task_auth_error(mock_key_manager, agent_card_apikey, sample_message):
    """Test initiate_task handles A2AAuthenticationError from _get_auth_headers."""
    mock_key_manager.get_key.return_value = None # Simulate missing key
    async with AgentVaultClient() as client:
        with pytest.raises(A2AAuthenticationError, match="Missing API key"):
            await client.initiate_task(agent_card_apikey, sample_message, mock_key_manager)

@pytest.mark.asyncio
async def test_initiate_task_key_management_error(mock_key_manager, agent_card_apikey, sample_message):
    """Test initiate_task handles KeyManagementError from _get_auth_headers."""
    error_msg = "Keyring access failed"
    mock_key_manager.get_key.side_effect = KeyManagementError(error_msg)
    async with AgentVaultClient() as client:
        # Should be wrapped in A2AAuthenticationError
        with pytest.raises(A2AAuthenticationError, match=f"Authentication failed due to key management error: {error_msg}"):
            await client.initiate_task(agent_card_apikey, sample_message, mock_key_manager)

@pytest.mark.asyncio
@patch("agentvault.client.AgentVaultClient._make_request", new_callable=AsyncMock)
@patch("agentvault.client.AgentVaultClient._get_auth_headers", new_callable=AsyncMock)
async def test_initiate_task_make_request_error(mock_get_headers, mock_make_request, mock_key_manager, agent_card_no_auth, sample_message):
    """Test initiate_task handles errors from _make_request."""
    mock_get_headers.return_value = {} # Simulate successful auth header fetch
    error_to_raise = A2ARemoteAgentError("Agent failed init", status_code=500)
    mock_make_request.side_effect = error_to_raise

    async with AgentVaultClient() as client:
        with pytest.raises(A2ARemoteAgentError, match="Agent failed init"):
            await client.initiate_task(agent_card_no_auth, sample_message, mock_key_manager)

    mock_get_headers.assert_awaited_once()
    mock_make_request.assert_awaited_once()

@pytest.mark.asyncio
@patch("agentvault.client.AgentVaultClient._make_request", new_callable=AsyncMock)
@patch("agentvault.client.AgentVaultClient._get_auth_headers", new_callable=AsyncMock)
async def test_initiate_task_unexpected_error(mock_get_headers, mock_make_request, mock_key_manager, agent_card_no_auth, sample_message):
    """Test initiate_task handles unexpected errors."""
    mock_get_headers.return_value = {}
    error_to_raise = ValueError("Unexpected validation issue")
    mock_make_request.side_effect = error_to_raise

    async with AgentVaultClient() as client:
        # Should be wrapped in A2AError
        with pytest.raises(A2AError, match="An unexpected error occurred during task initiation"):
            await client.initiate_task(agent_card_no_auth, sample_message, mock_key_manager)

    mock_get_headers.assert_awaited_once()
    mock_make_request.assert_awaited_once()
