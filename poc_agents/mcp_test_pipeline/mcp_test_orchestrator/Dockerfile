# MCP Test Pipeline Orchestrator Dockerfile
# Based on Dynamics Pipeline Orchestrator template

FROM python:3.11-slim-bookworm

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (Curl for health checks, netcat for waits)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy library first
COPY agentvault_library/ /app/agentvault_library/

# Copy orchestrator code (Corrected Path)
COPY poc_agents/mcp_test_pipeline/mcp_test_orchestrator/src /app/src
COPY poc_agents/mcp_test_pipeline/mcp_test_orchestrator/mcp_test_config.json /app/mcp_test_config.json
COPY poc_agents/mcp_test_pipeline/mcp_test_orchestrator/.env /app/.env
COPY poc_agents/mcp_test_pipeline/mcp_test_orchestrator/entrypoint.sh /app/entrypoint.sh

# Install dependencies
# Ensure pip install happens *before* setting PYTHONPATH that might conflict
RUN pip install --no-cache-dir /app/agentvault_library
RUN pip install --no-cache-dir \
    langgraph==0.1.1 \
    langchain-core==0.2.23 \
    "httpx[http2,brotli]>=0.26.0,<0.27.0" \
    pydantic==2.7.1 \
    python-dotenv==1.0.1 \
    pydantic-settings==2.0 \
    tenacity==8.2.3

# Create user/group
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Add host.docker.internal (if needed for registry/LLM)
RUN echo "host.docker.internal host-gateway" >> /etc/hosts || true

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Set Python Path
ENV PYTHONPATH=/app/src

# Switch user
USER appuser

# Default command
ENTRYPOINT ["/app/entrypoint.sh"]
# Example CMD: Pass path to a script in the shared volume
CMD ["/data/test_script.py"]
