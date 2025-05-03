#!/bin/sh
# Script to start the filesystem MCP server with proper transport mechanism

# Check if MCP_TRANSPORT is set to http
if [ "$MCP_TRANSPORT" = "http" ]; then
  # Start directly with HTTP transport
  exec node /app/dist/index.js /projects/shared
else
  # Use socat to bridge TCP to stdio as fallback
  echo "Warning: Using socat TCP bridge because MCP_TRANSPORT is not set to 'http'"
  exec socat TCP-LISTEN:8001,fork,reuseaddr EXEC:"node /app/dist/index.js /projects/shared",pty
fi
