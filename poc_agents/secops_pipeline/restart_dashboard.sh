#!/bin/bash
# Script to restart the dashboard services

echo "Stopping dashboard services..."
docker-compose -f docker-compose.secops.yml stop secops-redis secops-dashboard secops-dashboard-backend

echo "Starting dashboard services..."
docker-compose -f docker-compose.secops.yml up -d secops-redis secops-dashboard-backend secops-dashboard

echo "Checking services..."
docker ps | grep secops-redis
docker ps | grep secops-dashboard-backend
docker ps | grep secops-dashboard

echo "Accessing dashboard at: http://localhost:8080/dynamic.html"
