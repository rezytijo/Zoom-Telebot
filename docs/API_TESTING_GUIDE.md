# Agent API Testing Guide - DEPRECATED

⚠️ **DEPRECATED**: This testing guide is no longer relevant.

## Important Notice

The Agent API functionality has been **completely replaced** by the C2 Framework.

### What Changed
- **Old System**: REST API with polling agents and curl testing
- **New System**: Sliver C2 Framework with real-time agent communication

### Migration Guide
1. **Stop using** the old API testing methods
2. **Start using** Sliver console for agent interaction
3. **Refer to** `C2_SETUP_GUIDE.md` for setup and testing instructions
4. **Use** `/zoom_c2` command in Telegram bot for C2 agent control

### Removed Components
- Agent API server testing
- Polling-based agent communication testing
- REST endpoint testing with curl
- Agent server testing scripts

### New Components
- Sliver C2 console for direct agent interaction
- Implant deployment and management
- Real-time command execution testing
- Enhanced security testing capabilities

---

*This guide is kept for historical reference only. All new testing should use the C2 Framework console and commands.*
Use the individual curl commands below for specific endpoint testing.

---

## 📡 Agent API Server Endpoints

### 1. Agent Registration
**Endpoint:** `POST /agent/register`
**Purpose:** Register a new agent with system information

```bash
curl -X POST "http://localhost:8081/agent/register" \
  -H "Content-Type: application/json" \
  -d '{
    "os_type": "Windows 11",
    "hostname": "COMPUTER-NAME",
    "ip_address": "192.168.1.100",
    "version": "1.0.0",
    "api_key": "your-agent-api-key",
    "base_url": "http://localhost:8767"
  }'
```

**Note:** The `name` field is now optional and will be assigned by admin when adding the agent.

**Expected Response:**
```json
{
  "ok": true,
  "agent_id": 7,
  "api_key": "your-agent-api-key",
  "message": "Agent registered successfully with ID 7"
}
```

### 2. Agent Polling
**Endpoint:** `GET /agent/poll`
**Purpose:** Poll for pending commands

```bash
curl -X GET "http://localhost:8081/agent/poll?agent_id=7" \
  -H "Authorization: Bearer your-agent-api-key"
```

**Expected Response (no commands):**
```json
{
  "ok": true,
  "commands": []
}
```

**Expected Response (with commands):**
```json
{
  "ok": true,
  "commands": [
    {
      "id": 1,
      "action": "start_zoom",
      "payload": "{\"url\": \"https://zoom.us/j/123456789\"}",
      "created_at": "2025-11-13 10:30:00"
    }
  ]
}
```

### 3. Agent Reporting
**Endpoint:** `POST /agent/report`
**Purpose:** Report command execution results

```bash
curl -X POST "http://localhost:8081/agent/report" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-api-key" \
  -d '{
    "agent_id": 7,
    "command_id": 1,
    "status": "completed",
    "output": "Command executed successfully",
    "error": null
  }'
```

**Expected Response:**
```json
{
  "ok": true
}
```

### 4. List Agents
**Endpoint:** `GET /agent/list`
**Purpose:** Get list of all registered agents

```bash
curl -X GET "http://localhost:8081/agent/list"
```

**Expected Response:**
```json
{
  "ok": true,
  "agents": [
    {
      "id": 7,
      "name": "My-Agent",
      "os_type": "Windows 11",
      "hostname": "COMPUTER-NAME",
      "ip_address": "192.168.1.100",
      "version": "1.0.0",
      "base_url": "http://localhost:8767",
      "last_seen": "2025-11-13 10:35:00",
      "status": "online"
    }
  ],
  "total": 1
}
```

---

## 🤖 Agent Server Endpoints

### 5. Agent Ping
**Endpoint:** `GET /ping`
**Purpose:** Get agent status and system information

```bash
curl -X GET "http://localhost:8767/ping"
```

**Expected Response:**
```json
{
  "ok": true,
  "os": "Windows",
  "os_type": "Windows 11 Pro (Version 10.0.22621)",
  "hostname": "COMPUTER-NAME",
  "ip_address": "192.168.1.100",
  "version": "1.0.0"
}
```

### 6. Execute Command - Start Zoom
**Endpoint:** `POST /command`
**Purpose:** Start a Zoom meeting

```bash
curl -X POST "http://localhost:8767/command" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-api-key" \
  -d '{
    "action": "start_zoom",
    "payload": {
      "action": "start_zoom",
      "url": "https://zoom.us/j/123456789",
      "meeting_id": "123456789",
      "topic": "Test Meeting",
      "timeout": 60
    }
  }'
```

**Expected Response:**
```json
{
  "ok": true,
  "meeting_id": "123456789",
  "topic": "Test Meeting",
  "action": "start_zoom",
  "executed_at": "now"
}
```

### 7. Execute Command - Recording Control
**Endpoint:** `POST /command`
**Purpose:** Control Zoom recording

```bash
# Start Recording
curl -X POST "http://localhost:8767/command" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-api-key" \
  -d '{"action": "start-record"}'

# Stop Recording
curl -X POST "http://localhost:8767/command" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-api-key" \
  -d '{"action": "stop-record"}'

# Pause Recording
curl -X POST "http://localhost:8767/command" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-api-key" \
  -d '{"action": "pause-record"}'

# Resume Recording
curl -X POST "http://localhost:8767/command" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-api-key" \
  -d '{"action": "resume-record"}'
```

**Expected Response:**
```json
{
  "ok": true,
  "action": "start-record"
}
```

### 8. Execute Command - Open URL
**Endpoint:** `POST /command`
**Purpose:** Open URL in default browser

```bash
curl -X POST "http://localhost:8767/command" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-api-key" \
  -d '{
    "action": "open_url",
    "url": "https://www.google.com"
  }'
```

**Expected Response:**
```json
{
  "ok": true,
  "action": "open_url"
}
```

### 9. Execute Command - Custom Hotkey
**Endpoint:** `POST /command`
**Purpose:** Send custom keyboard shortcuts

```bash
curl -X POST "http://localhost:8767/command" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-agent-api-key" \
  -d '{
    "action": "hotkey",
    "keys": ["alt", "f4"]
  }'
```

**Expected Response:**
```json
{
  "ok": true,
  "action": "hotkey"
}
```

---

## 🔐 Security Testing

### Invalid API Key Test
```bash
curl -X POST "http://localhost:8767/command" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid-key" \
  -d '{"action": "start-record"}'
```

**Expected Response:**
```json
{
  "error": "invalid api key"
}
```

---

## 🛠️ Setup Instructions

### 1. Start Agent API Server
```bash
python api/agent_api.py --port 8081 --verbose
```

### 2. Start Agent Server (Standalone Mode)
```bash
python agent/agent_server.py --port 8767 --api-key your-api-key
```

### 3. Start Agent Server (Polling Mode)
```bash
python agent/agent_server.py --server-url http://localhost:8081 --api-key your-api-key
```

### 4. Run Tests
```bash
# Linux/Mac
./test_endpoints.sh

# Windows
test_endpoints.bat
```

---

## 📊 Supported Actions Summary

| Action | Description | Hotkey |
|--------|-------------|---------|
| `open_url` | Open URL in browser | N/A |
| `start_zoom` | Start Zoom meeting | N/A |
| `start-record` | Start recording | Alt+R |
| `stop-record` | Stop recording | Alt+R |
| `pause-record` | Pause recording | Alt+P |
| `resume-record` | Resume recording | Alt+P |
| `hotkey` | Custom hotkey combination | Custom |

---

## ⚠️ Notes

- **API Keys:** Always use strong, unique API keys for production
- **Firewall:** Ensure proper firewall configuration for agent communication
- **Zoom Dependency:** Recording commands require Zoom application to be running
- **pyautogui:** Required for hotkey functionality on Windows/Linux
- **Network:** Ensure agents can reach the API server for polling mode

---

## 🔍 Troubleshooting

### Common Issues:

1. **Connection Refused**
   - Check if servers are running on correct ports
   - Verify firewall settings

2. **Invalid API Key**
   - Ensure API key matches between agent and server
   - Check Authorization header format

3. **Command Not Executed**
   - Verify pyautogui is installed
   - Check if Zoom is running for recording commands
   - Ensure agent has proper permissions

4. **Database Errors**
   - Check database file permissions
   - Ensure database schema is up to date