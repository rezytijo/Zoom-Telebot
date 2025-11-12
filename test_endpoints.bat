@echo off
REM Test script for all Agent API endpoints (Windows)
REM Usage: test_endpoints.bat [server_url] [agent_api_key]

setlocal enabledelayedexpansion

set SERVER_URL=%1
if "%SERVER_URL%"=="" set SERVER_URL=http://localhost:8081

set AGENT_API_KEY=%2
if "%AGENT_API_KEY%"=="" set AGENT_API_KEY=test-api-key-123

set AGENT_URL=%3
if "%AGENT_URL%"=="" set AGENT_URL=http://localhost:8767

echo ========================================
echo 🧪 Testing Agent API Endpoints
echo Server URL: %SERVER_URL%
echo Agent URL: %AGENT_URL%
echo API Key: %AGENT_API_KEY%
echo ========================================
echo.

echo 📋 AGENT API SERVER ENDPOINTS
echo ========================================
echo.

REM Test 1: Agent Registration
echo 1. Testing Agent Registration (POST /agent/register)
set REGISTER_PAYLOAD={\"os_type\":\"Windows 11\",\"hostname\":\"test-pc-01\",\"ip_address\":\"192.168.1.201\",\"version\":\"1.0.0\",\"api_key\":\"%AGENT_API_KEY%\",\"base_url\":\"http://localhost:8767\"}

echo Payload: !REGISTER_PAYLOAD!
curl -s -w "\n%%{http_code}" -X POST "%SERVER_URL%/agent/register" -H "Content-Type: application/json" -d "!REGISTER_PAYLOAD!" > temp_response.txt 2>nul

set /p RESPONSE=<temp_response.txt
for /f "tokens=*" %%i in (temp_response.txt) do set RESPONSE=%%i
for /f "delims=" %%i in (temp_response.txt) do set LAST_LINE=%%i

REM Extract HTTP code (last line)
for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i

REM Get body (all lines except last)
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status %HTTP_CODE% "Agent Registration"
echo Response: !BODY!

REM Extract agent_id from response
echo !BODY! | findstr "agent_id" > temp_agent_id.txt 2>nul
if exist temp_agent_id.txt (
    for /f "tokens=2 delims=:" %%a in (temp_agent_id.txt) do (
        set AGENT_ID=%%a
        set AGENT_ID=!AGENT_ID:,=!
        set AGENT_ID=!AGENT_ID: =!
    )
) else (
    set AGENT_ID=1
)
echo Using Agent ID: !AGENT_ID!
echo.

REM Test 2: Agent Polling
echo 2️⃣  Testing Agent Polling (GET /agent/poll)
curl -s -w "\n%%{http_code}" -X GET "%SERVER_URL%/agent/poll?agent_id=!AGENT_ID!" -H "Authorization: Bearer %AGENT_API_KEY%" > temp_response.txt 2>nul

set /p RESPONSE=<temp_response.txt
for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status !HTTP_CODE! "Agent Polling"
echo Response: !BODY!
echo.

REM Test 3: Agent Reporting
echo 3️⃣  Testing Agent Reporting (POST /agent/report)
set REPORT_PAYLOAD={\"agent_id\":!AGENT_ID!,\"command_id\":1,\"status\":\"completed\",\"output\":\"Command executed successfully via curl test\",\"error\":null}

echo Payload: !REPORT_PAYLOAD!
curl -s -w "\n%%{http_code}" -X POST "%SERVER_URL%/agent/report" -H "Content-Type: application/json" -H "Authorization: Bearer %AGENT_API_KEY%" -d "!REPORT_PAYLOAD!" > temp_response.txt 2>nul

for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status !HTTP_CODE! "Agent Reporting"
echo Response: !BODY!
echo.

REM Test 4: List Agents
echo 4️⃣  Testing List Agents (GET /agent/list)
curl -s -w "\n%%{http_code}" -X GET "%SERVER_URL%/agent/list" > temp_response.txt 2>nul

for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status !HTTP_CODE! "List Agents"
echo Response: !BODY!
echo.

echo 🤖 AGENT SERVER ENDPOINTS (Standalone Agent)
echo ========================================
echo.

REM Test 5: Agent Ping
echo 5️⃣  Testing Agent Ping (GET /ping)
curl -s -w "\n%%{http_code}" -X GET "%AGENT_URL%/ping" > temp_response.txt 2>nul

for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status !HTTP_CODE! "Agent Ping"
echo Response: !BODY!
echo.

REM Test 6: Agent Command - Start Zoom
echo 6️⃣  Testing Agent Command - Start Zoom (POST /command)
set ZOOM_PAYLOAD={\"action\":\"start_zoom\",\"payload\":{\"action\":\"start_zoom\",\"url\":\"https://zoom.us/j/123456789\",\"meeting_id\":\"123456789\",\"topic\":\"Test Meeting via Curl\",\"timeout\":60}}

echo Payload: !ZOOM_PAYLOAD!
curl -s -w "\n%%{http_code}" -X POST "%AGENT_URL%/command" -H "Content-Type: application/json" -H "Authorization: Bearer %AGENT_API_KEY%" -d "!ZOOM_PAYLOAD!" > temp_response.txt 2>nul

for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status !HTTP_CODE! "Start Zoom Command"
echo Response: !BODY!
echo.

REM Test 7: Agent Command - Start Recording
echo 7️⃣  Testing Agent Command - Start Recording (POST /command)
set RECORD_PAYLOAD={\"action\":\"start-record\"}

echo Payload: !RECORD_PAYLOAD!
curl -s -w "\n%%{http_code}" -X POST "%AGENT_URL%/command" -H "Content-Type: application/json" -H "Authorization: Bearer %AGENT_API_KEY%" -d "!RECORD_PAYLOAD!" > temp_response.txt 2>nul

for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status !HTTP_CODE! "Start Recording Command"
echo Response: !BODY!
echo.

REM Test 8: Agent Command - Open URL
echo 8️⃣  Testing Agent Command - Open URL (POST /command)
set URL_PAYLOAD={\"action\":\"open_url\",\"url\":\"https://www.google.com\"}

echo Payload: !URL_PAYLOAD!
curl -s -w "\n%%{http_code}" -X POST "%AGENT_URL%/command" -H "Content-Type: application/json" -H "Authorization: Bearer %AGENT_API_KEY%" -d "!URL_PAYLOAD!" > temp_response.txt 2>nul

for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status !HTTP_CODE! "Open URL Command"
echo Response: !BODY!
echo.

REM Test 9: Agent Command - Custom Hotkey
echo 9️⃣  Testing Agent Command - Custom Hotkey (POST /command)
set HOTKEY_PAYLOAD={\"action\":\"hotkey\",\"keys\":[\"alt\",\"f4\"]}

echo Payload: !HOTKEY_PAYLOAD!
curl -s -w "\n%%{http_code}" -X POST "%AGENT_URL%/command" -H "Content-Type: application/json" -H "Authorization: Bearer %AGENT_API_KEY%" -d "!HOTKEY_PAYLOAD!" > temp_response.txt 2>nul

for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status !HTTP_CODE! "Custom Hotkey Command"
echo Response: !BODY!
echo.

REM Test 10: Invalid API Key Test
echo 🔐 Testing Invalid API Key (POST /command)
set INVALID_PAYLOAD={\"action\":\"start-record\"}

echo Payload: !INVALID_PAYLOAD!
curl -s -w "\n%%{http_code}" -X POST "%AGENT_URL%/command" -H "Content-Type: application/json" -H "Authorization: Bearer invalid-key" -d "!INVALID_PAYLOAD!" > temp_response.txt 2>nul

for /f "delims=" %%i in (temp_response.txt) do set HTTP_CODE=%%i
findstr /v /r "^[0-9][0-9][0-9]$" temp_response.txt > temp_body.txt 2>nul
set /p BODY=<temp_body.txt

call :print_status !HTTP_CODE! "Invalid API Key Test"
echo Response: !BODY!
echo.

REM Cleanup
del temp_response.txt temp_body.txt temp_agent_id.txt 2>nul

echo ========================================
echo 🎉 Testing Complete!
echo ========================================
echo 📝 Notes:
echo    - Make sure both Agent API Server and Agent Server are running
echo    - Replace API keys with actual values for production testing
echo    - Some commands (like start-record) require Zoom to be running
echo.
echo 📊 Summary of tested endpoints:
echo    ✅ Agent API Server: register, poll, report, list
echo    ✅ Agent Server: ping, command (multiple actions)
echo    ✅ Security: API key authentication
echo.
pause
goto :eof

:print_status
set status=%1
set message=%2
if %status% equ 200 (
    echo ✅ %message% (Status: %status%)
) else if %status% equ 201 (
    echo ✅ %message% (Status: %status%)
) else if %status% equ 400 (
    echo ⚠️  %message% (Status: %status%)
) else if %status% equ 401 (
    echo ⚠️  %message% (Status: %status%)
) else if %status% equ 404 (
    echo ⚠️  %message% (Status: %status%)
) else (
    echo ❌ %message% (Status: %status%)
)
goto :eof
