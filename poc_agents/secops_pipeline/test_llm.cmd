@echo off
echo Testing LLM configuration for SecOps pipeline...
echo Make sure LM Studio is running with the Qwen3-8B model loaded!
echo.

REM Run the test script
python -m shared.test_llm

REM Check if test passed
if %ERRORLEVEL% EQU 0 (
    echo.
    echo =====================================================
    echo Success! LLM is properly configured.
    echo You can now run the SecOps pipeline.
    echo =====================================================
) else (
    echo.
    echo =====================================================
    echo Test failed with error code %ERRORLEVEL%
    echo Please check the error messages above and fix the configuration.
    echo =====================================================
)

pause
