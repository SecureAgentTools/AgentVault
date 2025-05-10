# SecOps Dashboard Troubleshooting Guide

## Overview

This guide provides troubleshooting steps to resolve the real-time data flow issue with the SecOps dashboard.

## Problem Description

The dashboard is not receiving real-time updates despite:
- Backend service running correctly
- WebSocket connection appearing to establish 
- Redis being accessible
- Events being published to Redis

## Automated Fix Scripts

Three scripts have been created to help diagnose and fix the issues:

1. **test_redis_connection.ps1** - Tests Redis connectivity and messaging
2. **test_websocket.ps1** - Tests WebSocket connections and messaging
3. **fix_dashboard_flow.ps1** - Comprehensive fix that restarts services in the correct order

Run the fix script first to attempt an automated fix:

```powershell
.\fix_dashboard_flow.ps1
```

## Manual Troubleshooting Steps

If the automated fix doesn't resolve the issue, follow these manual steps:

### 1. Verify Redis Connection

```powershell
# Test redis connection
docker exec secops-redis redis-cli ping

# In one terminal, subscribe to the channel
docker exec -it secops-redis redis-cli
> SUBSCRIBE secops_events

# In another terminal, publish a test message
docker exec secops-redis redis-cli PUBLISH secops_events "{\"event_type\":\"test_event\",\"message\":\"Test message\"}"
```

### 2. Check Backend Logs for Redis Connection Issues

```powershell
docker logs secops-dashboard-backend | findstr "Redis redis"
```

If you see Redis connection errors, ensure the connection URL is correct in both the code and environment variables.

### 3. Verify WebSocket Connection

```powershell
# Check backend logs for WebSocket connections
docker logs secops-dashboard-backend | findstr "WebSocket"
```

### 4. Check Browser DevTools

1. Open the dashboard in your browser
2. Open DevTools (F12)
3. Go to Network tab
4. Filter for "WS" (WebSocket)
5. Refresh the page
6. Verify a WebSocket connection to "/ws" is established
7. Check the connection status and messages

### 5. Test End-to-End Flow

```powershell
# Send a test broadcast via API
Invoke-RestMethod -Uri "http://localhost:8080/test-broadcast"

# Check if the message appears in the dashboard
```

### 6. Restart Services in Correct Order

```powershell
# Restart services in correct order
docker-compose -f docker-compose.secops.yml restart secops-redis
Start-Sleep -Seconds 5
docker-compose -f docker-compose.secops.yml restart secops-dashboard-backend
Start-Sleep -Seconds 10
docker-compose -f docker-compose.secops.yml restart secops-dashboard
```

## Common Issues and Solutions

### Redis Connection Issues

- **Symptom**: Backend logs show Redis connection errors
- **Solution**: Check that the Redis URL is correct. It should be `redis://host.docker.internal:6379` for Windows Docker.

### WebSocket Connection Issues

- **Symptom**: WebSocket connection appears to establish but messages don't arrive
- **Solution**: 
  1. Check Nginx proxy configuration
  2. Ensure browser isn't blocking WebSockets
  3. Verify the backend is successfully subscribing to Redis channel

### Event Format Issues

- **Symptom**: WebSocket connects but dashboard doesn't update
- **Solution**: Ensure events published to Redis match the exact format expected by the dashboard frontend

## Testing the Fix

After applying fixes, run a full pipeline simulation:

```powershell
.\simulate-pipeline.ps1
```

Monitor the dashboard to verify it receives and displays the events properly.

## Key Components to Check

1. **Redis Connection** in the backend code
2. **Redis Subscription** to the "secops_events" channel
3. **WebSocket Forwarding** of Redis messages
4. **Nginx Proxy** for WebSocket connections
5. **Browser Console** for JavaScript errors

If all else fails, consider rebuilding the containers from scratch:

```powershell
docker-compose -f docker-compose.secops.yml down
docker-compose -f docker-compose.secops.yml up -d
```
