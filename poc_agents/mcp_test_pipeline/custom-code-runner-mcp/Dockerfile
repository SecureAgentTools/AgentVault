# Dockerfile for Custom Code Runner MCP Server
# Based on research findings (Section 7.4)
# Corrected CMD syntax

# Use a minimal Python base image
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Create a non-root user and group for security
RUN groupadd -r appgroup --gid 1001 && \
    useradd --no-log-init -r -g appgroup --uid 1001 appuser

# Install dependencies
# Copy only requirements first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt
# Ensure pip is up-to-date and install requirements
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy application code into the image
COPY ./src /app/src
COPY ./.env /app/.env

# Create necessary directories if needed (e.g., for logs or temp files)
# RUN mkdir /tmp/code_execution && chown appuser:appgroup /tmp/code_execution

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose the port the app runs on (MCP standard port for code runner)
EXPOSE 8002

# Set environment variables (can be overridden)
ENV PYTHONPATH=/app/src
ENV LOG_LEVEL=INFO
ENV MCP_PORT=8002
ENV TIMEOUT_SECONDS=10

# Command to run the application using Uvicorn
# Use exec form to avoid shell interpretation issues with LOG_LEVEL
# Uvicorn handles case-insensitivity for log levels.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002", "--log-level", "info"]
# Note: LOG_LEVEL env var can still be set in docker-compose.yml to override,
# but the default here is 'info'. If DEBUG is needed, set it in compose.
