# Response Suggestion Agent Dockerfile (REQ-SUP-SUG-008)
# Adapting the standard agent Dockerfile structure

FROM python:3.11-slim-bookworm

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (minimal needed for this agent)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy library and SDK first (Paths relative to build context - monorepo root)
COPY agentvault_library/ /app/agentvault_library/
COPY agentvault_server_sdk/ /app/agentvault_server_sdk/

# Copy base agent (assuming standard location) and agent-specific code
COPY poc_agents/research_pipeline/base_agent.py /app/base_agent.py
COPY poc_agents/support_pipeline/response_suggester_agent/src /app/src
COPY poc_agents/support_pipeline/response_suggester_agent/agent-card.json /app/agent-card.json

# Install base dependencies (SDK/Library)
RUN pip install --no-cache-dir /app/agentvault_library /app/agentvault_server_sdk

# Install agent-specific Python dependencies (from pyproject.toml)
# Ensure httpx is included for LLM calls (REQ-SUP-SUG-007)
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic python-dotenv httpx

# Create a non-root user
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Change ownership
RUN chown -R appuser:appgroup /app

# Switch user
USER appuser

# Set environment variables
ENV PORT=8033 \
    AGENT_CARD_PATH=/app/agent-card.json \
    PYTHONPATH=/app:/app/src

# Expose the port
EXPOSE 8033

# Define the command to run the agent server
CMD ["uvicorn", "response_suggester_agent.main:app", "--host", "0.0.0.0", "--port", "8033", "--log-level", "info"]
