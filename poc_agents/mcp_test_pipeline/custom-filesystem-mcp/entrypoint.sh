#!/bin/bash
set -e

# Simple diagnostic information
echo "Current directory: $(pwd)"
echo "Python version: $(python --version)"
echo "Current user: $(whoami)"
echo "User ID: $(id -u)"
echo "Group ID: $(id -g)"

# Check permissions on /data directory
echo "Checking /data directory permissions..."
ls -la /data || echo "/data directory does not exist or cannot be accessed"

# If running as root, fix permissions and switch to appuser
if [ "$(id -u)" = "0" ]; then
    echo "Running as root, fixing permissions..."
    # Fix permissions on /data
    chown -R appuser:appuser /data || echo "Could not change ownership of /data"
    chmod -R 775 /data || echo "Could not change permissions of /data"
    
    # Switch to appuser for running the server
    echo "Switching to appuser..."
    exec gosu appuser "$0" "$@"
fi

# Set PYTHONPATH to include necessary paths
export PYTHONPATH=/app:/app/src:${PYTHONPATH:-}

echo "PYTHONPATH: $PYTHONPATH"

# Run Uvicorn with the correct module path
echo "Starting custom-filesystem-mcp server..."
exec uvicorn src.custom_filesystem_mcp.main:app --host 0.0.0.0 --port 8001 --log-level debug
