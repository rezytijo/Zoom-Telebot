import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from config import settings
from handlers import router
from db import init_db, get_user_by_telegram_id, sync_meetings_from_zoom
from middleware import LoggingMiddleware
from zoom import zoom_client


logger = logging.getLogger(__name__)


async def background_sync_meetings():
    """Background task to sync meetings from Zoom to database every 30 minutes."""
    while True:
        try:
            logger.info("Running scheduled meeting sync")
            stats = await sync_meetings_from_zoom(zoom_client)
            logger.info("Meeting sync completed: %s", stats)
        except Exception as e:
            logger.exception("Error in background meeting sync: %s", e)
        
        # Wait 30 minutes before next sync
        await asyncio.sleep(30 * 60)  # 30 minutes


async def on_startup(bot: Bot):
    logger.info("Bot starting...")
    
    # Run initial sync on startup
    logger.info("Running initial meeting sync on startup...")
    try:
        stats = await sync_meetings_from_zoom(zoom_client)
        logger.info("Initial meeting sync completed: %s", stats)
    except Exception as e:
        logger.exception("Error in initial meeting sync: %s", e)
    
    # Start background sync task
    asyncio.create_task(background_sync_meetings())
    logger.info("Background meeting sync task started")
    # Start agent API server (for agents to poll commands)
    try:
        from agent.agent_api import create_app
        from config import settings
        app = create_app()
        # run aiohttp app in background
        asyncio.create_task(asyncio.to_thread(lambda: __import__('aiohttp').web.run_app(app, host='0.0.0.0', port=settings.AGENT_API_PORT)))
        logger.info("Agent API server started on port %s", settings.AGENT_API_PORT)
    except Exception as e:
        logger.exception("Failed to start agent API server: %s", e)


async def main():
    # Run environment setup first
    logger.info("Running environment setup...")
    try:
        from setup import EnvironmentSetup
        setup = EnvironmentSetup()
        if not await setup.setup_environment():
            logger.error("Environment setup failed. Please run 'python setup.py' to fix issues.")
            return
    except ImportError:
        logger.warning("Setup module not found. Skipping environment validation.")
    except Exception as e:
        logger.exception("Error during environment setup: %s", e)
        return

    await init_db()
    # configure logging early
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO), format=settings.LOG_FORMAT)
    # Add file handler for logging to file with dynamic name
    log_filename = f"./logs/{datetime.now().strftime('%d-%b-%Y')}-{settings.LOG_LEVEL.upper()}.log"
    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)
    logger.info("Initializing bot")

    # Validate required settings
    if not settings.bot_token:
        logger.error("TELEGRAM_TOKEN not configured. Please set it in .env file.")
        return

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    # Register middleware for guaranteed pre-handler logging
    dp.update.middleware(LoggingMiddleware())
    
    # Register startup handler
    dp.startup.register(on_startup)

    try:
        # run polling by default
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
