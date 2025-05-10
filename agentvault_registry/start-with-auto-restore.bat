@echo off
REM Start the Registry with automatic backup restoration if needed

REM First check if the database has data
echo Checking if database needs restoration...
docker compose --env-file .env.docker up -d db
timeout /t 5 /nobreak > nul

REM Try to query for tables
docker exec agentvault_registry_db psql -U postgres -d agentvault_dev -c "\dt" | find "0 rows" > nul
IF NOT ERRORLEVEL 1 (
  echo Database appears to be empty, attempting to restore from latest backup...
  
  REM Find the most recent backup
  set LATEST_BACKUP=
  for /f "delims=" %%i in ('dir /b /o-d backups\*.sql 2^>nul') do (
    if "!LATEST_BACKUP!"=="" set LATEST_BACKUP=backups\%%i
  )
  
  IF "!LATEST_BACKUP!"=="" (
    echo No backups found. Starting with a fresh database.
  ) ELSE (
    echo Found latest backup: !LATEST_BACKUP!
    call restore-from-backup.bat !LATEST_BACKUP!
  )
) ELSE (
  echo Database already contains tables, no restoration needed.
)

REM Start the registry without rebuilding (to avoid unnecessary wiping)
echo Starting registry...
docker compose --env-file .env.docker up

REM After user presses Ctrl+C to exit, create a backup
echo Creating backup before exit...
call auto-backup-db.bat
