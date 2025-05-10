@echo off
REM Restores the database from a specified backup file

IF "%~1"=="" (
  echo Error: No backup file specified
  echo Usage: restore-from-backup.bat backups\filename.sql
  exit /b 1
)

IF NOT EXIST "%~1" (
  echo Error: Backup file not found: %~1
  exit /b 1
)

echo Starting database container...
docker compose --env-file .env.docker up -d db

echo Waiting for database to be ready...
timeout /t 10 /nobreak > nul

echo Restoring database from %~1...
type "%~1" | docker exec -i agentvault_registry_db psql -U postgres -d agentvault_dev

echo Database restoration completed successfully!
echo.
echo You can now start the registry with:
echo    .\start-without-wipe.bat
