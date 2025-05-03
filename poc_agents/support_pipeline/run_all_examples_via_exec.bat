@echo off
echo Running all example tickets through the Support Pipeline using docker exec...
echo.

rem Make sure the support pipeline is running first
echo Checking if support pipeline is already running...
docker ps | find "support-pipeline-orchestrator" > nul
if errorlevel 1 (
    echo Support pipeline not running. Starting it...
    call .\start_complete_support_pipeline.bat
) else (
    echo Support pipeline is already running.
)

rem Create output directory for logs
if not exist "example_run_logs" mkdir example_run_logs

rem Run through all 10 example tickets
for /l %%i in (1, 1, 10) do (
    echo.
    echo ==================================================
    echo === PROCESSING EXAMPLE TICKET %%i ===
    echo ==================================================
    echo.
    
    rem Extract ticket information
    echo Extracting ticket %%i from example_tickets.txt...
    powershell -Command "$content = Get-Content -Raw -Path '.\example_tickets.txt'; $pattern = 'Ticket %%i \([^)]+\):\r?\nSubject: ([^\r\n]+)([\s\S]+?)(?=\r?\n-{10,}|\z)'; $matches = [regex]::Match($content, $pattern); if ($matches.Success) { $subject = $matches.Groups[1].Value.Trim(); $body = $matches.Groups[2].Value.Trim(); Write-Output $subject; Write-Output '---BODY_SEPARATOR---'; Write-Output $body; } else { Write-Output 'ERROR: Ticket not found'; }" > temp_ticket_%%i.txt
    
    rem Read the extracted information
    set "found_subject="
    set "found_body="
    set "customer_id=default-customer-id"
    
    for /f "usebackq delims=" %%j in (temp_ticket_%%i.txt) do (
        if not defined found_subject (
            set "found_subject=%%j"
        ) else if "%%j"=="---BODY_SEPARATOR---" (
            rem Skip the separator
        ) else if not defined found_body (
            set "found_body=%%j"
        )
    )
    
    rem Extract customer identifier
    powershell -Command "$ticketBody = Get-Content -Raw temp_ticket_%%i.txt; $pattern = '([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+|[a-zA-Z0-9_-]+(?:_user|_id)\w*)'; $matches = [regex]::Matches($ticketBody, $pattern); if ($matches.Count -gt 0) { Write-Output $matches[0].Value } else { Write-Output 'default-customer-id' }" > temp_customer_%%i.txt
    set /p customer_id=<temp_customer_%%i.txt
    
    rem Print ticket details
    echo.
    echo SUBJECT: %found_subject%
    echo CUSTOMER ID: %customer_id%
    echo BODY: %found_body:~0,80%...
    echo.
    
    rem Combine subject and body for the ticket text
    set "ticket_text=%found_subject%. %found_body%"
    
    rem Escape quotes in the ticket text for passing to docker exec
    set "ticket_text=%ticket_text:"=\"%"
    
    echo Running with ticket %%i via docker exec...
    
    rem Start logging the container output to a file
    start cmd /c "docker logs -f support-pipeline-orchestrator > example_run_logs\ticket_%%i_logs.txt"
    
    rem Run the command inside the container
    docker exec -it support-pipeline-orchestrator python -m support_orchestrator.run "%ticket_text%" "%customer_id%"
    
    echo.
    echo === TICKET %%i COMPLETED ===
    echo Check example_run_logs\ticket_%%i_logs.txt for full logs
    echo.
    
    echo Waiting 5 seconds before next ticket...
    timeout /t 5 > nul
    
    rem Stop log capture (kill the process, a bit crude but effective)
    taskkill /f /im cmd.exe /fi "WINDOWTITLE eq *docker logs*" > nul 2>&1
    
    rem Clean up temp files
    del temp_ticket_%%i.txt 2>nul
    del temp_customer_%%i.txt 2>nul
)

echo.
echo ===================================================
echo === ALL TICKETS PROCESSED ===
echo Logs for each ticket saved in the example_run_logs folder
echo.
echo To view logs for a specific ticket, check:
echo example_run_logs\ticket_X_logs.txt
echo.
echo To view the current logs from the container:
echo docker logs support-pipeline-orchestrator
echo ===================================================
