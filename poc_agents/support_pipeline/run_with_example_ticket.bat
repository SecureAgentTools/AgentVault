@echo off
echo Running Support Pipeline with Example Ticket Data

rem Parse arguments
set TICKET_NUMBER=%1
if "%TICKET_NUMBER%"=="" set TICKET_NUMBER=2

rem Read the example tickets file and extract the specified ticket
powershell -Command "$content = Get-Content -Raw -Path '.\example_tickets.txt'; $pattern = 'Ticket %TICKET_NUMBER% \([^)]+\):\r?\nSubject: ([^\r\n]+)([\s\S]+?)(?=\r?\n-{10,}|\z)'; $matches = [regex]::Match($content, $pattern); if ($matches.Success) { $subject = $matches.Groups[1].Value.Trim(); $body = $matches.Groups[2].Value.Trim(); $extractedData = @{Subject=$subject; Body=$body}; $extractedData | ConvertTo-Json -Compress } else { Write-Output '{\"error\": \"Ticket not found\"}' }" > temp_ticket.json

rem Extract the ticket data
for /f "delims=" %%i in ('type temp_ticket.json') do set TICKET_JSON=%%i
del temp_ticket.json

rem Extract customer from the ticket
powershell -Command "$ticketJson = '%TICKET_JSON%' | ConvertFrom-Json; $ticketBody = $ticketJson.Body; $pattern = '([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+|[a-zA-Z0-9_-]+(?:_user|_id)\w*)'; $matches = [regex]::Matches($ticketBody, $pattern); if ($matches.Count -gt 0) { Write-Output $matches[0].Value } else { Write-Output 'default-customer-id' }" > temp_customer.txt
set /p CUSTOMER_ID=<temp_customer.txt
del temp_customer.txt

rem Extract ticket subject and body
powershell -Command "$ticketJson = '%TICKET_JSON%' | ConvertFrom-Json; Write-Output $ticketJson.Subject" > temp_subject.txt
set /p SUBJECT=<temp_subject.txt
del temp_subject.txt

powershell -Command "$ticketJson = '%TICKET_JSON%' | ConvertFrom-Json; Write-Output $ticketJson.Body" > temp_body.txt
set /p BODY=<temp_body.txt
del temp_body.txt

echo Selected Ticket %TICKET_NUMBER%:
echo.
echo Subject: %SUBJECT%
echo Body: %BODY%
echo Customer ID: %CUSTOMER_ID%
echo.

rem Build the ticket text
set TICKET_TEXT=%SUBJECT%. %BODY%

rem Ensure the support pipeline is running
echo Checking if support pipeline is running...
docker ps | find "support-pipeline-orchestrator" > nul
if errorlevel 1 (
    echo Support pipeline is not running. Starting it...
    call .\start_complete_support_pipeline.bat
)

rem Connect to the orchestrator container and run with the example ticket
echo.
echo Running support pipeline with the example ticket...
echo.
docker exec -it support-pipeline-orchestrator python -m support_orchestrator.run "%TICKET_TEXT%" "%CUSTOMER_ID%"

echo.
echo Pipeline execution completed.
