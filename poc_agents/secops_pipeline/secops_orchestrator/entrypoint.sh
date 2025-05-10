#!/bin/bash
# Enhanced Entrypoint for SecOps Orchestrator
# Adds pipeline fix steps to ensure enrichment works
set -e

echo "SecOps Orchestrator Entrypoint executing..."
echo "Entrypoint received args: $@"

# --- Ensure Redis is available ---
echo "Checking for Redis module..."
if ! pip list | grep -q redis; then
  echo "Redis module not found! Installing Redis module..."
  pip install --no-cache-dir redis
else
  echo "Redis module is already installed."
fi

# Verify Redis can be imported
python -c "import redis; print('Redis module imports successfully!')" || {
  echo "Redis import failed! Reinstalling..."
  pip uninstall -y redis && pip install --no-cache-dir redis
  python -c "import redis; print('Redis module imports successfully after reinstall!')" || echo "CRITICAL: Redis still cannot be imported!"
}

# --- Skip creating enrichment data ---
echo "Skipping enrichment data creation - will be handled in nodes.py"

# --- Wait for registry (Essential for discovering agents) ---
# Check if AGENTVAULT_REGISTRY_URL is set, use default if not
if [ -z "$AGENTVAULT_REGISTRY_URL" ]; then
  echo "WARNING: AGENTVAULT_REGISTRY_URL environment variable not set. Using default http://localhost:8000"
  export AGENTVAULT_REGISTRY_URL="http://localhost:8000"
fi

# If registry is localhost, replace with host.docker.internal for container->host communication
# Otherwise, use the provided URL directly
if [[ "$AGENTVAULT_REGISTRY_URL" == *"localhost"* || "$AGENTVAULT_REGISTRY_URL" == *"127.0.0.1"* ]]; then
  # Use sed for replacement to handle http/https gracefully
  REGISTRY_CHECK_URL=$(echo "$AGENTVAULT_REGISTRY_URL" | sed 's/localhost/host.docker.internal/g; s/127.0.0.1/host.docker.internal/g')
  echo "Detected localhost registry URL, attempting connection via host.docker.internal: $REGISTRY_CHECK_URL"
else
  REGISTRY_CHECK_URL="$AGENTVAULT_REGISTRY_URL"
  echo "Using configured registry URL: $REGISTRY_CHECK_URL"
fi

echo "Waiting for AgentVault Registry at $REGISTRY_CHECK_URL..."
max_retries=30
retry_count=0
# Use /health endpoint which should be faster than root
health_url=$(echo "$REGISTRY_CHECK_URL" | sed 's,/*$,,' )/health # Ensure single trailing slash before adding /health
echo "Checking health endpoint: $health_url"

while [ $retry_count -lt $max_retries ]; do
  # Use curl with fail-silent and timeout
  if curl --fail --silent --max-time 5 "$health_url" > /dev/null 2>&1; then
    echo "Registry available!"
    break
  fi
  status_code=$(curl --silent --output /dev/null --write-out "%{http_code}" --max-time 5 "$health_url" || echo "N/A")
  echo "Attempt $((retry_count+1))/$max_retries: Registry not ready (Status: $status_code at $health_url). Waiting 5s..."
  retry_count=$((retry_count+1))
  sleep 5
done

if [ $retry_count -eq $max_retries ]; then
  echo "ERROR: AgentVault Registry timeout after $max_retries attempts at $health_url."
  # Decide whether to exit or proceed cautiously
  # For now, let's proceed but log a critical warning, the app might handle it
  echo "WARNING: Proceeding without confirmed registry connection."
  # exit 1 # Option to exit if registry is mandatory for startup
fi

# --- Execute main Python application ---
# Pass any arguments received by this script ($@) to the Python module
echo "Starting SecOps Pipeline Orchestrator via python -m secops_orchestrator.run..."
echo "Arguments to pass to Python: $@"

# Make sure PYTHONPATH includes /app/src
export PYTHONPATH=/app:/app/src:${PYTHONPATH:-}
echo "Effective PYTHONPATH: $PYTHONPATH"

# exec replaces the shell process with the Python process
exec python -m secops_orchestrator.run "$@"

echo "Entrypoint finished (should not be reached if exec succeeds)."
