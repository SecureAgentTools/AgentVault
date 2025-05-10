@echo off
REM Start the Registry with the correct environment variables WITHOUT wiping the database

REM First, stop any existing containers (but don't remove volumes)
docker compose down

REM Use the Docker .env file with the proper credentials and rebuild the images
docker compose --env-file .env.docker up --build %*