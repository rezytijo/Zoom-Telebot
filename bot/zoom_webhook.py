"""Minimal verified Zoom webhook receiver for meeting lifecycle events."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

from aiohttp import web

from config import settings
from db import update_meeting_live_status


logger = logging.getLogger(__name__)


def _signature(timestamp: str, body: bytes) -> str:
    message = b"v0:" + timestamp.encode() + b":" + body
    digest = hmac.new(
        (settings.zoom_webhook_secret_token or "").encode(), message, hashlib.sha256
    ).hexdigest()
    return f"v0={digest}"


async def receive_zoom_webhook(request: web.Request) -> web.Response:
    body = await request.read()
    timestamp = request.headers.get("x-zm-request-timestamp", "")
    supplied = request.headers.get("x-zm-signature", "")
    if not settings.zoom_webhook_secret_token:
        raise web.HTTPServiceUnavailable(text="Zoom webhook secret is not configured")
    try:
        if abs(int(time.time()) - int(timestamp)) > 300:
            raise web.HTTPUnauthorized(text="stale webhook")
    except ValueError:
        raise web.HTTPUnauthorized(text="invalid timestamp")
    if not hmac.compare_digest(supplied, _signature(timestamp, body)):
        raise web.HTTPUnauthorized(text="invalid signature")

    payload = json.loads(body)
    if payload.get("event") == "endpoint.url_validation":
        plain_token = payload.get("payload", {}).get("plainToken", "")
        encrypted = hmac.new(
            settings.zoom_webhook_secret_token.encode(), plain_token.encode(), hashlib.sha256
        ).hexdigest()
        return web.json_response({"plainToken": plain_token, "encryptedToken": encrypted})

    meeting = payload.get("payload", {}).get("object", {})
    meeting_id = meeting.get("id")
    if meeting_id is not None:
        event = payload.get("event")
        if event == "meeting.started":
            await update_meeting_live_status(str(meeting_id), "started")
        elif event == "meeting.ended":
            await update_meeting_live_status(str(meeting_id), "ended")
    return web.json_response({"ok": True})


async def start_zoom_webhook_server():
    if not settings.zoom_webhook_secret_token:
        logger.warning("ZOOM_WEBHOOK_SECRET_TOKEN is not configured; webhook receiver disabled")
        return None
    app = web.Application(client_max_size=1024 * 1024)
    app.router.add_post("/webhooks/zoom", receive_zoom_webhook)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, settings.zoom_webhook_host, settings.zoom_webhook_port)
    await site.start()
    logger.info("Zoom webhook receiver listening on port %s", settings.zoom_webhook_port)
    return runner
