@echo off
REM Automatically backs up the database to a local file

echo Creating database backup directory...
mkdir backups 2>nul

echo Backing up database...
set TIMESTAMP=%date:~-4,4%%date:~-7,2%%date:~-10,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set BACKUP_FILE=backups\db_backup_%TIMESTAMP%.sql

docker exec agentvault_registry_db pg_dump -U postgres -d agentvault_dev > %BACKUP_FILE%

echo Backup saved to %BACKUP_FILE%
echo.
echo You can restore this backup using: 
echo    .\restore-from-backup.bat %BACKUP_FILE%
