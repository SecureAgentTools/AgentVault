#!/bin/bash

# This script builds and runs the dockerized registry

echo "Building and starting the AgentVault Registry using Docker..."
docker-compose up --build -d

echo "
=====================================================
AgentVault Registry is now running in Docker!
=====================================================

Access the registry at:
- API: http://localhost:8000/api/v1
- Documentation: http://localhost:8000/docs
- UI: http://localhost:8000/ui

To view logs:
  docker-compose logs -f registry

To stop the registry:
  docker-compose down

To stop and remove all data (including database):
  docker-compose down -v
"