# SecOps Investigation Agent Dockerfile

FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    PORT=8072 \
    AGENT_CARD_PATH=/app/agent-card.json
# Set Python Path to include src and copied libraries
ENV PYTHONPATH=/app/src:/app/agentvault_library:/app/agentvault_server_sdk:/app/shared

# Install system dependencies if needed (e.g., curl)
RUN apt-get update && apt-get install -y --no-install-recommends curl git build-essential && rm -rf /var/lib/apt/lists/*

# Copy library and SDK source first
COPY agentvault_library/ /app/agentvault_library/
COPY agentvault_server_sdk/ /app/agentvault_server_sdk/
COPY poc_agents/secops_pipeline/shared/ /app/shared/

# Copy agent-specific code and project files
COPY poc_agents/secops_pipeline/secops_investigation_agent/src /app/src
COPY poc_agents/secops_pipeline/secops_investigation_agent/pyproject.toml /app/pyproject.toml
# COPY poc_agents/secops_pipeline/secops_investigation_agent/poetry.lock /app/poetry.lock # Removed: Will be generated
COPY poc_agents/secops_pipeline/secops_investigation_agent/agent-card.json /app/agent-card.json
COPY poc_agents/secops_pipeline/secops_investigation_agent/.env.example /app/.env.example

# Install base dependencies (SDK/Library) directly
RUN pip install --no-cache-dir /app/agentvault_library /app/agentvault_server_sdk keyring

# Install agent-specific Python dependencies directly
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" "httpx>=0.26.0,<0.27.0" pydantic==2.7.1 python-dotenv==1.0.1 jsonschema>=4.18.0 anyio>=3.7.1

# Create user/group
RUN groupadd -r appgroup --gid 1003 && useradd --no-log-init -r -g appgroup --uid 1003 appuser

# Change ownership
RUN chown -R appuser:appgroup /app

# Switch user
USER appuser

# Expose the agent's port
EXPOSE 8072

# Default command to run the agent - fix the module structure
CMD cd /app && python -m secops_investigation_agent.main
