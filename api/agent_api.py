"""Agent API for server: endpoints agents poll to fetch commands and report results.

This module exposes an aiohttp app to be started in the bot process.

API Endpoints:
- POST /agent/register: Register a new agent with system information
- GET  /agent/poll: Poll for pending commands (requires agent_id and api_key)
- POST /agent/report: Report command execution results
- GET  /agent/list: Get list of all registered agents (for admin/debugging)

Agent Registration Payload (name is optional - will be set by admin):
{
    "name": "agent-name (optional)",
    "os_type": "Windows 11",
    "hostname": "COMPUTER-NAME",
    "ip_address": "192.168.1.100",
    "version": "1.0.0",
    "api_key": "agent-api-key (required)",
    "base_url": "http://localhost:8767"
}
"""
from aiohttp import web
import asyncio
import json
import logging
import os
import sys

# Add parent directory to path so we can import from the main project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import add_agent, list_agents, get_agent, get_pending_commands, update_command_status, update_agent_last_seen, init_db
from config import settings

logger = logging.getLogger(__name__)


async def initialize_database():
    """Initialize database if running standalone."""
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

logger = logging.getLogger(__name__)


async def handle_register(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid json'}, status=400)

    # Name is no longer required - will be set by admin when adding agent
    name = body.get('name', '')  # Default to empty string if not provided
    os_type = body.get('os_type')
    hostname = body.get('hostname')
    ip_address = body.get('ip_address')
    version = body.get('version')
    api_key = body.get('api_key')
    base_url = body.get('base_url', '')

    # Validate required fields (excluding name)
    if not api_key:
        return web.json_response({'error': 'missing api_key'}, status=400)

    try:
        # Register agent with system information (name can be empty or set later by admin)
        agent_id = await add_agent(
            name=name,
            base_url=base_url,
            api_key=api_key,
            os_type=os_type,
            hostname=hostname,
            ip_address=ip_address,
            version=version
        )
        logger.info("Agent registered: ID=%s, OS=%s, Host=%s, IP=%s (Name: '%s')",
                   agent_id, os_type, hostname, ip_address, name or 'not set')
        return web.json_response({
            'ok': True,
            'agent_id': agent_id,
            'api_key': api_key,
            'message': f'Agent registered successfully with ID {agent_id}'
        })
    except Exception as e:
        logger.exception('Agent registration failed')
        return web.json_response({'error': f'registration failed: {str(e)}'}, status=500)


async def handle_poll(request: web.Request):
    # expects agent_id and api_key in query or headers
    aid = request.query.get('agent_id')
    api_key = request.headers.get('Authorization', '').split(' ', 1)[-1] if request.headers.get('Authorization') else None
    if not aid:
        return web.json_response({'error': 'missing agent_id'}, status=400)
    try:
        agent = await get_agent(int(aid))
    except Exception:
        return web.json_response({'error': 'invalid agent_id'}, status=400)
    if not agent:
        return web.json_response({'error': 'agent not found'}, status=404)
    # validate api_key if agent has one
    if agent.get('api_key') and api_key != agent.get('api_key'):
        return web.json_response({'error': 'invalid api key'}, status=403)

    # update last seen
    try:
        await update_agent_last_seen(agent['id'])
    except Exception:
        logger.exception('update last seen failed')

    # fetch pending commands
    try:
        cmds = await get_pending_commands(agent['id'])
        return web.json_response({'ok': True, 'commands': cmds})
    except Exception as e:
        logger.exception('get_pending_commands failed')
        return web.json_response({'error': str(e)}, status=500)


async def handle_report(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid json'}, status=400)
    agent_id = body.get('agent_id')
    api_key = request.headers.get('Authorization', '').split(' ', 1)[-1] if request.headers.get('Authorization') else None
    if not agent_id:
        return web.json_response({'error': 'missing agent_id'}, status=400)
    agent = await get_agent(int(agent_id))
    if not agent:
        return web.json_response({'error': 'agent not found'}, status=404)
    if agent.get('api_key') and api_key != agent.get('api_key'):
        return web.json_response({'error': 'invalid api key'}, status=403)

    command_id = body.get('command_id')
    status = body.get('status')
    result = body.get('result')
    if not command_id or not status:
        return web.json_response({'error': 'missing command_id or status'}, status=400)
    try:
        await update_command_status(int(command_id), status, json.dumps(result) if result is not None else None)
        return web.json_response({'ok': True})
    except Exception as e:
        logger.exception('report failed')
        return web.json_response({'error': str(e)}, status=500)


async def handle_list_agents(request: web.Request):
    """Get list of all registered agents (for monitoring/debugging)."""
    try:
        agents = await list_agents()
        # Convert agents to dict format for JSON response
        agent_list = []
        for agent in agents:
            agent_list.append({
                'id': agent['id'],
                'name': agent['name'],
                'os_type': agent['os_type'],
                'hostname': agent['hostname'],
                'ip_address': agent['ip_address'],
                'version': agent['version'],
                'base_url': agent['base_url'],
                'last_seen': agent['last_seen'],
                'status': 'online' if agent['last_seen'] else 'offline'
            })
        return web.json_response({
            'ok': True,
            'agents': agent_list,
            'total': len(agent_list)
        })
    except Exception as e:
        logger.exception('Failed to list agents')
        return web.json_response({'error': f'failed to list agents: {str(e)}'}, status=500)


def create_app():
    app = web.Application()
    app.add_routes([
        web.post('/agent/register', handle_register),
        web.get('/agent/poll', handle_poll),
        web.post('/agent/report', handle_report),
        web.get('/agent/list', handle_list_agents),
    ])
    return app


async def run_server(host='0.0.0.0', port=8080):
    """Run the agent API server standalone."""
    # Initialize database first
    await initialize_database()
    
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"======== Agent API Server running on http://{host}:{port} ========")
    print("Endpoints:")
    print("  POST /agent/register - Register new agent")
    print("  GET  /agent/poll     - Poll for pending commands")
    print("  POST /agent/report   - Report command execution results")
    print("  GET  /agent/list     - List all registered agents")
    print("")
    print("Press Ctrl+C to stop")
    
    try:
        # Keep the server running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Agent API Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind to (default: 8080)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    print("Starting Agent API Server...")
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Log Level: {'DEBUG' if args.verbose else 'INFO'}")
    print("")
    
    try:
        asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        logger.exception(f"Server error: {e}")
        print(f"Server error: {e}")
