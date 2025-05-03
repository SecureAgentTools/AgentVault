#!/bin/bash
set -e

# Wait for registry (essential for agent discovery)
echo "Waiting for AgentVault Registry at $AGENTVAULT_REGISTRY_URL..."
max_retries=30; retry_count=0
while [ $retry_count -lt $max_retries ]; do
  if curl --fail -s $AGENTVAULT_REGISTRY_URL/health > /dev/null 2>&1; then echo "Registry available!"; break; fi
  status_code=$(curl -s -o /dev/null -w "%{http_code}" $AGENTVAULT_REGISTRY_URL/health || echo "N/A")
  echo "Attempt $retry_count/$max_retries: Registry not ready (Status: $status_code). Waiting 5s..."
  retry_count=$((retry_count+1)); sleep 5
done
if [ $retry_count -eq $max_retries ]; then echo "ERROR: Registry timeout."; exit 1; fi

# Wait for DB (essential for agents)
echo "Waiting for ETL Database (etl-db)..."
# Use nc now that it should be installed. Increased retries slightly.
max_db_retries=25; db_retry_count=0
while [ $db_retry_count -lt $max_db_retries ]; do
    if nc -z etl-db 5432; then
        echo "Database port 5432 is open!";
        # Add a small extra delay AFTER port is open, just in case service isn't fully accepting yet
        sleep 2
        echo "Proceeding after short delay."
        break;
    fi
    echo "Attempt $db_retry_count/$max_db_retries: Database port not responding. Waiting 3s..."
    db_retry_count=$((db_retry_count+1));
    sleep 3
done
if [ $db_retry_count -eq $max_db_retries ]; then echo "ERROR: Database (etl-db:5432) timeout."; exit 1; fi

# Optional: Wait longer for agents themselves
echo "Waiting briefly for ETL agents (5s)..." # Reduced wait now DB check is better
sleep 5

# Execute the orchestrator's run module, passing CMD arguments ($@)
echo "Starting ETL Pipeline Orchestrator via python -m etl_orchestrator.run..."
echo "Arguments passed to run.py: $@"
exec python -m etl_orchestrator.run "$@"
