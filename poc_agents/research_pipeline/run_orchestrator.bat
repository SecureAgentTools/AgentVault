@echo off
echo Running the agent discovery test first...
python test_orchestrator_discovery.py

echo.
echo If the test passes, now running the full orchestrator...
python orchestrator.py

echo.
echo Done!
pause
