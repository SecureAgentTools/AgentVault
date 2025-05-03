# Improved Dockerfile for the custom-filesystem-mcp server
# Corrected MCP package installation & Separated user creation/chown

FROM python:3.11-slim

WORKDIR /app

# Install required system dependencies (including gosu for user switching)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/*

# Copy application code and project file
COPY ./src /app/src
# Combine COPY for pyproject.toml and entrypoint.sh into one layer
COPY ./pyproject.toml ./entrypoint.sh /app/
# Make the entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Create an empty __init__.py file in /app to make it a Python package (if needed by entrypoint)
# RUN touch /app/__init__.py

# Install Python dependencies
# Install only the dependencies we need
RUN pip install --no-cache-dir "fastapi>=0.111,<0.112" \
    "uvicorn[standard]>=0.29,<0.35" \
    "python-dotenv>=1.0.0"

# Setup data directory
ENV MCP_DATA_DIR=/data
RUN mkdir -p $MCP_DATA_DIR

# Create a non-root user and group in one layer
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Change ownership in a separate layer AFTER user/group creation
RUN chown -R appuser:appuser /app && chown -R appuser:appuser $MCP_DATA_DIR

# Don't switch to non-root user yet - we'll do it in the entrypoint
# USER appuser

EXPOSE 8001

# Set PYTHONPATH correctly to ensure proper imports
ENV PYTHONPATH=/app:/app/src:$PYTHONPATH

# Stay in the main app directory
WORKDIR /app

# Run using the entrypoint script, which handles uvicorn launch
# The entrypoint script already calls:
# uvicorn src.custom_filesystem_mcp.main:app --host 0.0.0.0 --port 8001 --log-level debug
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
# CMD is effectively handled by the entrypoint script
