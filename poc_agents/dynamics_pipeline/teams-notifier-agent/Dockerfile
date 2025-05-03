# Teams Notifier Agent Dockerfile
# Based on slack-notifier-agent template

FROM python:3.11-slim-bookworm

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (minimal needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy library and SDK first
COPY agentvault_library/ /app/agentvault_library/
COPY agentvault_server_sdk/ /app/agentvault_server_sdk/

# Copy agent-specific code
COPY poc_agents/dynamics_pipeline/teams-notifier-agent/src /app/src
COPY poc_agents/dynamics_pipeline/teams-notifier-agent/agent-card.json /app/agent-card.json

# Install base dependencies (SDK/Library)
RUN pip install --no-cache-dir /app/agentvault_library /app/agentvault_server_sdk

# Install agent-specific Python dependencies
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic python-dotenv

# Create a non-root user
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Change ownership
RUN chown -R appuser:appgroup /app

# Switch user
USER appuser

# Set environment variables
ENV PORT=8058 \
    AGENT_CARD_PATH=/app/agent-card.json \
    PYTHONPATH=/app/src:/app/agentvault_library

# Expose the port
EXPOSE 8058

# Define the command
CMD ["uvicorn", "teams_notifier_agent.main:app", "--host", "0.0.0.0", "--port", "8058", "--log-level", "info"]
