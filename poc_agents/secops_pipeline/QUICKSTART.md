# SecOps Pipeline Quick Start Guide

This guide will help you quickly set up and run the SecOps Pipeline with Qwen3-8B LLM integration.

## Prerequisites

1. Docker and Docker Compose installed
2. LM Studio with Qwen3-8B model (for LLM processing)

## Step 1: Start LM Studio

1. Open LM Studio
2. Select the Qwen3-8B model
3. Click "Start Server"
4. Ensure it's running on http://localhost:1234

## Step 2: Start the Pipeline Components

```bash
# Create the required Docker network if it doesn't exist
docker network create agentvault_network

# Start all pipeline components, including Redis and dashboard
docker-compose -f docker-compose.secops.yml up -d
```

## Step 3: Access the Dashboard

You have three dashboard options:

1. **Static Dashboard** (baseline view, no real-time updates):
   ```
   http://localhost:8080/
   ```

2. **Dynamic Dashboard with WebSockets** (real-time updates):
   ```
   http://localhost:8080/dynamic.html
   ```

3. **Dynamic Dashboard with SSE** (alternative real-time updates):
   ```
   http://localhost:8080/sse.html
   ```

If you have issues with the WebSocket-based dashboard, try the SSE version which uses a different connection technology.

## Step 4: Process Alert Scenarios

Run these commands to process different alert types and see dynamic updates on the dashboard:

```bash
# Scenario 1: Authentication Alert
docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert1.json

# Scenario 2: Malware Alert
docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert3.json

# Scenario 3: Network Scanning Alert
docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert4.json

# Scenario 4: Data Exfiltration Alert
docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert5.json
```

Watch the dashboard update in real-time as each alert is processed!

## Troubleshooting

### Dashboard not updating?

1. **Try the SSE Dashboard instead of WebSockets**:
   ```
   http://localhost:8080/sse.html
   ```
   Some environments have issues with WebSockets. The SSE dashboard uses a different technology.

2. **Test the WebSocket connection**:
   ```
   http://localhost:8080/test_websocket.html
   ```
   This test page will show if the WebSocket connection can be established.

3. **Check if Redis is running**:
   ```bash
   docker logs secops-redis
   ```

4. **Check if the dashboard backend is running**:
   ```bash
   docker logs secops-dashboard-backend
   ```

5. **Check NGINX logs for proxy errors**:
   ```bash
   docker logs secops-dashboard
   ```

### LLM connection issues?

1. Make sure LM Studio is running on port 1234
2. Check that you have Qwen3-8B loaded in LM Studio
3. Verify the Docker network allows connections to host.docker.internal

## Stopping the Pipeline

```bash
docker-compose -f docker-compose.secops.yml down
```