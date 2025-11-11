<#
Package the agent into a single zip artifact for distribution.

Usage:
  .\package_agent.ps1 -OutPath C:\temp\zoom-agent-1.0.zip

What it does:
 - creates a temporary staging folder
 - copies the `agent/` directory into the stage
 - writes a minimal `agent_requirements.txt` (aiohttp + pyautogui)
 - writes small run scripts (Windows + bash) inside the package
 - compresses the stage into the output zip
#>

param(
    [string]$OutPath = "zoom-agent.zip",
    [string]$SourceDir = (Join-Path $PSScriptRoot "."),
    [switch]$IncludeReadme = $true
)

if (-not (Test-Path $SourceDir)) {
    Write-Error "Source directory not found: $SourceDir"
    exit 1
}

$tmp = Join-Path $env:TEMP ("zoom_agent_pkg_" + ([guid]::NewGuid().ToString()))
New-Item -ItemType Directory -Path $tmp | Out-Null

try {
    # Copy agent folder
    $agentSrc = Join-Path $PSScriptRoot '..'\'agent' | Resolve-Path -ErrorAction SilentlyContinue
    if (-not $agentSrc) {
        # fallback: use current agent folder if already in repo
        $agentSrc = Join-Path $PSScriptRoot 'agent'
    }
    Copy-Item -Path $agentSrc -Destination $tmp -Recurse -Force

    # Create minimal requirements file
    $reqPath = Join-Path $tmp 'agent\agent_requirements.txt'
    @('
aiohttp
pyautogui
') | Out-File -FilePath $reqPath -Encoding UTF8

    # Create helper run scripts in the package
    $winRun = @"
@echo off
REM Creates venv if missing and runs agent (Windows)
if not exist venv (python -m venv venv)
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r agent\agent_requirements.txt
python agent\agent_server.py %*
"@
    $winRunPath = Join-Path $tmp 'run_agent.bat'
    $winRun | Out-File -FilePath $winRunPath -Encoding ASCII

    $shRun = @"
#!/usr/bin/env bash
# Creates venv if missing and runs agent (Unix)
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r agent/agent_requirements.txt
python3 agent/agent_server.py "$@"
"@
    $shRunPath = Join-Path $tmp 'run_agent.sh'
    $shRun | Out-File -FilePath $shRunPath -Encoding UTF8
    icacls $shRunPath /grant Everyone:(RX) | Out-Null

    if ($IncludeReadme) {
        $readmeSrc = Join-Path $PSScriptRoot '..'\'agent'\'README_AGENT.md'
        if (Test-Path $readmeSrc) { Copy-Item -Path $readmeSrc -Destination (Join-Path $tmp 'agent') -Force -Recurse }
    }

    # Create zip
    if (Test-Path $OutPath) { Remove-Item $OutPath -Force }
    Compress-Archive -Path (Join-Path $tmp '*') -DestinationPath $OutPath -Force
    Write-Host "Created package: $OutPath"
}
finally {
    # cleanup
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
