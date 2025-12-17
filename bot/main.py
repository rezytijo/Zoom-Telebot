import asyncio
import logging
import signal
import sys
from datetime import datetime
from urllib.parse import urlparse
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from config import settings
from bot.handlers import router
from bot.cloud_recording_handlers import router as cloud_recording_router
from db import init_db, get_user_by_telegram_id, sync_meetings_from_zoom
from bot.middleware import LoggingMiddleware
from zoom import zoom_client


logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown."""
    signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    logger.info("Received signal %s (%d). Initiating graceful shutdown...", signal_name, signum)
    # Raise KeyboardInterrupt to be caught by the main exception handler
    raise KeyboardInterrupt(f"Signal {signal_name} received")


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


async def background_check_timeouts():
    """Background task to check for timed out agent commands every 30 seconds."""
    while True:
        try:
            from db import check_timeout_commands
            timed_out_count = await check_timeout_commands()
            if timed_out_count > 0:
                logger.info("Marked %d commands as failed due to timeout", timed_out_count)
        except Exception as e:
            logger.exception("Error in background timeout check: %s", e)
        
        # Check every 30 seconds
        await asyncio.sleep(30)


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
    
    # Start background timeout check task
    asyncio.create_task(background_check_timeouts())
    logger.info("Background timeout check task started")


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
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO), format=settings.LOG_FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
    # Add file handler for logging to file with dynamic name
    log_filename = f"./logs/{datetime.now().strftime('%d-%b-%Y')}-{settings.LOG_LEVEL.upper()}.log"
    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(logging.Formatter(settings.LOG_FORMAT, datefmt='%Y-%m-%d %H:%M:%S'))
    logging.getLogger().addHandler(file_handler)
    logger.info("Initializing bot")

    # Register signal handlers for graceful shutdown
    try:
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        logger.info("Signal handlers registered for graceful shutdown")
    except (OSError, ValueError) as e:
        # Signal handling might not be available on all platforms (e.g., Windows)
        logger.warning("Signal handling not available: %s", e)

    # Validate required settings
    if not settings.bot_token:
        logger.error("TELEGRAM_TOKEN not configured. Please set it in .env file.")
        return

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    # Include cloud recording handlers FIRST (before generic handlers)
    dp.include_router(cloud_recording_router)
    dp.include_router(router)

    # Register middleware for guaranteed pre-handler logging
    dp.update.middleware(LoggingMiddleware())
    
    # Register startup handler
    dp.startup.register(on_startup)

    try:
        # run polling by default
        logger.info("Bot started successfully. Press Ctrl+C to stop.")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot shutdown initiated by user (Ctrl+C)")
    except asyncio.CancelledError:
        logger.info("Bot polling was cancelled")
    except Exception as e:
        logger.error("Unexpected error during bot operation: %s", e)
        raise
    finally:
        logger.info("Closing bot session...")
        await bot.session.close()
        logger.info("Bot session closed. Shutdown complete.")


if __name__ == '__main__':
    asyncio.run(main())
