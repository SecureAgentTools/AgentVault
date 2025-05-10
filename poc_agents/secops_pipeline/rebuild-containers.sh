#!/bin/bash

echo "Stopping any running containers..."
docker-compose -f docker-compose.secops.yml down

echo "Building containers with latest code changes..."
docker-compose -f docker-compose.secops.yml build

echo "Containers have been rebuilt successfully."
echo "Run 'docker-compose -f docker-compose.secops.yml up' to start the pipeline."
