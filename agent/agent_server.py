#!/usr/bin/env python3
"""
Lightweight Agent server to run on host (Windows/Linux).

Usage:
  python agent_server.py --api-key YOUR_KEY

Configuration:
  The agent automatically saves its configuration to 'agent_config.json' on first run.
  Subsequent runs will load the saved configuration, so you only need to specify
  parameters when you want to change them.

  Options:
    --config FILE        Configuration file path (default: agent_config.json)
    --reset-config       Reset configuration to defaults and exit
    --port PORT          Port to listen on (default: 8767)
    --api-key KEY        API key for authentication (required)
    --host HOST          Host to bind to (default: 0.0.0.0)
    --verbose            Enable verbose (DEBUG) logging to console
    --log-file FILE      Optional path to write logs to a file
    --server-url URL     Optional central server URL for polling mode

The agent exposes a simple HTTP API (POST /command) secured by header
Authorization: Bearer <API_KEY>. Supported actions:
 - open_url: {"url": "https://..."} -> opens the URL in the default browser (which may trigger Zoom client)
 - start_zoom: {"payload": {"action": "...", "url": "...", ...}} -> opens Zoom meeting URL
 - start-record: {} -> sends Alt+R to start recording in Zoom
 - stop-record: {} -> sends Alt+R to stop recording in Zoom
 - pause-record: {} -> sends Alt+P to pause recording in Zoom
 - resume-record: {} -> sends Alt+P to resume recording in Zoom
 - hotkey: {"keys": ["alt","q"]} -> sends a hotkey combination using pyautogui (legacy support)

When running in polling mode (--server-url), the agent automatically registers with the server
and provides detailed system information (name will be assigned by admin later):
 - os_type: Detailed OS name and version (e.g., "Windows 11 Pro (Version 10.0.22621)")
 - hostname: System hostname
 - ip_address: Primary IP address of the host
 - version: Agent version (e.g., "1.0.0")

Security: Use a strong API key and run agent behind firewall / only on trusted hosts.

Dependencies: aiohttp, pyautogui
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import socket
import sys
import webbrowser
from aiohttp import web

logger = logging.getLogger("agent")

try:
    import pyautogui
except Exception:
    pyautogui = None


def get_system_info():
    """Get detailed system information for agent registration."""
    # OS Type and Version
    system = platform.system()
    if system == 'Windows':
        try:
            import subprocess
            result = subprocess.run(['wmic', 'os', 'get', 'Caption,Version', '/value'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                caption = ""
                version = ""
                for line in lines:
                    if line.startswith('Caption='):
                        caption = line.split('=', 1)[1]
                    elif line.startswith('Version='):
                        version = line.split('=', 1)[1]
                os_type = f"{caption} (Version {version})" if caption else f"Windows {version}"
            else:
                os_type = f"Windows {platform.release()}"
        except Exception:
            os_type = f"Windows {platform.release()}"
    elif system == 'Linux':
        try:
            # Try to get distribution info
            import subprocess
            result = subprocess.run(['lsb_release', '-d', '-s'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                os_type = result.stdout.strip()
            else:
                # Fallback to /etc/os-release
                try:
                    with open('/etc/os-release', 'r') as f:
                        for line in f:
                            if line.startswith('PRETTY_NAME='):
                                os_type = line.split('=', 1)[1].strip().strip('"')
                                break
                        else:
                            os_type = f"Linux {platform.release()}"
                except Exception:
                    os_type = f"Linux {platform.release()}"
        except Exception:
            os_type = f"Linux {platform.release()}"
    else:
        os_type = f"{system} {platform.release()}"

    # Hostname
    hostname = platform.node()
    
    # IP Address (get the primary IP)
    ip_address = "127.0.0.1"  # fallback
    try:
        # Get IP address by connecting to a public DNS server
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
    except Exception:
        try:
            # Fallback: get hostname IP
            ip_address = socket.gethostbyname(hostname)
        except Exception:
            pass
    
    # Agent Version (hardcoded for now, can be made dynamic later)
    agent_version = "1.0.0"
    
    return {
        'os_type': os_type,
        'hostname': hostname,
        'ip_address': ip_address,
        'version': agent_version
    }


def load_config(config_file: str = 'agent_config.json') -> dict:
    """Load configuration from JSON file."""
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info('Loaded configuration from %s', config_file)
                return config
        except Exception as e:
            logger.warning('Failed to load config from %s: %s', config_file, e)
    return {}


def save_config(config: dict, config_file: str = 'agent_config.json') -> bool:
    """Save configuration to JSON file."""
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info('Saved configuration to %s', config_file)
        return True
    except Exception as e:
        logger.error('Failed to save config to %s: %s', config_file, e)
        return False


def create_default_config() -> dict:
    """Create default configuration."""
    return {
        'port': 8767,
        'host': '0.0.0.0',
        'api_key': None,  # Must be provided
        'verbose': False,
        'log_file': None,
        'server_url': None
    }


async def handle_command(request: web.Request):
    api_key_expected = request.app['api_key']
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return web.json_response({'error': 'missing auth'}, status=401)
    token = auth.split(' ', 1)[1]
    if token != api_key_expected:
        return web.json_response({'error': 'invalid token'}, status=403)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid json'}, status=400)

    action = data.get('action')
    if action == 'open_url':
        url = data.get('url')
        if not url:
            return web.json_response({'error': 'missing url'}, status=400)
        logger.info('Opening URL: %s', url)
        try:
            webbrowser.open(url)
            return web.json_response({'ok': True})
        except Exception as e:
            logger.exception('Failed to open URL')
            return web.json_response({'error': str(e)}, status=500)

    if action == 'start_zoom':
        # Payload is JSON with action, url, meeting_id, topic, timeout
        payload = data.get('payload', {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                return web.json_response({'error': 'invalid payload json'}, status=400)
        
        # Get action from payload for identification
        payload_action = payload.get('action', 'unknown')
        url = payload.get('url')
        meeting_id = payload.get('meeting_id')
        topic = payload.get('topic', 'Unknown Meeting')
        timeout = payload.get('timeout', 60)
        
        if not url:
            return web.json_response({'error': 'missing url in payload'}, status=400)
        
        logger.info('Executing %s: %s (ID: %s, Topic: %s)', payload_action, url, meeting_id, topic)
        try:
            webbrowser.open(url)
            return web.json_response({
                'ok': True,
                'meeting_id': meeting_id,
                'topic': topic,
                'action': payload_action,
                'executed_at': 'now'
            })
        except Exception as e:
            logger.exception('Failed to execute %s', payload_action)
            return web.json_response({'error': str(e)}, status=500)

    # Handle recording actions directly
    recording_actions = ['start-record', 'stop-record', 'pause-record', 'resume-record']
    if action in recording_actions:
        # Map recording actions to hotkeys
        action_to_keys = {
            'start-record': ['alt', 'r'],
            'stop-record': ['alt', 'r'],
            'pause-record': ['alt', 'p'],
            'resume-record': ['alt', 'p']
        }
        keys = action_to_keys.get(action)
        if not keys:
            return web.json_response({'error': f'unknown recording action: {action}'}, status=400)
            
        if pyautogui is None:
            return web.json_response({'error': 'pyautogui not installed on agent'}, status=500)
        try:
            # pyautogui.hotkey takes key names as strings
            logger.info('Sending hotkey for action %s: %s', action, keys)
            pyautogui.hotkey(*keys)
            return web.json_response({'ok': True, 'action': action})
        except Exception as e:
            logger.exception('Failed to send hotkey for %s', action)
            return web.json_response({'error': str(e)}, status=500)

    # Legacy hotkey support (for backward compatibility)
    if action == 'hotkey':
        # Support both old format {"keys": ["alt", "r"]} and new format {"action": "start-record"}
        payload_action = data.get('action')
        keys = data.get('keys')
        
        if payload_action:
            # New format: map action to keys
            action_to_keys = {
                'start-record': ['alt', 'r'],
                'stop-record': ['alt', 'r'],
                'pause-record': ['alt', 'p'],
                'resume-record': ['alt', 'p']
            }
            keys = action_to_keys.get(payload_action)
            if not keys:
                return web.json_response({'error': f'unknown recording action: {payload_action}'}, status=400)
        elif keys and isinstance(keys, list):
            # Old format: direct keys array
            pass
        else:
            return web.json_response({'error': 'missing keys array or action'}, status=400)
            
        if pyautogui is None:
            return web.json_response({'error': 'pyautogui not installed on agent'}, status=500)
        try:
            # pyautogui.hotkey takes key names as strings
            logger.info('Sending hotkey for action %s: %s', payload_action or 'legacy', keys)
            pyautogui.hotkey(*keys)
            return web.json_response({'ok': True, 'action': payload_action})
        except Exception as e:
            logger.exception('Failed to send hotkey')
            return web.json_response({'error': str(e)}, status=500)

    return web.json_response({'error': 'unknown action'}, status=400)


async def handle_ping(request: web.Request):
    system_info = get_system_info()
    return web.json_response({
        'ok': True,
        'os': platform.system(),
        'os_type': system_info['os_type'],
        'hostname': system_info['hostname'],
        'ip_address': system_info['ip_address'],
        'version': system_info['version']
    })


def create_app(api_key: str):
    app = web.Application()
    app['api_key'] = api_key
    app.add_routes([web.post('/command', handle_command), web.get('/ping', handle_ping)])
    return app


def main():
    # Load existing configuration
    config_file = 'agent_config.json'
    saved_config = load_config(config_file)
    default_config = create_default_config()
    
    # Merge saved config with defaults
    config = {**default_config, **saved_config}
    
    parser = argparse.ArgumentParser(description='Zoom Agent Server - Lightweight agent for Zoom automation')
    
    # Add config file option
    parser.add_argument('--config', type=str, default=config_file, 
                       help=f'Configuration file path (default: {config_file})')
    parser.add_argument('--reset-config', action='store_true', 
                       help='Reset configuration to defaults and exit')
    
    # Agent configuration arguments
    parser.add_argument('--port', type=int, default=config.get('port', 8767),
                       help=f'Port to listen on (default: {config.get("port", 8767)})')
    parser.add_argument('--api-key', type=str, default=config.get('api_key'),
                       help='API key for authentication (required)')
    parser.add_argument('--host', type=str, default=config.get('host', '0.0.0.0'),
                       help=f'Host to bind to (default: {config.get("host", "0.0.0.0")})')
    parser.add_argument('--verbose', action='store_true', default=config.get('verbose', False),
                       help='Enable verbose (DEBUG) logging to console')
    parser.add_argument('--log-file', type=str, default=config.get('log_file'),
                       help='Optional path to write logs to a file')
    parser.add_argument('--server-url', type=str, default=config.get('server_url'),
                       help='Optional central server URL for polling mode')
    
    args = parser.parse_args()
    
    # Handle reset config option
    if args.reset_config:
        if os.path.exists(config_file):
            os.remove(config_file)
            print(f"Configuration reset. Deleted {config_file}")
        else:
            print(f"No configuration file found at {config_file}")
        sys.exit(0)
    
    # Validate required arguments
    if not args.api_key:
        print("Error: --api-key is required. Use --api-key to specify the API key.")
        print("Example: python agent_server.py --api-key YOUR_API_KEY")
        sys.exit(1)
    
    # Configure logging: console + optional file
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers = [logging.StreamHandler()]
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=handlers)
    if args.log_file:
        fh = logging.FileHandler(args.log_file)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(fh)

    # Save configuration if different from saved config or first run
    current_config = {
        'port': args.port,
        'host': args.host,
        'api_key': args.api_key,
        'verbose': args.verbose,
        'log_file': args.log_file,
        'server_url': args.server_url
    }
    
    if current_config != saved_config:
        if save_config(current_config, config_file):
            logger.info('Configuration saved to %s', config_file)
        else:
            logger.warning('Failed to save configuration')

    # If a server URL is provided, run in polling mode: agent will poll the server
    if args.server_url:
        # start background polling loop
        async def poll_loop():
            import aiohttp
            # Get detailed system information
            system_info = get_system_info()
            agent_info = {
                # 'name' is now optional - will be set by admin when adding agent
                'os_type': system_info['os_type'],
                'hostname': system_info['hostname'],
                'ip_address': system_info['ip_address'],
                'version': system_info['version'],
                'api_key': args.api_key,
                'base_url': f'http://{args.host}:{args.port}'
            }
            # register (best-effort)
            try:
                logger.info('Attempting agent register to %s', args.server_url)
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{args.server_url.rstrip('/')}/agent/register", json=agent_info, timeout=5) as r:
                        logger.info('Register response status: %s', r.status)
                        try:
                            jr = await r.json()
                            logger.debug('Register response body: %s', jr)
                        except Exception:
                            logger.exception('Failed to parse register response json')
                            jr = None
                        if r.status == 200 and jr:
                            aid = jr.get('agent_id')
                            if aid:
                                os.environ['AGENT_ID'] = str(aid)
                                logger.info('Registered agent_id=%s', aid)
                            else:
                                logger.warning('Register response missing agent_id')
                        else:
                            logger.warning('Agent register did not return 200 OK')
            except Exception:
                logger.exception('Agent register attempt failed')

            async with aiohttp.ClientSession() as session:
                while True:
                    try:
                        # poll for commands
                        agent_id_env = os.getenv('AGENT_ID')
                        q = {'agent_id': agent_id_env}
                        headers = {'Authorization': f'Bearer {args.api_key}'}
                        poll_url = f"{args.server_url.rstrip('/')}/agent/poll"
                        logger.debug('Polling %s params=%s', poll_url, q)
                        async with session.get(poll_url, params=q, headers=headers, timeout=30) as resp:
                            logger.debug('Poll response status: %s', resp.status)
                            if resp.status == 200:
                                try:
                                    j = await resp.json()
                                except Exception:
                                    logger.exception('Failed to decode poll json')
                                    j = {}
                                cmds = j.get('commands', []) if isinstance(j, dict) else []
                                logger.info('Polled %d commands', len(cmds))
                                for cmd in cmds:
                                    cid = cmd.get('id')
                                    action = cmd.get('action')
                                    payload = cmd.get('payload')
                                    logger.info('Executing command id=%s action=%s payload=%s', cid, action, payload)
                                    # execute
                                    try:
                                        # Update status to running before execution
                                        try:
                                            running_payload = {'agent_id': agent_id_env, 'command_id': cid, 'status': 'running', 'result': {'message': 'Command execution started'}}
                                            async with session.post(f"{args.server_url.rstrip('/')}/agent/report", json=running_payload, headers=headers, timeout=5) as rep:
                                                logger.debug('Running status report for command %s: %s', cid, rep.status)
                                        except Exception:
                                            logger.exception('Failed to update command %s to running status', cid)
                                        
                                        if action == 'open_url':
                                            # payload may be a plain URL string, or a JSON string like '{"url":"..."}'
                                            url = None
                                            if isinstance(payload, dict):
                                                url = payload.get('url')
                                            elif isinstance(payload, str):
                                                try:
                                                    _parsed = __import__('json').loads(payload)
                                                    if isinstance(_parsed, dict) and 'url' in _parsed:
                                                        url = _parsed.get('url')
                                                    else:
                                                        # treat as raw URL string
                                                        url = payload
                                                except Exception:
                                                    url = payload
                                            if not url:
                                                raise ValueError('missing url in payload')
                                            logger.info('Opening resolved URL: %s', url)
                                            webbrowser.open(url)
                                            result = {'ok': True}
                                            status = 'done'
                                        
                                        elif action == 'start_zoom':
                                            # payload is JSON string with action, url, meeting_id, topic, timeout
                                            if isinstance(payload, str):
                                                try:
                                                    payload_data = json.loads(payload)
                                                except Exception:
                                                    raise ValueError('invalid json payload')
                                            elif isinstance(payload, dict):
                                                payload_data = payload
                                            else:
                                                raise ValueError('invalid payload format')
                                            
                                            # Get action from payload for identification
                                            payload_action = payload_data.get('action', 'unknown')
                                            url = payload_data.get('url')
                                            meeting_id = payload_data.get('meeting_id')
                                            topic = payload_data.get('topic', 'Unknown Meeting')
                                            timeout = payload_data.get('timeout', 60)
                                            
                                            if not url:
                                                raise ValueError('missing url in payload')
                                            
                                            logger.info('Executing %s: %s (ID: %s, Topic: %s)', payload_action, url, meeting_id, topic)
                                            webbrowser.open(url)
                                            result = {
                                                'ok': True,
                                                'meeting_id': meeting_id,
                                                'topic': topic,
                                                'action': payload_action,
                                                'executed_at': 'now'
                                            }
                                            status = 'done'
                                        
                                        elif action == 'hotkey':
                                            if pyautogui is None:
                                                raise RuntimeError('pyautogui not installed')
                                            import json as _j
                                            keys = _j.loads(payload) if isinstance(payload, str) else payload
                                            logger.debug('Hotkey keys resolved: %s', keys)
                                            pyautogui.hotkey(*keys)
                                            result = {'ok': True}
                                            status = 'done'
                                        else:
                                            result = {'error': 'unknown action'}
                                            status = 'failed'
                                    except Exception as e:
                                        logger.exception('Command execution failed: %s', e)
                                        result = {'error': str(e)}
                                        status = 'failed'
                                    # report
                                    try:
                                        report_payload = {'agent_id': agent_id_env, 'command_id': cid, 'status': status, 'result': result}
                                        logger.debug('Reporting result for command %s: %s', cid, report_payload)
                                        async with session.post(f"{args.server_url.rstrip('/')}/agent/report", json=report_payload, headers=headers, timeout=5) as rep:
                                            logger.debug('Report response status: %s', rep.status)
                                    except Exception:
                                        logger.exception('Failed to POST report for command %s', cid)
                            else:
                                try:
                                    text = await resp.text()
                                    logger.warning('Non-200 poll response: %s body=%s', resp.status, text)
                                except Exception:
                                    logger.warning('Non-200 poll response: %s (could not read body)', resp.status)
                            await asyncio.sleep(2)
                    except Exception:
                        logger.exception('Polling loop crashed, sleeping 5s')
                        await asyncio.sleep(5)

        loop = asyncio.get_event_loop()
        loop.create_task(poll_loop())
        # also run local HTTP endpoint to accept direct commands if firewall allows
        app = create_app(args.api_key)
        web.run_app(app, host=args.host, port=args.port)
    else:
        app = create_app(args.api_key)
        web.run_app(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
