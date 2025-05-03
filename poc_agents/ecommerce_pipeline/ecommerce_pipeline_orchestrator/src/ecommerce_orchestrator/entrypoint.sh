#!/bin/bash
set -e

# Wait for registry to be available
echo "Waiting for AgentVault Registry at $AGENTVAULT_REGISTRY_URL to be available..."
max_retries=30
retry_count=0

# Use curl with --fail to check for HTTP errors too
while [ $retry_count -lt $max_retries ]; do
  if curl --fail -s $AGENTVAULT_REGISTRY_URL/health > /dev/null 2>&1; then
    echo "AgentVault Registry is available!"
    break
  else
    status_code=$(curl -s -o /dev/null -w "%{http_code}" $AGENTVAULT_REGISTRY_URL/health)
    echo "Attempt $retry_count/$max_retries: Registry not available yet (Status: $status_code). Waiting 5 seconds..."
  fi
  retry_count=$((retry_count+1))
  sleep 5
done

if [ $retry_count -eq $max_retries ]; then
  echo "ERROR: AgentVault Registry not available after $max_retries attempts. Exiting."
  exit 1 # Exit if registry is critical
fi

# Wait for all agents to be ready (optional, adjust time as needed)
echo "Waiting for agents to be available (15s)..."
sleep 15

# --- MODIFIED: Execute python -m with corrected module path ---
# Run the orchestrator module, passing all script arguments ($@) to it
# The first argument after 'run' will be the user_id from the Dockerfile CMD
echo "Starting E-commerce Pipeline Orchestrator via python -m..."
exec python -m ecommerce_orchestrator.run "$@"
# --- END MODIFIED ---
