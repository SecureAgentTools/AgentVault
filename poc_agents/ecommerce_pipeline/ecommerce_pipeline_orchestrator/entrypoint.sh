#!/bin/bash
set -e

# Wait for registry to be available
echo "Waiting for AgentVault Registry at $AGENTVAULT_REGISTRY_URL to be available..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
  if curl -s -f $AGENTVAULT_REGISTRY_URL/health > /dev/null 2>&1; then
    echo "AgentVault Registry is available!"
    break
  fi
  
  retry_count=$((retry_count+1))
  echo "Attempt $retry_count/$max_retries: Registry not available yet. Waiting 5 seconds..."
  sleep 5
done

if [ $retry_count -eq $max_retries ]; then
  echo "ERROR: AgentVault Registry not available after $max_retries attempts. Using direct agent connections."
fi

# Wait for all agents to be ready
echo "Waiting for agents to be available..."
# Wait longer for agents to start up
sleep 30
echo "Agents should be ready now."

# Run the orchestrator with the provided arguments
echo "Starting E-commerce Pipeline Orchestrator..."
# Print Python path for debugging
echo "PYTHONPATH: $PYTHONPATH"
echo "Python version: $(python --version)"
echo "System paths:"
python -c "import sys; print('\n'.join(sys.path))"

# Run the orchestrator via our wrapper script
echo "Running ecommerce_orchestrator via wrapper.py..."
cd /app
exec python -m ecommerce_orchestrator.wrapper
