#!/bin/bash
# Check if the Redis and dashboard backend containers are running
echo "Checking services..."
docker ps | grep secops-redis
docker ps | grep secops-dashboard-backend

# Check Redis connectivity
echo "Testing Redis connection..."
docker exec secops-redis redis-cli ping

# Check dashboard backend health
echo "Testing dashboard backend health..."
curl http://localhost:8081/health
