# Dynamic Dashboard Implementation Guide

## Overview

The SecOps Pipeline now includes both a static dashboard (for reliability) and a dynamic dashboard that updates in real-time as alerts are processed. The dynamic dashboard uses WebSockets to receive updates from the pipeline.

## Components

1. **Redis Message Broker**: Central message broker for pipeline events
2. **Dashboard Backend**: FastAPI service that subscribes to Redis events and forwards them to WebSocket clients
3. **Dynamic Dashboard HTML**: WebSocket-enabled dashboard that updates in real-time
4. **Redis Publisher**: Helper module for the orchestrator to publish events to Redis

## Accessing the Dashboard

1. **Static Dashboard**: http://localhost:8080/
2. **Dynamic Dashboard**: http://localhost:8080/dynamic.html

## Troubleshooting

If the dynamic dashboard is not updating:

1. **Check Redis Connection**: Make sure Redis is running and accessible
   ```bash
   docker exec secops-redis redis-cli ping
   ```

2. **Check Dashboard Backend**: Verify the backend service is running
   ```bash
   curl http://localhost:8081/health
   ```

3. **Test Event Publishing**: Send a test event to verify the event flow
   ```bash
   curl http://localhost:8081/test-broadcast
   ```

4. **Check WebSocket Connection**: Open browser developer tools and look for WebSocket errors
   - In Chrome/Firefox: Open DevTools > Network tab > Filter by WS
   - Verify a WebSocket connection to `/ws` is established

5. **Review Logs**: Check logs for errors
   ```bash
   docker-compose -f docker-compose.secops.yml logs secops-redis
   docker-compose -f docker-compose.secops.yml logs secops-dashboard-backend
   docker-compose -f docker-compose.secops.yml logs secops-orchestrator
   ```

## Working with the Dynamic Dashboard

1. **Process an Alert**: Run a sample alert through the pipeline
   ```bash
   docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert3.json
   ```

2. **Watch Updates**: The dynamic dashboard should update automatically with:
   - Pipeline flow visualization
   - Alert details
   - Enrichment results
   - LLM decision
   - Response action

## Extending the Dashboard

To add new types of visualizations:

1. Add a new event type in `redis_publisher.py`
2. Add a corresponding handler in `dynamic_dashboard.html`
3. Update the orchestrator to publish the new event type

## Reset the Dashboard

If needed, restart the dashboard components:

```bash
./restart_dashboard.sh
```