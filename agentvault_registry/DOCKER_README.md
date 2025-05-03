# Dockerized AgentVault Registry

This guide explains how to run the AgentVault Registry using Docker, which containerizes the application and makes it easier to deploy and connect with other Docker-based agents.

## Prerequisites

- Docker and Docker Compose installed
- No other services using port 5432 (PostgreSQL) or 8000 (Registry API)

## Quick Start

### Windows

Run the following command from the `agentvault_registry` directory:

```
run_dockerized_registry.bat
```

### Linux/Mac

Run the following command from the `agentvault_registry` directory:

```bash
chmod +x run_dockerized_registry.sh
./run_dockerized_registry.sh
```

## Manual Setup

If you prefer to run the commands manually:

1. Build and start the containers:
   ```bash
   docker-compose up --build -d
   ```

2. The registry will be available at:
   - API: http://localhost:8000/api/v1
   - Documentation: http://localhost:8000/docs
   - UI: http://localhost:8000/ui

3. View logs:
   ```bash
   docker-compose logs -f registry
   ```

4. Stop the service:
   ```bash
   docker-compose down
   ```

## Configuration

The Docker Compose setup uses the following default configuration:

- PostgreSQL database with credentials from the .env file
- API running on port 8000
- Registry API key secret from the .env file

To modify this configuration, edit the `docker-compose.yml` file.

## Connecting to Docker-based Agents

When agents are running in Docker containers on the same Docker network, they can reach the registry using the internal Docker network hostname:

- Internal hostname: `registry`
- Internal port: `8000`

For example, agents can connect to the registry at: `http://registry:8000/api/v1`

## Troubleshooting

### Database Connection Issues

If the registry container can't connect to the database, you may see errors about PostgreSQL connection failures. Make sure:

1. The database container is running: `docker ps | grep agentvault_registry_db`
2. The DATABASE_URL environment variable in docker-compose.yml is correct
3. The database is initialized: `docker-compose logs db`

### Rebuilding Everything

To completely restart with a clean environment:

```bash
docker-compose down -v
docker-compose up --build -d
```

The `-v` flag removes volumes, which will delete all database data.
