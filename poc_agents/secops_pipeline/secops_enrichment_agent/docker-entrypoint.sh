#!/bin/bash
# Custom entrypoint to ensure enrichment data is generated at startup
set -e

# Install Redis if needed
if ! pip list | grep -q redis; then
  echo "Installing redis module..."
  pip install redis
fi

# Make sure to run the direct fix for current projects
echo "Running direct enrichment fix..."
if python -c "from secops_enrichment_agent.direct_fix import main; main()"; then
  echo "Direct fix applied successfully!"
else
  echo "Warning: Direct fix failed, but continuing with startup"
fi

# Then run the original command (the main FastAPI app)
echo "Starting FastAPI application..."
exec "$@"
