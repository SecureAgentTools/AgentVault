# Support Pipeline Orchestrator Dockerfile
# Adapting the e-commerce orchestrator Dockerfile structure

FROM python:3.11-slim-bookworm

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy library first (assuming build context is monorepo root: D:/AgentVault)
COPY agentvault_library/ /app/agentvault_library/

# Copy orchestrator code (relative to build context)
COPY poc_agents/support_pipeline/support_pipeline_orchestrator/src /app/src
# Copy config files to the root /app directory where they are expected
COPY poc_agents/support_pipeline/support_pipeline_orchestrator/support_config.json /app/support_config.json
COPY poc_agents/support_pipeline/support_pipeline_orchestrator/.env /app/.env
# Copy entrypoint script
COPY poc_agents/support_pipeline/support_pipeline_orchestrator/entrypoint.sh /app/entrypoint.sh

# Install dependencies directly with pip (using the copied library)
# Install library first
RUN pip install --no-cache-dir /app/agentvault_library

# Install Python dependencies for the orchestrator
# Match versions from pyproject.toml
RUN pip install --no-cache-dir \
    langgraph==0.1.1 \
    langchain-core==0.2.23 \
    "httpx[http2,brotli]>=0.26.0,<0.27.0" \
    pydantic==2.7.1 \
    python-dotenv==1.0.1 \
    pydantic-settings==2.0 \
    tenacity==8.2.3 \
    "langchain>=0.2.11" \
    "langchain-community>=0.2.10"

# Create a non-root user
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Create artifact directory and set permissions (REQ-SUP-ORCH-002)
RUN mkdir -p /app/pipeline_artifacts/support && chown -R appuser:appgroup /app/pipeline_artifacts

# Add extra hosts to resolve host.docker.internal (needed for registry/agents on host)
# RUN echo "$(getent hosts host.docker.internal | awk '{ print $1 }') host.docker.internal" >> /etc/hosts || true
# Simpler approach often works:
RUN echo "host.docker.internal host-gateway" >> /etc/hosts || true

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Set Python Path correctly for src layout
ENV PYTHONPATH=/app/src:/app/agentvault_library

# Switch user AFTER setting permissions and ENV vars that might be needed by root
USER appuser

# Default command to run the orchestrator via the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
# CMD arguments will be passed to the entrypoint script (e.g., ticket text, customer ID)
# Example default (can be overridden in docker-compose):
CMD ["Default ticket text", "default-customer-id"]
