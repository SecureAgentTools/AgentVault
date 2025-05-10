# SecOps Pipeline with Qwen3-8B LLM Integration

This is an enhanced version of the SecOps pipeline that uses the Qwen3-8B language model through an OpenAI-compatible API for advanced security analysis and response determination.

## Prerequisites

- Docker and Docker Compose installed
- Qwen3-8B model running with OpenAI-compatible API on port 1234
- AgentVault registry service running

## Setup Instructions

1. **Prepare Qwen3-8B API**:
   - Ensure your Qwen3-8B instance is running with an OpenAI-compatible API
   - The API should be accessible on port 1234
   - Verify the chat completions endpoint is working properly

2. **Test LLM Configuration**:
   - You can send a test request to verify the API is working:
   ```bash
   curl -X POST http://localhost:1234/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen3-8b",
       "messages": [{"role": "user", "content": "Say hello!"}],
       "temperature": 0.7
     }'
   ```
   - If this returns a valid response, the LLM is properly configured

3. **Start the Pipeline**:
   - Run `docker-compose -f docker-compose.secops.yml up -d` to start the pipeline
   - This will start all required containers including the orchestrator, agents, Redis, and dashboard

## Using the Pipeline

The SecOps pipeline now uses the Qwen3-8B model for:

- Security alert analysis and investigation
- Severity assessment with confidence ratings
- Determining appropriate response actions
- Providing detailed reasoning for security decisions

Sample alert files are provided in the `input_alerts` directory. To run the pipeline with a specific alert:

```bash
docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert1.json
```

## Pipeline Flow

1. **Alert Ingestion**: Standardizes the alert format
2. **Enrichment Phase**: Gathers context on any Indicators of Compromise (IoCs)
3. **LLM Investigation**: Analyzes the alert with Qwen3-8B reasoning
4. **Response Determination**: LLM decides on appropriate actions
5. **Action Execution**: Implements the determined response

The dashboard shows this flow in real-time, including all enrichment data and LLM reasoning.

## Monitoring and Logs

- View logs for all containers: `docker compose -f docker-compose.secops.yml logs -f`
- View logs for a specific service: `docker compose -f docker-compose.secops.yml logs -f secops-orchestrator`
- Access the dashboard at `http://localhost:8080/`

## Troubleshooting

If you encounter LLM-related errors:

1. Ensure your Qwen3-8B API is running and accessible
2. Check that the API endpoint is correctly configured in the environment variables
3. Verify the model name matches what your API expects
4. Inspect container logs for specific error messages
5. Try increasing the timeout value if complex queries are timing out

## Configuration

The LLM configuration can be adjusted in `docker-compose.secops.yml`:

```yaml
# LLM configuration
- LLM_API_URL=http://host.docker.internal:1234/v1
- LLM_MODEL_NAME=qwen3-8b
- LLM_TIMEOUT_SECONDS=120
- RUNNING_IN_DOCKER=true
```

For local testing without Docker, you may need to use `localhost` instead of `host.docker.internal`.

## Advanced Configuration

### Qwen3-8B Specific Features

The integration supports Qwen3-8B specific features like the `/no_think` directive, which can be enabled or disabled in the code. When enabled, the directive is appended to user messages to request concise, direct responses without detailed reasoning steps.

### Fallback Mechanisms

The system includes robust fallback to mock responses if the LLM fails, ensuring pipeline reliability even if the LLM service is unavailable or returns errors.

### Custom Alert Types

To create custom alert types, you can extend the LLM prompts with examples specific to your security domain. The flexible nature of the LLM integration allows it to adapt to various security alert formats without hardcoded rules.
