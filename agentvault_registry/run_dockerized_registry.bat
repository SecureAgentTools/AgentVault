@echo off
echo Building and starting the AgentVault Registry using Docker...
docker-compose up --build -d

echo.
echo =====================================================
echo AgentVault Registry is now running in Docker!
echo =====================================================
echo.
echo Access the registry at:
echo - API: http://localhost:8000/api/v1
echo - Documentation: http://localhost:8000/docs
echo - UI: http://localhost:8000/ui
echo.
echo To view logs:
echo   docker-compose logs -f registry
echo.
echo To stop the registry:
echo   docker-compose down
echo.
echo To stop and remove all data (including database):
echo   docker-compose down -v
echo.
