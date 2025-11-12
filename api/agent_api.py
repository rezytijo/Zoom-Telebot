"""Agent API for server: endpoints agents poll to fetch commands and report results.

This module exposes an aiohttp app to be started in the bot process.
"""
from aiohttp import web
import asyncio
import json
import logging
from db import add_agent, list_agents, get_agent, get_pending_commands, update_command_status, update_agent_last_seen
from config import settings
import os

logger = logging.getLogger(__name__)


async def handle_register(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid json'}, status=400)

    name = body.get('name')
    os_type = body.get('os_type')
    api_key = body.get('api_key')
    base_url = body.get('base_url', '')
    if not name:
        return web.json_response({'error': 'missing name'}, status=400)
    try:
        # if api_key provided, use it; otherwise server will store provided value
        agent_id = await add_agent(name, base_url or '', api_key, os_type)
        return web.json_response({'ok': True, 'agent_id': agent_id, 'api_key': api_key})
    except Exception as e:
        logger.exception('register failed')
        return web.json_response({'error': str(e)}, status=500)


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


def create_app():
    app = web.Application()
    app.add_routes([
        web.post('/agent/register', handle_register),
        web.get('/agent/poll', handle_poll),
        web.post('/agent/report', handle_report),
    ])
    return app
