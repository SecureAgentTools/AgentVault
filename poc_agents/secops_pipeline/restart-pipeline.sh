#!/bin/bash

echo "Stopping any running containers..."
docker-compose -f docker-compose.secops.yml down

echo "Building containers with latest code changes..."
docker-compose -f docker-compose.secops.yml build

echo "Creating network if it doesn't exist..."
docker network create agentvault_network 2>/dev/null || true

echo "Starting SecOps pipeline..."
docker-compose -f docker-compose.secops.yml up

echo "Pipeline started. Press Ctrl+C to stop."
