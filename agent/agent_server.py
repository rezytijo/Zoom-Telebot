#!/usr/bin/env python3
"""
Lightweight Agent server to run on host (Windows/Linux).

Usage:
  python agent_server.py --port 8766 --api-key YOUR_KEY

The agent exposes a simple HTTP API (POST /command) secured by header
Authorization: Bearer <API_KEY>. Supported actions:
 - open_url: {"url": "https://..."} -> opens the URL in the default browser (which may trigger Zoom client)
 - hotkey: {"keys": ["alt","q"]} -> sends a hotkey combination using pyautogui

Security: Use a strong API key and run agent behind firewall / only on trusted hosts.

Dependencies: aiohttp, pyautogui
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import webbrowser
from aiohttp import web

logger = logging.getLogger("agent")

try:
    import pyautogui
except Exception:
    pyautogui = None


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

    if action == 'hotkey':
        keys = data.get('keys')
        if not keys or not isinstance(keys, list):
            return web.json_response({'error': 'missing keys array'}, status=400)
        if pyautogui is None:
            return web.json_response({'error': 'pyautogui not installed on agent'}, status=500)
        try:
            # pyautogui.hotkey takes key names as strings
            logger.info('Sending hotkey: %s', keys)
            pyautogui.hotkey(*keys)
            return web.json_response({'ok': True})
        except Exception as e:
            logger.exception('Failed to send hotkey')
            return web.json_response({'error': str(e)}, status=500)

    return web.json_response({'error': 'unknown action'}, status=400)


async def handle_ping(request: web.Request):
    return web.json_response({'ok': True, 'os': platform.system()})


def create_app(api_key: str):
    app = web.Application()
    app['api_key'] = api_key
    app.add_routes([web.post('/command', handle_command), web.get('/ping', handle_ping)])
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--api-key', type=str, required=True)
    parser.add_argument('--host', type=str, default='0.0.0.0')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose (DEBUG) logging to console')
    parser.add_argument('--log-file', type=str, default=None, help='Optional path to write logs to a file')
    parser.add_argument('--server-url', type=str, default=None, help='Optional central server URL for polling mode')
    args = parser.parse_args()

    # Configure logging: console + optional file
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers = [logging.StreamHandler()]
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=handlers)
    if args.log_file:
        fh = logging.FileHandler(args.log_file)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(fh)

    # If a server URL is provided, run in polling mode: agent will poll the server
    if args.server_url:
        # start background polling loop
        async def poll_loop():
            import aiohttp
            agent_info = {
                'name': os.getenv('AGENT_NAME', 'agent'),
                'os_type': os.getenv('AGENT_OS', platform.system()),
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
