# PowerShell script to generate a dashboard-compatible pipeline event simulation
# This script sends events directly to Redis that match what the dashboard expects

# Format the timestamp in the expected format
$timestamp = Get-Date -Format "MMM d, yyyy - HH:mm:ss"
$projectId = "secops-$(Get-Date -Format 'yyyyMMddHHmmss')-$(Get-Random -Minimum 10000 -Maximum 99999)"

# First event: Pipeline step 1 (Start)
Write-Host "Publishing pipeline step 1 (Start)"
$step1 = @{
    event_type = "pipeline_execution"
    status = "STARTING"
    project_id = $projectId
    step = "start"
    step_number = 1
    message = "Pipeline execution starting"
    timestamp = (Get-Date).ToString("o")
} | ConvertTo-Json -Compress
docker exec secops-redis redis-cli PUBLISH secops_events $step1

# Wait 1 second
Start-Sleep -Seconds 1

# Second event: Pipeline step 2 (Ingest Alert)
Write-Host "Publishing pipeline step 2 (Ingest Alert)"
$step2 = @{
    event_type = "pipeline_execution"
    status = "IN_PROGRESS"
    project_id = $projectId
    step = "ingest_alert"
    step_number = 2
    message = "Ingested alert from Firewall"
    alert = @{
        name = "Suspicious Authentication Activity"
        source = "Firewall"
        time = (Get-Date).ToString("o")
        user = "admin@example.com"
        source_ip = "198.51.100.42"
        description = "Multiple failed login attempts followed by successful login from unusual geographical location"
    }
    timestamp = (Get-Date).ToString("o")
} | ConvertTo-Json -Compress
docker exec secops-redis redis-cli PUBLISH secops_events $step2

# Wait 1 second
Start-Sleep -Seconds 1

# Third event: Pipeline step 3 (Enrichment)
Write-Host "Publishing pipeline step 3 (Enrichment)"
$step3 = @{
    event_type = "pipeline_execution"
    status = "IN_PROGRESS"
    project_id = $projectId
    step = "enrichment"
    step_number = 3
    message = "Enriched alert data with threat intelligence"
    enrichment_results = @(
        @{
            indicator = "198.51.100.42"
            type = "IP Address"
            verdict = "Suspicious"
        },
        @{
            indicator = "admin@example.com"
            type = "Username"
            verdict = "Legitimate"
        }
    )
    timestamp = (Get-Date).ToString("o")
} | ConvertTo-Json -Compress
docker exec secops-redis redis-cli PUBLISH secops_events $step3

# Wait 1 second
Start-Sleep -Seconds 1

# Fourth event: Pipeline step 4 (Investigation)
Write-Host "Publishing pipeline step 4 (Investigation)"
$step4 = @{
    event_type = "pipeline_execution"
    status = "IN_PROGRESS"
    project_id = $projectId
    step = "investigation"
    step_number = 4
    message = "Completed investigation"
    timestamp = (Get-Date).ToString("o")
} | ConvertTo-Json -Compress
docker exec secops-redis redis-cli PUBLISH secops_events $step4

# Wait 1 second
Start-Sleep -Seconds 1

# Fifth event: Pipeline step 5 (Determine Response)
Write-Host "Publishing pipeline step 5 (Determine Response)"
$step5 = @{
    event_type = "pipeline_execution"
    status = "IN_PROGRESS"
    project_id = $projectId
    step = "determine_response"
    step_number = 5
    message = "LLM has determined appropriate response"
    llm_decision = @{
        severity = "Medium"
        confidence_percentage = 87
        recommended_action = "CREATE_TICKET"
        reasoning = "The login activity shows a suspicious pattern from an unusual IP address. While the user account is legitimate, the behavior is anomalous enough to warrant investigation. Since there's no evidence of data exfiltration or system compromise, a medium-severity ticket is appropriate rather than immediate blocking or isolation."
    }
    timestamp = (Get-Date).ToString("o")
} | ConvertTo-Json -Compress
docker exec secops-redis redis-cli PUBLISH secops_events $step5

# Wait 1 second
Start-Sleep -Seconds 1

# Sixth event: Pipeline step 6 (Execute Response)
Write-Host "Publishing pipeline step 6 (Execute Response)"
$ticketId = "SEC-$(Get-Date -Format 'yyyy')-$(Get-Random -Minimum 1000 -Maximum 9999)"

$step6 = @{
    event_type = "pipeline_execution"
    status = "IN_PROGRESS"
    project_id = $projectId
    step = "execute_response"
    step_number = 6
    message = "Executing response action: Create Ticket"
    response_action = @{
        action_type = "CREATE_TICKET"
        status = "Success"
        details = @{
            ticket_id = $ticketId
        }
        parameters = @{
            summary = "Suspicious authentication activity for admin@example.com"
            priority = "Medium"
            affected_systems = @("firewall.example.com", "auth.example.com")
        }
    }
    timestamp = (Get-Date).ToString("o")
} | ConvertTo-Json -Compress
docker exec secops-redis redis-cli PUBLISH secops_events $step6

# Wait 1 second
Start-Sleep -Seconds 1

# Final event: Pipeline step 7 (Complete)
Write-Host "Publishing pipeline step 7 (Complete)"
$step7 = @{
    event_type = "pipeline_execution"
    status = "COMPLETED"
    project_id = $projectId
    step = "complete"
    step_number = 7
    message = "Pipeline execution completed successfully"
    duration_seconds = 8.42
    timestamp = (Get-Date).ToString("o")
} | ConvertTo-Json -Compress
docker exec secops-redis redis-cli PUBLISH secops_events $step7

# Success message
Write-Host ""
Write-Host "Pipeline simulation complete!"
Write-Host "Project ID: $projectId"
Write-Host "Ticket ID: $ticketId"
Write-Host ""
Write-Host "The dashboard should now show the complete pipeline execution."
