# API Documentation - DEPRECATED

⚠️ **DEPRECATED**: This API documentation is no longer relevant.

## Important Notice

The Agent API functionality has been **completely replaced** by the C2 Framework.

### What Changed
- **Old System**: REST API with polling agents
- **New System**: Sliver C2 Framework with real-time agent communication

### Migration Guide
1. **Stop using** the old API server (`api_server.py`)
2. **Start using** Sliver C2 for agent management
3. **Refer to** `C2_SETUP_GUIDE.md` for setup instructions
4. **Use** `/zoom_c2` command in Telegram bot for C2 agent control

### Removed Components
- Agent API server (`api/`)
- Polling-based agent communication
- REST endpoints for agent management
- `AGENT_API_PORT`, `AGENT_BASE_URL`, `AGENT_POLL_WAIT_SECONDS` settings

### New Components
- Sliver C2 server integration (`c2/`)
- Real-time agent communication via mTLS
- Implant-based agent deployment
- Enhanced security and reliability

---

*This documentation is kept for historical reference only. All new development should use the C2 Framework.*

## 🚀 Server Configuration

### Default Configuration
- **Host**: 0.0.0.0 (all interfaces)
- **Port**: 8767 (configurable via `AGENT_API_PORT`)
- **Base URL**: `http://localhost:8767`

### Environment Variables
```bash
# API Server
AGENT_API_PORT=8767

# Security (future implementation)
API_USERNAME=admin
API_PASSWORD=secure_password
```

## 📋 API Endpoints

### Health Check
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-12-05T10:30:00Z",
  "version": "1.0.0"
}
```

### Agent Polling
```http
GET /api/agent/poll
```

**Description:** Agent polling endpoint untuk mendapatkan command yang pending.

**Response:**
```json
{
  "commands": [
    {
      "id": 1,
      "command": "start_meeting",
      "meeting_id": "123456789",
      "parameters": {
        "topic": "Security Meeting"
      },
      "timestamp": "2025-12-05T10:30:00Z"
    }
  ]
}
```

### Command Status Update
```http
POST /api/agent/command/{command_id}/status
```

**Parameters:**
- `command_id`: ID command yang akan diupdate

**Request Body:**
```json
{
  "status": "completed",
  "result": {
    "meeting_url": "https://zoom.us/j/123456789",
    "recording_started": true
  },
  "error": null
}
```

**Response:**
```json
{
  "success": true,
  "message": "Command status updated"
}
```

### Meeting Control (Future Implementation)
```http
POST /api/meeting/{meeting_id}/control
```

**Actions:**
- `start`: Start meeting
- `stop`: Stop meeting
- `record_start`: Start recording
- `record_stop`: Stop recording
- `record_pause`: Pause recording
- `record_resume`: Resume recording

**Request Body:**
```json
{
  "action": "start",
  "agent_id": "agent_001"
}
```

### System Status
```http
GET /api/system/status
```

**Response:**
```json
{
  "bot_status": "running",
  "active_meetings": 2,
  "online_agents": 3,
  "database_status": "connected",
  "uptime": "2h 30m",
  "memory_usage": "45.2 MB"
}
```

### Agent Management
```http
GET /api/agents
```

**Response:**
```json
{
  "agents": [
    {
      "id": "agent_001",
      "name": "Meeting Room A",
      "status": "online",
      "last_seen": "2025-12-05T10:29:00Z",
      "capabilities": ["meeting_control", "recording"]
    }
  ]
}
```

```http
POST /api/agents/{agent_id}/register
```

**Request Body:**
```json
{
  "name": "New Agent",
  "capabilities": ["meeting_control", "recording"],
  "metadata": {
    "location": "Room A",
    "hardware": "Windows 11"
  }
}
```

## 🔐 Authentication (Future Implementation)

### API Key Authentication
```bash
# Header
X-API-Key: your_api_key_here
```

### Basic Authentication
```bash
# Header
Authorization: Basic base64(username:password)
```

## 📊 Response Format

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation completed successfully"
}
```

### Error Response
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "field": "meeting_id",
      "reason": "Meeting ID is required"
    }
  }
}
```

## ⚠️ Error Codes

| Code | Description |
|------|-------------|
| `VALIDATION_ERROR` | Invalid request parameters |
| `NOT_FOUND` | Resource not found |
| `UNAUTHORIZED` | Authentication failed |
| `FORBIDDEN` | Insufficient permissions |
| `INTERNAL_ERROR` | Server internal error |
| `AGENT_OFFLINE` | Agent is not responding |
| `MEETING_ERROR` | Zoom meeting operation failed |

## 🔄 Rate Limiting

- **Global Limit**: 100 requests per minute
- **Per Agent**: 10 requests per minute
- **Headers**:
  - `X-RateLimit-Limit`: Maximum requests
  - `X-RateLimit-Remaining`: Remaining requests
  - `X-RateLimit-Reset`: Reset time

## 📝 Examples

### Python Client
```python
import requests
import json

class AgentAPI:
    def __init__(self, base_url="http://localhost:8767"):
        self.base_url = base_url

    def poll_commands(self):
        response = requests.get(f"{self.base_url}/api/agent/poll")
        return response.json()

    def update_command_status(self, command_id, status, result=None):
        data = {
            "status": status,
            "result": result
        }
        response = requests.post(
            f"{self.base_url}/api/agent/command/{command_id}/status",
            json=data
        )
        return response.json()

# Usage
api = AgentAPI()
commands = api.poll_commands()
print(f"Pending commands: {len(commands['commands'])}")
```

### cURL Examples
```bash
# Health check
curl http://localhost:8767/health

# Poll commands
curl http://localhost:8767/api/agent/poll

# Update command status
curl -X POST http://localhost:8767/api/agent/command/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "completed", "result": {"meeting_url": "https://zoom.us/j/123"}}'
```

## 🔍 Monitoring

### Health Checks
```bash
# Simple health check
curl http://localhost:8767/health

# Detailed system status
curl http://localhost:8767/api/system/status
```

### Logs
API server logs tersedia di:
- Docker logs: `docker compose logs api`
- File logs: `logs/api.log`

## 🚀 Development

### Running API Server
```bash
# Standalone
python api/api_server.py

# With full bot
python run.py  # API server akan start otomatis
```

### Testing API
```bash
# Install HTTP client
pip install httpx

# Run tests
python -m pytest tests/test_api.py -v
```

## 📋 TODO / Future Features

- [ ] API Key authentication
- [ ] Rate limiting implementation
- [ ] WebSocket support untuk real-time updates
- [ ] API versioning
- [ ] Comprehensive API documentation (Swagger/OpenAPI)
- [ ] Request/response logging
- [ ] API metrics dan monitoring
- [ ] Batch operations support
- [ ] File upload/download endpoints

## 🔒 Security Considerations

1. **Network Security**: Jalankan API server di internal network only
2. **Authentication**: Implement proper authentication sebelum production
3. **Input Validation**: Validate semua input parameters
4. **Rate Limiting**: Implement rate limiting untuk mencegah abuse
5. **HTTPS**: Gunakan HTTPS di production environment
6. **Logging**: Log semua API requests untuk audit trail

## 📞 Support

Untuk pertanyaan API atau dukungan development, silakan buat issue di repository dengan label `api`.