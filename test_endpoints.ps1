# Agent API Testing Script (PowerShell)
# Usage: .\test_endpoints.ps1 [-ServerUrl "http://localhost:8081"] [-AgentUrl "http://localhost:8767"] [-ApiKey "your-key"]

param(
    [string]$ServerUrl = "http://localhost:8081",
    [string]$AgentUrl = "http://localhost:8767",
    [string]$ApiKey = "test-api-key-123"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Testing Agent API Endpoints" -ForegroundColor Yellow
Write-Host "Server URL: $ServerUrl" -ForegroundColor White
Write-Host "Agent URL: $AgentUrl" -ForegroundColor White
Write-Host "API Key: $ApiKey" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

function Write-Status {
    param([int]$StatusCode, [string]$Message)
    if ($StatusCode -eq 200 -or $StatusCode -eq 201) {
        Write-Host "SUCCESS: $Message (Status: $StatusCode)" -ForegroundColor Green
    } elseif ($StatusCode -eq 400 -or $StatusCode -eq 401 -or $StatusCode -eq 404) {
        Write-Host "WARNING: $Message (Status: $StatusCode)" -ForegroundColor Yellow
    } else {
        Write-Host "ERROR: $Message (Status: $StatusCode)" -ForegroundColor Red
    }
}

Write-Host "AGENT API SERVER ENDPOINTS" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

# Test 1: Agent Registration
Write-Host "1. Testing Agent Registration (POST /agent/register)" -ForegroundColor White
$registerPayload = @{
    os_type = "Windows 11"
    hostname = "test-pc-ps"
    ip_address = "192.168.1.202"
    version = "1.0.0"
    api_key = $ApiKey
    base_url = "http://localhost:8767"
} | ConvertTo-Json

Write-Host "Payload: $registerPayload" -ForegroundColor Gray
try {
    $response = Invoke-RestMethod -Uri "$ServerUrl/agent/register" -Method Post -Body $registerPayload -ContentType "application/json"
    Write-Status 200 "Agent Registration"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green

    # Extract agent_id for later tests
    $agentId = $response.agent_id
    if (-not $agentId) { $agentId = 1 }
    Write-Host "Using Agent ID: $agentId" -ForegroundColor Cyan
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "Agent Registration"
    } else {
        Write-Host "ERROR: Agent Registration (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    $agentId = 1
}
Write-Host ""

# Test 2: Agent Polling
Write-Host "2. Testing Agent Polling (GET /agent/poll)" -ForegroundColor White
try {
    $headers = @{ "Authorization" = "Bearer $ApiKey" }
    $response = Invoke-RestMethod -Uri "$ServerUrl/agent/poll?agent_id=$agentId" -Method Get -Headers $headers
    Write-Status 200 "Agent Polling"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "Agent Polling"
    } else {
        Write-Host "ERROR: Agent Polling (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 3: Agent Reporting
Write-Host "3. Testing Agent Reporting (POST /agent/report)" -ForegroundColor White
$reportPayload = @{
    agent_id = $agentId
    command_id = 1
    status = "completed"
    output = "Command executed successfully via PowerShell test"
    error = $null
} | ConvertTo-Json

Write-Host "Payload: $reportPayload" -ForegroundColor Gray
try {
    $headers = @{ "Authorization" = "Bearer $ApiKey" }
    $response = Invoke-RestMethod -Uri "$ServerUrl/agent/report" -Method Post -Body $reportPayload -ContentType "application/json" -Headers $headers
    Write-Status 200 "Agent Reporting"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "Agent Reporting"
    } else {
        Write-Host "ERROR: Agent Reporting (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 4: List Agents
Write-Host "4. Testing List Agents (GET /agent/list)" -ForegroundColor White
try {
    $response = Invoke-RestMethod -Uri "$ServerUrl/agent/list" -Method Get
    Write-Status 200 "List Agents"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "List Agents"
    } else {
        Write-Host "ERROR: List Agents (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

Write-Host "AGENT SERVER ENDPOINTS (Standalone Agent)" -ForegroundColor Blue
Write-Host "========================================" -ForegroundColor Blue
Write-Host ""

# Test 5: Agent Ping
Write-Host "5. Testing Agent Ping (GET /ping)" -ForegroundColor White
try {
    $response = Invoke-RestMethod -Uri "$AgentUrl/ping" -Method Get
    Write-Status 200 "Agent Ping"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "Agent Ping"
    } else {
        Write-Host "ERROR: Agent Ping (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 6: Agent Command - Start Zoom
Write-Host "6. Testing Agent Command - Start Zoom (POST /command)" -ForegroundColor White
$zoomPayload = @{
    action = "start_zoom"
    payload = @{
        action = "start_zoom"
        url = "https://zoom.us/j/123456789"
        meeting_id = "123456789"
        topic = "Test Meeting via PowerShell"
        timeout = 60
    }
} | ConvertTo-Json -Depth 3

Write-Host "Payload: $zoomPayload" -ForegroundColor Gray
try {
    $headers = @{ "Authorization" = "Bearer $ApiKey" }
    $response = Invoke-RestMethod -Uri "$AgentUrl/command" -Method Post -Body $zoomPayload -ContentType "application/json" -Headers $headers
    Write-Status 200 "Start Zoom Command"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "Start Zoom Command"
    } else {
        Write-Host "ERROR: Start Zoom Command (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 7: Agent Command - Start Recording
Write-Host "7. Testing Agent Command - Start Recording (POST /command)" -ForegroundColor White
$recordPayload = @{ action = "start-record" } | ConvertTo-Json

Write-Host "Payload: $recordPayload" -ForegroundColor Gray
try {
    $headers = @{ "Authorization" = "Bearer $ApiKey" }
    $response = Invoke-RestMethod -Uri "$AgentUrl/command" -Method Post -Body $recordPayload -ContentType "application/json" -Headers $headers
    Write-Status 200 "Start Recording Command"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "Start Recording Command"
    } else {
        Write-Host "ERROR: Start Recording Command (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 8: Agent Command - Open URL
Write-Host "8. Testing Agent Command - Open URL (POST /command)" -ForegroundColor White
$urlPayload = @{
    action = "open_url"
    url = "https://www.google.com"
} | ConvertTo-Json

Write-Host "Payload: $urlPayload" -ForegroundColor Gray
try {
    $headers = @{ "Authorization" = "Bearer $ApiKey" }
    $response = Invoke-RestMethod -Uri "$AgentUrl/command" -Method Post -Body $urlPayload -ContentType "application/json" -Headers $headers
    Write-Status 200 "Open URL Command"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "Open URL Command"
    } else {
        Write-Host "ERROR: Open URL Command (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 9: Agent Command - Custom Hotkey
Write-Host "9. Testing Agent Command - Custom Hotkey (POST /command)" -ForegroundColor White
$hotkeyPayload = @{
    action = "hotkey"
    keys = @("alt", "f4")
} | ConvertTo-Json

Write-Host "Payload: $hotkeyPayload" -ForegroundColor Gray
try {
    $headers = @{ "Authorization" = "Bearer $ApiKey" }
    $response = Invoke-RestMethod -Uri "$AgentUrl/command" -Method Post -Body $hotkeyPayload -ContentType "application/json" -Headers $headers
    Write-Status 200 "Custom Hotkey Command"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "Custom Hotkey Command"
    } else {
        Write-Host "ERROR: Custom Hotkey Command (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 10: Invalid API Key Test
Write-Host "10. Testing Invalid API Key (POST /command)" -ForegroundColor White
$invalidPayload = @{ action = "start-record" } | ConvertTo-Json

Write-Host "Payload: $invalidPayload" -ForegroundColor Gray
try {
    $headers = @{ "Authorization" = "Bearer invalid-key" }
    $response = Invoke-RestMethod -Uri "$AgentUrl/command" -Method Post -Body $invalidPayload -ContentType "application/json" -Headers $headers
    Write-Status 200 "Invalid API Key Test"
    Write-Host "Response: $($response | ConvertTo-Json)" -ForegroundColor Green
} catch {
    if ($_.Exception.Response) {
        Write-Status $_.Exception.Response.StatusCode.value__ "Invalid API Key Test"
    } else {
        Write-Host "ERROR: Invalid API Key Test (Connection failed)" -ForegroundColor Red
    }
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Testing Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Notes:" -ForegroundColor Yellow
Write-Host "   - Make sure both Agent API Server and Agent Server are running" -ForegroundColor White
Write-Host "   - Replace API keys with actual values for production testing" -ForegroundColor White
Write-Host "   - Some commands (like start-record) require Zoom to be running" -ForegroundColor White
Write-Host ""
Write-Host "Summary of tested endpoints:" -ForegroundColor Yellow
Write-Host "   - Agent API Server: register, poll, report, list" -ForegroundColor Green
Write-Host "   - Agent Server: ping, command (multiple actions)" -ForegroundColor Green
Write-Host "   - Security: API key authentication" -ForegroundColor Green
Write-Host ""

Read-Host "Press Enter to exit"