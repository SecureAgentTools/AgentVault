@echo off
echo ===============================================
echo SecOps Pipeline with Qwen3-8B LLM - Restart Script
echo ===============================================
echo.

REM Check if LLM is configured properly
echo Checking LLM configuration...
python -m shared.test_llm > nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo WARNING: LLM test failed. Run test_llm.cmd for detailed diagnostics.
    echo LLM might not be properly configured or LM Studio might not be running.
    echo.
    echo Do you want to continue anyway? (Y/N)
    set /p choice=
    if /i not "%choice%"=="Y" (
        echo Aborting restart.
        exit /b 1
    )
    echo Continuing despite LLM configuration issues...
)

echo.
echo Stopping existing containers...
docker compose -f docker-compose.secops.yml down

echo.
echo Starting SecOps pipeline with Qwen3-8B LLM integration...
docker compose -f docker-compose.secops.yml up -d

echo.
echo Checking container status...
timeout /t 5 /nobreak > nul
docker compose -f docker-compose.secops.yml ps

echo.
echo View logs with: docker compose -f docker-compose.secops.yml logs -f
echo.
echo ===============================================
echo SecOps Pipeline restart complete!
echo ===============================================
