# Dynamics Pipeline Orchestrator Dockerfile
# Corrected Version 6 (Fix PYTHONPATH for library import)

FROM python:3.11-slim-bookworm

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (ADDED netcat-openbsd)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy library first
COPY agentvault_library/ /app/agentvault_library/

# Copy orchestrator code
COPY poc_agents/dynamics_pipeline/dynamics_pipeline_orchestrator/src /app/src
COPY poc_agents/dynamics_pipeline/dynamics_pipeline_orchestrator/dynamics_config_fixed.json /app/dynamics_config.json
COPY poc_agents/dynamics_pipeline/dynamics_pipeline_orchestrator/.env /app/.env
COPY poc_agents/dynamics_pipeline/dynamics_pipeline_orchestrator/entrypoint.sh /app/entrypoint.sh

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

# Add host.docker.internal
RUN echo "host.docker.internal host-gateway" >> /etc/hosts || true

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Set Python Path - CORRECTED: Remove agentvault_library source path
ENV PYTHONPATH=/app/src

# Switch user
USER appuser

# Default command
ENTRYPOINT ["/app/entrypoint.sh"]
# CORRECTED CMD: Use JSON exec form again. The entrypoint script will handle passing these correctly.
CMD ["ACC-GUID-SVA"]
