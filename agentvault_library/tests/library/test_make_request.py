import pytest
import respx
import json
import uuid
import datetime
import asyncio
import httpx
from unittest.mock import patch, MagicMock, AsyncMock

from agentvault.client import AgentVaultClient
from agentvault.exceptions import (
    A2AError, A2AConnectionError, A2ATimeoutError, 
    A2ARemoteAgentError, A2AMessageError
)

from agentvault_testing_utils.mock_server import (
    create_jsonrpc_error_response,
    create_jsonrpc_success_response,
    JSONRPC_PARSE_ERROR, JSONRPC_INVALID_REQUEST, JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_APP_ERROR, JSONRPC_INVALID_PARAMS, JSONRPC_INTERNAL_ERROR, JSONRPC_TASK_NOT_FOUND
)

# --- Test the _make_request method directly ---
@pytest.mark.asyncio
async def test_make_request_success():
    """Test _make_request successful POST with JSON-RPC result."""
    url = "http://test.com/api"
    req_id = "mkreq-1"
    result_data = {"status": "ok", "value": 123}
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": req_id}
    
    async with respx.mock(base_url=url) as respx_mock:
        mock_route = respx_mock.post("/").mock(
            return_value=httpx.Response(200, json=create_jsonrpc_success_response(req_id, result_data))
        )
        
        async with AgentVaultClient() as client:
            response_data = await client._make_request("POST", url, json_payload=payload)

        assert response_data == result_data
        assert mock_route.called

@pytest.mark.asyncio
async def test_make_request_timeout():
    """Test _make_request raises A2ATimeoutError on httpx.TimeoutException."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(base_url=url) as respx_mock:
        mock_route = respx_mock.post("/").mock(
            side_effect=httpx.TimeoutException("Timeout!", request=None)
        )
        
        async with AgentVaultClient() as client:
            with pytest.raises(A2ATimeoutError, match="Request timed out"):
                await client._make_request("POST", url, json_payload=payload)
                
        assert mock_route.called

@pytest.mark.asyncio
async def test_make_request_connect_error():
    """Test _make_request raises A2AConnectionError on httpx.ConnectError."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(base_url=url) as respx_mock:
        mock_route = respx_mock.post("/").mock(
            side_effect=httpx.ConnectError("Connection failed!")
        )
        
        async with AgentVaultClient() as client:
            with pytest.raises(A2AConnectionError, match="Connection failed"):
                await client._make_request("POST", url, json_payload=payload)
                
        assert mock_route.called

@pytest.mark.asyncio
async def test_make_request_http_status_error():
    """Test _make_request raises A2ARemoteAgentError on httpx.HTTPStatusError."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(base_url=url) as respx_mock:
        mock_route = respx_mock.post("/").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        
        async with AgentVaultClient() as client:
            with pytest.raises(A2ARemoteAgentError) as excinfo:
                await client._make_request("POST", url, json_payload=payload)
                
        assert excinfo.value.status_code == 500
        assert "Internal Server Error" in str(excinfo.value)
        assert mock_route.called

@pytest.mark.asyncio
async def test_make_request_invalid_json_response():
    """Test _make_request raises A2AMessageError on invalid JSON response."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(base_url=url) as respx_mock:
        mock_route = respx_mock.post("/").mock(
            return_value=httpx.Response(200, text="{not json")
        )
        
        async with AgentVaultClient() as client:
            with pytest.raises(A2AMessageError, match="Failed to decode JSON response"):
                await client._make_request("POST", url, json_payload=payload)
                
        assert mock_route.called

@pytest.mark.asyncio
async def test_make_request_json_rpc_error_response():
    """Test _make_request raises A2ARemoteAgentError on JSON-RPC error response."""
    url = "http://test.com/api"
    req_id = "err-req-1"
    error_code = JSONRPC_INVALID_PARAMS
    error_message = "Missing required parameter"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": req_id}
    error_response = create_jsonrpc_error_response(req_id, error_code, error_message)
    
    async with respx.mock(base_url=url) as respx_mock:
        mock_route = respx_mock.post("/").mock(
            return_value=httpx.Response(200, json=error_response)
        )
        
        async with AgentVaultClient() as client:
            with pytest.raises(A2ARemoteAgentError) as excinfo:
                await client._make_request("POST", url, json_payload=payload)
                
        assert excinfo.value.status_code == error_code
        assert error_message in str(excinfo.value)
        assert mock_route.called

@pytest.mark.asyncio
async def test_make_request_response_not_dict():
    """Test _make_request raises A2AMessageError if JSON response is not a dict."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(base_url=url) as respx_mock:
        mock_route = respx_mock.post("/").mock(
            return_value=httpx.Response(200, json=[1, 2, 3])  # Return list
        )
        
        async with AgentVaultClient() as client:
            with pytest.raises(A2AMessageError, match="Expected dictionary"):
                await client._make_request("POST", url, json_payload=payload)
                
        assert mock_route.called

@pytest.mark.asyncio
async def test_make_request_response_missing_result_or_error():
    """Test _make_request raises A2AMessageError if response lacks result/error."""
    url = "http://test.com/api"
    payload = {"jsonrpc": "2.0", "method": "test_method", "id": 1}
    
    async with respx.mock(base_url=url) as respx_mock:
        mock_route = respx_mock.post("/").mock(
            return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1})  # Missing result/error
        )
        
        async with AgentVaultClient() as client:
            with pytest.raises(A2AMessageError, match="Missing 'result' or 'error' key"):
                await client._make_request("POST", url, json_payload=payload)
                
        assert mock_route.called
