@echo off
REM This script starts the registry WITHOUT wiping the database under any circumstances

echo Creating external volume if it doesn't exist...
docker volume create agentvault_registry_postgres_data_permanent

echo Starting registry components...
docker compose --env-file .env.docker up %*

echo Registry should now be running. Your database is stored in a permanent volume
echo named 'agentvault_registry_postgres_data_permanent' which will persist across restarts.
