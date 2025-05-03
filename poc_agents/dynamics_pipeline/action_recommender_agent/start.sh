#!/bin/sh
set -e

# Print Python path and environment for debugging
echo "PYTHONPATH: $PYTHONPATH"
echo "Current directory: $(pwd)"
echo "Contents of /app/src:"
ls -la /app/src
echo "Contents of /app/src/action_recommender_agent:"
ls -la /app/src/action_recommender_agent

# Run the application
exec uvicorn action_recommender:app --host 0.0.0.0 --port 8054 --log-level info
