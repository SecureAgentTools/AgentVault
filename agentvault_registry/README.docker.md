# Docker Setup for AgentVault Registry

## Database Authentication Fix

The database authentication issue has been fixed by creating a separate `.env.docker` file with the correct database credentials extracted from your main `.env` file.

## How to Start the Registry

### On Windows:
1. Open a command prompt in this directory
2. Run:
```
.\start-registry.bat
```

### On Linux/macOS:
1. Open a terminal in this directory
2. Make the script executable:
```
chmod +x start-registry.sh
```
3. Run:
```
./start-registry.sh
```

## What This Does

The script uses Docker Compose with the `.env.docker` file, which contains:
- The correct PostgreSQL username and password
- The database name
- The API key secret
- Email configuration settings

## Troubleshooting

If you encounter any errors:

1. Ensure Docker is running
2. Check that the `.env.docker` file exists and has the correct credentials
3. If the containers are already running, stop them first:
```
docker compose down
```
4. Try running with the detached flag to run in the background:
```
.\start-registry.bat -d
```
or
```
./start-registry.sh -d
```

## Manual Verification

To manually verify the database connection:
```
docker exec -it agentvault_registry_db psql -U postgres -d agentvault_dev
```
When prompted for password, enter: `Password1337?`
