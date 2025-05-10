# SecOps Pipeline with Qwen3-8B LLM Integration

A complete Security Operations pipeline leveraging the Qwen3-8B large language model for intelligent security alert analysis and automated response.

## Overview

This pipeline processes security alerts end-to-end through various stages of analysis and response with LLM-powered decision making. The system evaluates different types of security alerts, makes severity assessments, and recommends appropriate response actions using advanced LLM reasoning.

## Key Features

- **Real-time LLM Analysis**: Direct integration with Qwen3-8B for sophisticated security reasoning
- **Transparent Decision Making**: Full visibility into LLM reasoning process
- **Automated Response Actions**: Direct action execution based on LLM recommendations
- **Real-time Dashboard**: Interactive visualization of pipeline execution
- **Robust Error Handling**: Fallback mechanisms ensure pipeline reliability

## Components

1. **Core Pipeline Architecture**:
   - `secops-orchestrator`: Coordinates the overall pipeline flow using LangGraph
   - `secops-enrichment-agent`: Gathers context on IOCs in alerts
   - `secops-investigation-agent`: Analyzes alerts with LLM reasoning
   - `secops-response-agent`: Executes determined responses
   - `secops-dashboard`: Real-time visualization of pipeline execution
   - `secops-redis`: Event bus for real-time updates

2. **LLM Integration**:
   - Direct connection to Qwen3-8B model via OpenAI-compatible API
   - OpenAI-compatible chat completions endpoint 
   - Enhanced security-specific prompts
   - Support for both detailed reasoning and fast analysis modes

3. **Response Actions**:
   - `CREATE_TICKET`: Creates tickets in external systems
   - `BLOCK_IP`: Blocks malicious IPs at the firewall
   - `ISOLATE_HOST`: Isolates compromised hosts from the network
   - `CLOSE_FALSE_POSITIVE`: Dismisses alerts determined to be false positives
   - `MANUAL_REVIEW`: Flags alerts requiring human analysis

4. **Dashboard Options**:
   - Interactive dashboard with real-time pipeline visualization
   - Detailed display of enrichment results, LLM reasoning, and response actions

## Alert Types Supported

The pipeline can process various types of security alerts:

1. **Authentication Alerts**: Failed login attempts, unusual login locations/times
2. **Malware Detection**: Ransomware, trojans, backdoors
3. **Network Scanning**: Port scans, vulnerability probing
4. **Data Exfiltration**: Unusual data transfers, insider threats

## How to Run

### Prerequisites

1. Docker and Docker Compose
2. Running Qwen3-8B instance with OpenAI-compatible API (on port 1234)
3. Created external Docker network: `docker network create agentvault_network`

### Start the Pipeline

```bash
# Start the pipeline components
docker-compose -f docker-compose.secops.yml up -d

# Process a sample alert
docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert1.json
```

## Dashboard Access

The interactive dashboard is available at:
```
http://localhost:8080/
```

For the dashboard to show real-time updates:
- Redis service must be running
- Dashboard backend must be running
- Pipeline must be executing an alert workflow

## Demo Materials

The `demo_materials` directory contains resources for showcasing the pipeline:

- Demo script with talking points
- Comparison of LLM vs. rule-based approaches
- Alert response decision matrix

## Configuration

### LLM Setup

The pipeline is configured to connect to a Qwen3-8B instance with an OpenAI-compatible API:

```yaml
# LLM configuration
- LLM_API_URL=http://host.docker.internal:1234/v1
- LLM_MODEL_NAME=qwen3-8b
- LLM_TIMEOUT_SECONDS=120
- RUNNING_IN_DOCKER=true
```

The LLM model should support the OpenAI chat completions API endpoint. Qwen3-8B with the `/no_think` directive is supported for faster response times when detailed reasoning isn't required.

### Redis for Event Publishing

For the dashboard to receive real-time updates:

```yaml
# Redis configuration
- REDIS_URL=redis://secops-redis:6379
```

## Adding New Alert Types

To add new alert types:

1. Create JSON alert files in `input_alerts/`
2. Ensure the LLM prompts can handle the new alert type
3. Update dashboard to display relevant fields

## License

This project is available as a free product for public use.

## Acknowledgments

- AgentVault Framework for agent orchestration
- Qwen3-8B LLM model for security intelligence
- LangGraph for pipeline state management