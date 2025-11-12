#!/usr/bin/env python3
"""
Standalone Agent API Server

This script runs only the agent API server without the Telegram bot.
Useful for running the API service independently.
"""

import asyncio
import logging
from urllib.parse import urlparse
from aiohttp import web
from config import settings
from api.agent_api import create_app
from db import init_db

logger = logging.getLogger(__name__)


async def main():
    # Initialize logging
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format=settings.LOG_FORMAT,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Initialize database
    logger.info("Initializing database...")
    await init_db()

    # Create and start the API server
    app = create_app()

    # Determine host from AGENT_BASE_URL if set, else default to 0.0.0.0
    host = '0.0.0.0'
    if settings.AGENT_BASE_URL:
        parsed = urlparse(settings.AGENT_BASE_URL)
        if parsed.hostname:
            host = parsed.hostname

    # Use AppRunner for cleaner startup
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, settings.AGENT_API_PORT)
    await site.start()

    logger.info("======== Agent API server running on http://%s:%s ========", host, settings.AGENT_API_PORT)
    print(f"======== Agent API server running on http://{host}:{settings.AGENT_API_PORT} ========")

    try:
        # Keep the server running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down API server...")
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())