#!/bin/bash
set -e

# Wait for registry
echo "Waiting for AgentVault Registry at $AGENTVAULT_REGISTRY_URL..."
max_retries=30; retry_count=0
while [ $retry_count -lt $max_retries ]; do
  if curl --fail -s $AGENTVAULT_REGISTRY_URL/health > /dev/null 2>&1; then echo "Registry available!"; break; fi
  status_code=$(curl -s -o /dev/null -w "%{http_code}" $AGENTVAULT_REGISTRY_URL/health || echo "N/A")
  echo "Attempt $retry_count/$max_retries: Registry not ready (Status: $status_code). Waiting 5s..."
  retry_count=$((retry_count+1)); sleep 5
done
if [ $retry_count -eq $max_retries ]; then echo "ERROR: Registry timeout."; exit 1; fi

# Wait for D365 DB
echo "Waiting for Dynamics DB (d365-db)..."
max_db_retries=25; db_retry_count=0
while [ $db_retry_count -lt $max_db_retries ]; do
    if nc -z d365-db 5432; then echo "Database port 5432 is open!"; sleep 2; echo "Proceeding after short delay."; break; fi
    echo "Attempt $db_retry_count/$max_db_retries: Database port not responding. Waiting 3s..."
    db_retry_count=$((db_retry_count+1)); sleep 3
done
if [ $db_retry_count -eq $max_db_retries ]; then echo "ERROR: Database (d365-db:5432) timeout."; exit 1; fi

# Optional: Wait for agents
echo "Waiting briefly for Dynamics agents (5s)..."
sleep 5

# When ENTRYPOINT is a script (exec form) and CMD is also exec form,
# the CMD array elements are passed as arguments ($1, $2, ...) to the script.
# "$@" correctly captures these arguments as separate strings.
echo "Starting Dynamics Pipeline Orchestrator via python -m dynamics_orchestrator.run..."
echo "Arguments received by entrypoint script: $@"

# Setting timeouts to avoid being stuck
export AGENTVAULT_API_TIMEOUT=30
echo "Set AGENTVAULT_API_TIMEOUT=$AGENTVAULT_API_TIMEOUT"

exec python -m dynamics_orchestrator.run "$@"
