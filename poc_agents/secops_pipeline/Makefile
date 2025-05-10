
# Makefile for SecOps Pipeline

# Default target
.PHONY: all
all: help

# Help target
.PHONY: help
help:
	@echo "SecOps Pipeline Commands:"
	@echo "------------------------"
	@echo "make start       - Start the SecOps pipeline with Docker Compose"
	@echo "make stop        - Stop all containers in the pipeline"
	@echo "make build       - Rebuild all containers"
	@echo "make logs        - Show logs from all containers"
	@echo "make network     - Create the required Docker network"
	@echo "make clean       - Stop containers and remove them"
	@echo "make reset-all   - Deep clean (stop, remove containers, prune)"

# Create the Docker network if it doesn't exist
.PHONY: network
network:
	@echo "Creating Docker network if it doesn't exist..."
	-docker network create agentvault_network

# Start the pipeline
.PHONY: start
start: network
	@echo "Starting SecOps pipeline..."
	docker-compose -f docker-compose.secops.yml up -d

# Build or rebuild the services
.PHONY: build
build: network
	@echo "Building SecOps pipeline containers..."
	docker-compose -f docker-compose.secops.yml build

# Show logs
.PHONY: logs
logs:
	@echo "Showing logs from all containers..."
	docker-compose -f docker-compose.secops.yml logs -f

# Stop all services
.PHONY: stop
stop:
	@echo "Stopping SecOps pipeline..."
	docker-compose -f docker-compose.secops.yml stop

# Clean up (stop and remove containers)
.PHONY: clean
clean:
	@echo "Cleaning up SecOps pipeline containers..."
	docker-compose -f docker-compose.secops.yml down

# Deep clean (remove containers, volumes, etc.)
.PHONY: reset-all
reset-all: clean
	@echo "Performing deep clean..."
	docker-compose -f docker-compose.secops.yml down --volumes --remove-orphans
	docker system prune -f --volumes
