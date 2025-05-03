#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

echo "Entrypoint received args: $@"

# --- Wait for registry ---
echo "Waiting for AgentVault Registry at $AGENTVAULT_REGISTRY_URL..."
max_retries=30; retry_count=0
while [ $retry_count -lt $max_retries ]; do
  # Use curl's built-in fail and silent options
  if curl --fail --silent --max-time 5 $AGENTVAULT_REGISTRY_URL/health > /dev/null 2>&1; then
    echo "Registry available!"; break
  fi
  status_code=$(curl --silent --output /dev/null --write-out "%{http_code}" --max-time 5 $AGENTVAULT_REGISTRY_URL/health || echo "N/A")
  echo "Attempt $((retry_count+1))/$max_retries: Registry not ready (Status: $status_code). Waiting 5s..."
  retry_count=$((retry_count+1)); sleep 5
done
if [ $retry_count -eq $max_retries ]; then echo "ERROR: Registry timeout."; exit 1; fi

# --- Wait for MCP Proxy Agent (Port 8059) ---
echo "Waiting for MCP Tool Proxy Agent (mcp-tool-proxy-agent:8059)..."
max_proxy_retries=25; proxy_retry_count=0
while [ $proxy_retry_count -lt $max_proxy_retries ]; do
    if nc -z mcp-tool-proxy-agent 8059; then echo "MCP Proxy Agent port 8059 is open!"; sleep 2; break; fi
    echo "Attempt $((proxy_retry_count+1))/$max_proxy_retries: MCP Proxy Agent port not responding. Waiting 3s..."
    proxy_retry_count=$((proxy_retry_count+1)); sleep 3
done
if [ $proxy_retry_count -eq $max_proxy_retries ]; then echo "ERROR: MCP Tool Proxy Agent (mcp-tool-proxy-agent:8059) timeout."; exit 1; fi

# --- Wait for Filesystem MCP Server (Port 8001) ---
echo "Waiting for Filesystem MCP Server (custom-filesystem-mcp:8001)..."
max_fs_retries=25; fs_retry_count=0
while [ $fs_retry_count -lt $max_fs_retries ]; do
    # Use timeout for nc to prevent hanging indefinitely
    if nc -z -w 3 custom-filesystem-mcp 8001; then echo "Filesystem MCP Server port 8001 is open!"; sleep 1; break; fi
    echo "Attempt $((fs_retry_count+1))/$max_fs_retries: Filesystem MCP Server port not responding. Waiting 3s..."
    fs_retry_count=$((fs_retry_count+1)); sleep 3
done
if [ $fs_retry_count -eq $max_fs_retries ]; then echo "ERROR: Filesystem MCP Server (custom-filesystem-mcp:8001) timeout."; exit 1; fi

# --- Wait for Code Runner MCP Server (Port 8002) ---
# CORRECTED SERVICE NAME HERE
echo "Waiting for Code Runner MCP Server (custom-code-runner-mcp:8002)..."
max_code_retries=25; code_retry_count=0
while [ $code_retry_count -lt $max_code_retries ]; do
    # Use timeout for nc and the CORRECT service name
    if nc -z -w 3 custom-code-runner-mcp 8002; then echo "Code Runner MCP Server port 8002 is open!"; sleep 1; break; fi
    echo "Attempt $((code_retry_count+1))/$max_code_retries: Code Runner MCP Server port not responding. Waiting 3s..."
    code_retry_count=$((code_retry_count+1)); sleep 3
done
if [ $code_retry_count -eq $max_code_retries ]; then echo "ERROR: Code Runner MCP Server (custom-code-runner-mcp:8002) timeout."; exit 1; fi
# --- END CORRECTION ---

# --- MODIFIED: Removed flawed argument shifting logic ---
# The arguments ($@) received by this script are now correctly
# passed directly from the 'command:' directive in docker-compose.yml

echo "Starting MCP Test Pipeline Orchestrator via python -m mcp_test_orchestrator.run..."
echo "Arguments to pass to Python: $@"

# Setting timeouts to avoid being stuck
export AGENTVAULT_API_TIMEOUT=30
echo "Set AGENTVAULT_API_TIMEOUT=$AGENTVAULT_API_TIMEOUT"

# Execute the main Python application, replacing this script process.
# "$@" correctly expands to the arguments received by this script
# (which are now --file /data/test_script.py due to the compose changes).
exec python -m mcp_test_orchestrator.run "$@"
