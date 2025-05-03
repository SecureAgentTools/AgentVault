# ETL Pipeline Orchestrator Dockerfile
# Corrected Version 2 (Fixed CMD)

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
COPY poc_agents/etl_pipeline/etl_pipeline_orchestrator/src /app/src
COPY poc_agents/etl_pipeline/etl_pipeline_orchestrator/etl_config.json /app/etl_config.json
COPY poc_agents/etl_pipeline/etl_pipeline_orchestrator/.env /app/.env
COPY poc_agents/etl_pipeline/etl_pipeline_orchestrator/entrypoint.sh /app/entrypoint.sh

# Install dependencies
RUN pip install --no-cache-dir /app/agentvault_library
RUN pip install --no-cache-dir \
    langgraph==0.1.1 \
    langchain-core==0.2.23 \
    "httpx[http2,brotli]>=0.26.0,<0.27.0" \
    pydantic==2.7.1 \
    python-dotenv==1.0.1 \
    pydantic-settings==2.0 \
    tenacity==8.2.3
    # Add asyncpg here if orchestrator needs DB access

# Create user/group
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Add host.docker.internal
RUN echo "host.docker.internal host-gateway" >> /etc/hosts || true

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Set Python Path
ENV PYTHONPATH=/app/src:/app/agentvault_library

# Switch user
USER appuser

# Default command
ENTRYPOINT ["/app/entrypoint.sh"]
# CORRECTED CMD: Use JSON array form with only the argument, no comment.
CMD ["/data/input_data.csv"]
