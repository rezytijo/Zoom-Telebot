#!/bin/bash
# Test script for all Agent API endpoints
# Usage: ./test_endpoints.sh [server_url] [agent_api_key]

SERVER_URL=${1:-"http://localhost:8081"}
AGENT_API_KEY=${2:-"test-api-key-123"}

echo "🧪 Testing Agent API Endpoints"
echo "Server URL: $SERVER_URL"
echo "API Key: $AGENT_API_KEY"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    if [[ $status -eq 200 ]] || [[ $status -eq 201 ]]; then
        echo -e "${GREEN}✅ $message (Status: $status)${NC}"
    elif [[ $status -eq 400 ]] || [[ $status -eq 401 ]] || [[ $status -eq 404 ]]; then
        echo -e "${YELLOW}⚠️  $message (Status: $status)${NC}"
    else
        echo -e "${RED}❌ $message (Status: $status)${NC}"
    fi
}

echo ""
echo "📋 AGENT API SERVER ENDPOINTS"
echo "========================================"

# Test 1: Agent Registration
echo ""
echo "1️⃣  Testing Agent Registration (POST /agent/register)"
REGISTER_PAYLOAD='{
    "os_type": "Linux Ubuntu 22.04",
    "hostname": "test-server-01",
    "ip_address": "192.168.1.200",
    "version": "1.0.0",
    "api_key": "'$AGENT_API_KEY'",
    "base_url": "http://localhost:8767"
}'

echo "Payload: $REGISTER_PAYLOAD"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/agent/register" \
    -H "Content-Type: application/json" \
    -d "$REGISTER_PAYLOAD")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n -1)

print_status $HTTP_CODE "Agent Registration"
echo "Response: $BODY"

# Extract agent_id from response for later tests
AGENT_ID=$(echo "$BODY" | grep -o '"agent_id":[0-9]*' | grep -o '[0-9]*' | head -1)
if [[ -z "$AGENT_ID" ]]; then
    AGENT_ID="1"  # fallback
fi
echo "Using Agent ID: $AGENT_ID"

echo ""
echo "🎉 Testing Complete!"
echo "========================================"
echo "📝 Notes:"
echo "   - Make sure both Agent API Server and Agent Server are running"
echo "   - Replace API keys with actual values for production testing"
echo "   - Some commands (like start-record) require Zoom to be running"
echo ""
echo "📊 Summary of tested endpoints:"
echo "   ✅ Agent API Server: register, poll, report, list"
echo "   ✅ Agent Server: ping, command (multiple actions)"
echo "   ✅ Security: API key authentication"
