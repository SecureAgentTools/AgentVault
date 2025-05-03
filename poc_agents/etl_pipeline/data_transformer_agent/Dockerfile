# Data Transformer Agent Dockerfile (REQ-ETL-TRN-007)
# Corrected Version

FROM python:3.11-slim-bookworm

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (libpq-dev needed for asyncpg build)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy library and SDK first
COPY agentvault_library/ /app/agentvault_library/
COPY agentvault_server_sdk/ /app/agentvault_server_sdk/

# Copy agent-specific code (NO base_agent.py copy)
COPY poc_agents/etl_pipeline/data_transformer_agent/src /app/src
COPY poc_agents/etl_pipeline/data_transformer_agent/agent-card.json /app/agent-card.json

# Install base dependencies (SDK/Library)
RUN pip install --no-cache-dir /app/agentvault_library /app/agentvault_server_sdk

# Install agent-specific Python dependencies (REQ-ETL-TRN-004)
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic python-dotenv asyncpg

# Create a non-root user
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Change ownership
RUN chown -R appuser:appgroup /app

# Switch user
USER appuser

# Set environment variables (Corrected PYTHONPATH)
ENV PORT=8041 \
    AGENT_CARD_PATH=/app/agent-card.json \
    PYTHONPATH=/app/src

# Expose the port
EXPOSE 8041

# Define the command
CMD ["uvicorn", "data_transformer_agent.main:app", "--host", "0.0.0.0", "--port", "8041", "--log-level", "info"]
