@echo off
echo Running all example tickets through the Support Pipeline...
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

rem Wait briefly to ensure all services are ready
timeout /t 5 > nul

rem Create a backup of the original docker-compose.yml
echo Creating backup of docker-compose.yml...
copy docker-compose.yml docker-compose.yml.bak > nul

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
    powershell -Command "$ticketBody = '%found_body%'; $pattern = '([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+|[a-zA-Z0-9_-]+(?:_user|_id)\w*)'; $matches = [regex]::Matches($ticketBody, $pattern); if ($matches.Count -gt 0) { Write-Output $matches[0].Value } else { Write-Output 'default-customer-id' }" > temp_customer_%%i.txt
    set /p customer_id=<temp_customer_%%i.txt
    
    rem Print ticket details
    echo.
    echo SUBJECT: %found_subject%
    echo CUSTOMER ID: %customer_id%
    echo BODY: %found_body%...
    echo.
    
    rem Combine subject and body
    set "ticket_text=%found_subject%. %found_body%"
    
    rem Update docker-compose.yml to use this ticket
    echo Updating docker-compose.yml with ticket %%i...
    powershell -Command "(Get-Content docker-compose.yml) -replace '# command: \[\""python\"", \""-m\"", \""support_orchestrator.run\"", \""[^""]*\"", \""[^""]*\""\]', 'command: [\"python\", \"-m\", \"support_orchestrator.run\", \"%ticket_text%\", \"%customer_id%\"]' | Set-Content docker-compose.yml"
    
    rem Restart the orchestrator with the new configuration
    echo Restarting orchestrator with ticket %%i...
    docker-compose up -d --no-deps support-orchestrator
    
    echo Waiting for processing to complete...
    timeout /t 5 > nul
    
    echo.
    echo === LOGS FOR TICKET %%i ===
    docker logs support-pipeline-orchestrator --tail 100
    
    echo.
    echo Waiting 10 seconds before next ticket...
    timeout /t 10 > nul
    
    rem Clean up temp files
    del temp_ticket_%%i.txt 2>nul
    del temp_customer_%%i.txt 2>nul
)

rem Restore the original docker-compose.yml
echo.
echo === ALL TICKETS PROCESSED ===
echo.
echo Restoring original docker-compose.yml...
copy docker-compose.yml.bak docker-compose.yml > nul
del docker-compose.yml.bak 2>nul

echo.
echo === FINAL LOGS ===
docker logs support-pipeline-orchestrator --tail 20

echo.
echo Complete! All example tickets have been processed.
