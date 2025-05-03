@echo off
setlocal EnableDelayedExpansion

rem Get ticket number from command line argument, default to 2 if not provided
set "TICKET_NUMBER=%~1"
if "%TICKET_NUMBER%"=="" set "TICKET_NUMBER=2"
echo Running Example Ticket %TICKET_NUMBER%...

rem Check if support pipeline is running
echo Checking if support pipeline is running...
docker ps | find "support-pipeline-orchestrator" > nul
if errorlevel 1 (
    echo Support pipeline is not running. Starting it...
    call .\start_complete_support_pipeline.bat
    rem Wait for pipeline to start
    timeout /t 30 > nul
) else (
    echo Support pipeline is already running.
)

rem Extract ticket information
echo Extracting ticket %TICKET_NUMBER% from example_tickets.txt...
powershell -Command "$content = Get-Content -Raw -Path '.\example_tickets.txt'; $pattern = 'Ticket %TICKET_NUMBER% \([^)]+\):\r?\nSubject: ([^\r\n]+)([\s\S]+?)(?=\r?\n-{10,}|\z)'; $matches = [regex]::Match($content, $pattern); if ($matches.Success) { $subject = $matches.Groups[1].Value.Trim(); $body = $matches.Groups[2].Value.Trim(); Write-Output $subject; Write-Output '---BODY_SEPARATOR---'; Write-Output $body; } else { Write-Output 'ERROR: Ticket not found'; }" > temp_ticket.txt

rem Read extracted ticket content
set "subject="
set "body="
set "reading_body=0"

for /f "usebackq delims=" %%a in (temp_ticket.txt) do (
    if "!reading_body!"=="1" (
        set "body=!body!%%a "
    ) else if "%%a"=="---BODY_SEPARATOR---" (
        set "reading_body=1"
    ) else if "!subject!"=="" (
        set "subject=%%a"
    )
)

rem Extract customer identifier
powershell -Command "$ticketBody = '%body%'; $pattern = '([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+|[a-zA-Z0-9_-]+(?:_user|_id)\w*)'; $matches = [regex]::Matches($ticketBody, $pattern); if ($matches.Count -gt 0) { Write-Output $matches[0].Value } else { Write-Output 'default-customer-id' }" > temp_customer.txt
set /p customer_id=<temp_customer.txt

rem Display ticket information
echo.
echo ======================================================
echo Ticket %TICKET_NUMBER% Details:
echo ======================================================
echo Subject: %subject%
echo Customer ID: %customer_id%
echo Body: %body:~0,100%...
echo ======================================================
echo.

rem Create output directory for logs
if not exist "ticket_logs" mkdir ticket_logs

rem Start capturing logs in the background
start cmd /c "docker logs -f support-pipeline-orchestrator > ticket_logs\ticket_%TICKET_NUMBER%_logs.txt"

rem Format the ticket text
set "ticket_text=%subject%. %body%"
set "ticket_text=%ticket_text:"=\"%"

echo Running ticket through support pipeline...
echo Log file: ticket_logs\ticket_%TICKET_NUMBER%_logs.txt
echo.

rem Execute the ticket processing in the container
docker exec -it support-pipeline-orchestrator python -m support_orchestrator.run "%ticket_text%" "%customer_id%"

echo.
echo Processing complete!
echo Logs are being saved to: ticket_logs\ticket_%TICKET_NUMBER%_logs.txt
echo.

rem Optional: Show a preview of the most recent logs
echo Last 20 lines of logs:
echo -------------------------------------------------------
docker logs --tail 20 support-pipeline-orchestrator
echo -------------------------------------------------------
echo.

rem Clean up temp files
del temp_ticket.txt 2>nul
del temp_customer.txt 2>nul

echo To stop log capturing, close the extra command window.
echo To see full logs, check ticket_logs\ticket_%TICKET_NUMBER%_logs.txt
