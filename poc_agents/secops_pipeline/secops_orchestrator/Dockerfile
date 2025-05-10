# SecOps Pipeline Orchestrator Dockerfile
# REQ-SECOPS-ORCH-1.2 - Corrected: REMOVE poetry.lock COPY, use poetry add

FROM python:3.11-slim-bookworm

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV POETRY_NO_INTERACTION=1
ENV POETRY_VIRTUALENVS_CREATE=false

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    netcat-openbsd \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy shared libraries and LLM client
COPY agentvault_library/ /app/agentvault_library/
COPY poc_agents/secops_pipeline/shared/ /app/shared/

# Copy orchestrator code and project files
# IMPORTANT: pyproject.toml here should have host-relative paths (e.g., ../../../agentvault_library)
COPY poc_agents/secops_pipeline/secops_orchestrator/src /app/src
COPY poc_agents/secops_pipeline/secops_orchestrator/pyproject.toml /app/pyproject.toml
# COPY poc_agents/secops_pipeline/secops_orchestrator/poetry.lock /app/poetry.lock # <<< REMOVED THIS LINE AGAIN
COPY poc_agents/secops_pipeline/secops_orchestrator/secops_pipeline_config.json /app/secops_pipeline_config.json
COPY poc_agents/secops_pipeline/secops_orchestrator/.env.example /app/.env.example
COPY poc_agents/secops_pipeline/secops_orchestrator/entrypoint.sh /app/entrypoint.sh

# Install base dependencies directly
RUN pip install --no-cache-dir /app/agentvault_library keyring \
    langgraph==0.1.1 \
    langchain-core==0.2.23 \
    "httpx[http2,brotli]>=0.26.0,<0.27.0" \
    pydantic==2.7.1 \
    python-dotenv==1.0.1 \
    pydantic-settings==2.0 \
    tenacity==8.2.3 \
    redis>=5.0.0 \
    # Additional dependencies for LLM integration
    jsonschema>=4.18.0 \
    anyio>=3.7.1

# Ensure Redis is properly installed
RUN pip install --no-cache-dir redis

# Create user/group
RUN groupadd -r appgroup --gid 1001 && useradd --no-log-init -r -g appgroup --uid 1001 appuser

# Copy pipeline fix script
COPY poc_agents/secops_pipeline/secops_orchestrator/ensure_pipeline.py /app/ensure_pipeline.py

# Change ownership
RUN chown -R appuser:appgroup /app

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Set Python Path to include src and copied libraries
ENV PYTHONPATH=/app/src:/app/agentvault_library:/app/shared

# Switch user
USER appuser

ENTRYPOINT ["/app/entrypoint.sh"]
CMD []
