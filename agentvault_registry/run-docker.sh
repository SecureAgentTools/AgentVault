#!/bin/bash

# Clean up any existing containers first
docker-compose down

# Build and start containers
docker-compose up --build

# To run in detached mode (background), uncomment this line instead:
# docker-compose up --build -d