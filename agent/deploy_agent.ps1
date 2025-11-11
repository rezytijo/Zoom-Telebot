<#
Simple Windows deployment helper for agent. Usage (PowerShell):
  .\deploy_agent.ps1 -ApiKey 'KEY' -ServerUrl 'https://your-bot.example.com'

This script will:
 - create a venv (if missing) at $VenvPath
 - install required packages
 - print the recommended run command and Scheduled Task example
#>

param(
    [string]$ApiKey,
    [string]$ServerUrl = '',
    [string]$VenvPath = "C:\zoom_agent_venv",
    [string]$AgentDir = "$PWD\agent",
    [switch]$CreateTask
)

if (-not (Test-Path $AgentDir)) {
    Write-Error "Agent directory not found: $AgentDir"
    exit 1
}

if (-not (Test-Path $VenvPath)) {
    python -m venv $VenvPath
}

& "$VenvPath\Scripts\Activate.ps1"
pip install --upgrade pip
pip install aiohttp pyautogui

$runCmd = "python " + $AgentDir + "\agent_server.py --api-key '" + $ApiKey + "'"
if ($ServerUrl) { $runCmd += " --server-url '" + $ServerUrl + "'" }

Write-Host "Run command:" -ForegroundColor Green
Write-Host $runCmd

if ($CreateTask) {
    # Create scheduled task that runs at user logon. Use the virtualenv python executable if available.
    $pythonExe = Join-Path $VenvPath 'Scripts\python.exe'
    $arg = $runCmd
    $action = New-ScheduledTaskAction -Execute $pythonExe -Argument $arg
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask -TaskName "ZoomAgent" -Action $action -Trigger $trigger -Description "Zoom agent polling to central server" -User $env:USERNAME -RunLevel Highest
    Write-Host "Scheduled Task 'ZoomAgent' created (run at logon)." -ForegroundColor Green
}
