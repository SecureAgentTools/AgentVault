# E-commerce Pipeline Orchestrator Dockerfile
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

# Copy library first (assuming build context is monorepo root)
COPY agentvault_library/ /app/agentvault_library/

# Copy orchestrator code
COPY poc_agents/ecommerce_pipeline/ecommerce_pipeline_orchestrator/src /app/src
# Copy config files to both locations to ensure they're found
COPY poc_agents/ecommerce_pipeline/ecommerce_pipeline_orchestrator/ecommerce_config.json /app/ecommerce_config.json
COPY poc_agents/ecommerce_pipeline/ecommerce_pipeline_orchestrator/ecommerce_config.json /app/src/ecommerce_orchestrator/ecommerce_config.json
COPY poc_agents/ecommerce_pipeline/ecommerce_pipeline_orchestrator/.env /app/.env
COPY poc_agents/ecommerce_pipeline/ecommerce_pipeline_orchestrator/.env /app/src/ecommerce_orchestrator/.env
COPY poc_agents/ecommerce_pipeline/ecommerce_pipeline_orchestrator/entrypoint.sh /app/entrypoint.sh

# Install dependencies directly with pip (following research_pipeline pattern)
# Note: Library path needs adjustment if WORKDIR changes or PYTHONPATH is only /app/src
# We install library first, then dependencies, then set final PYTHONPATH

# Install library using its setup.py or pyproject.toml from the copied location
# Assuming agentvault_library has a pyproject.toml for build
RUN pip install --no-cache-dir /app/agentvault_library

# Install Python dependencies for the orchestrator
# Assuming a pyproject.toml exists for the orchestrator at the standard location relative to context
# If not, list dependencies explicitly as before
RUN pip install --no-cache-dir \
    langgraph==0.1.1 \
    langchain-core==0.2.23 \
    "httpx>=0.26.0,<0.27.0" \
    pydantic==2.7.1 \
    python-dotenv==1.0.1 \
    pydantic-settings==2.0 \
    tenacity==8.2.3 \
    "langchain>=0.2.11" \
    "langchain-community>=0.2.10"

# Create a non-root user
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Create artifact directory and set permissions (adjust path if needed)
RUN mkdir -p /app/pipeline_artifacts/ecommerce && chown -R appuser:appgroup /app/pipeline_artifacts

# Add extra hosts to resolve host.docker.internal
RUN echo "host.docker.internal host-gateway" >> /etc/hosts || true

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Set Python Path correctly for src layout
ENV PYTHONPATH=/app/src:/app/agentvault_library

# Switch user AFTER setting permissions and ENV vars that might be needed by root
USER appuser

# Default command to run the orchestrator
ENTRYPOINT ["/app/entrypoint.sh"]
# No arguments needed as entrypoint handles everything
CMD []
