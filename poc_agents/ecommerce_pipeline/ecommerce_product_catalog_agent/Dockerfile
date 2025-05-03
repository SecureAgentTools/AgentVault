# Product Catalog Agent Dockerfile
FROM python:3.11-slim-bookworm

WORKDIR /app

# Set environment variables - Ensure no stray characters
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (minimal for now)
# Ensure line continuation backslashes are correct and no invalid characters
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    # libpq-dev \ # Uncomment if using asyncpg
    && rm -rf /var/lib/apt/lists/*

# Copy library and SDK first (Paths relative to build context - monorepo root)
COPY agentvault_library/ /app/agentvault_library/
COPY agentvault_server_sdk/ /app/agentvault_server_sdk/

# Copy agent code and base agent (Paths relative to build context - monorepo root)
COPY poc_agents/research_pipeline/base_agent.py /app/base_agent.py
COPY poc_agents/ecommerce_pipeline/ecommerce_product_catalog_agent/src /app/src
COPY poc_agents/ecommerce_pipeline/ecommerce_product_catalog_agent/agent-card.json /app/agent-card.json

# Install base dependencies (SDK/Library)
RUN pip install --no-cache-dir /app/agentvault_library /app/agentvault_server_sdk

# Install agent-specific Python dependencies
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic httpx python-dotenv # asyncpg

# Create a non-root user
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Change ownership
RUN chown -R appuser:appgroup /app

# Switch user
USER appuser

# Set environment variables - Ensure no stray characters
ENV PORT=8021 \
    AGENT_CARD_PATH=/app/agent-card.json \
    PYTHONPATH=/app:/app/src

# Expose the port
EXPOSE 8021

# Define the command
CMD ["uvicorn", "ecommerce_product_catalog_agent.main:app", "--host", "0.0.0.0", "--port", "8021", "--log-level", "info"]
