@echo off
cd ..\..\..\
echo Running HumanReadableID tests...
python -m pytest agentvault_registry\tests\registry_api\test_by_human_id.py -v
pause
