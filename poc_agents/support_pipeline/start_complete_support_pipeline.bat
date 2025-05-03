@echo off
echo Starting the complete Support Ticket Pipeline with registry and agents...

echo ------------------------------------------------------------------
echo IMPORTANT: Before running this script, make sure you have:
echo 1. Started an LLM server accessible at the URL defined in
echo    .\response_suggester_agent\.env (likely http://localhost:1234)
echo    (e.g., LM Studio, Ollama, or similar local LLM server)
echo 2. Selected a suitable model in your LLM server.
echo ------------------------------------------------------------------
echo.
pause

rem Ensure the AgentVault registry is running first
echo Ensuring registry is running...
cd D:\AgentVault\agentvault_registry
docker-compose up -d
cd ..\poc_agents\support_pipeline

rem Wait for the registry to be potentially ready
echo Waiting for registry to initialize (15 seconds)...
timeout /t 15 > NUL

rem Go back to the support pipeline directory (redundant if already there, but safe)
cd D:\AgentVault\poc_agents\support_pipeline

rem Stop any existing support pipeline containers defined in the compose file
echo Stopping any existing support pipeline containers...
docker-compose down

rem Make sure the agentvault_network exists
echo Ensuring agentvault_network exists...
docker network create agentvault_network > NUL 2>&1 || echo Network 'agentvault_network' already exists or could not be created.

rem Build all containers defined in the support pipeline compose file
echo Building all support pipeline containers (use --no-cache if needed)...
docker-compose build

rem Start all services defined in the support pipeline compose file in detached mode
echo Starting all support pipeline services...
docker-compose up -d

echo.
echo Support Pipeline services started in detached mode.
echo Use 'docker-compose logs -f' to view logs.
echo Use '.\check_connectivity_support.bat' to test connections after a brief wait.
echo Use 'docker-compose down' to stop the services.
