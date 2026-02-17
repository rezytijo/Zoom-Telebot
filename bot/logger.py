import logging
import sys
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from config import settings

# Create logs directory if it doesn't exist
LOGS_DIR = "logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

def setup_logging():
    """
    Setup centralized logging configuration.
    Configures logging to both console and daily rotating file.
    """
    # Determine log level
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Common formatter
    log_format = settings.LOG_FORMAT
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplication
    if root_logger.handlers:
        root_logger.handlers.clear()

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. File Handler (Timed Rotating - Daily)
    # Filename format: logs/zoom-telebot.log (current), rotated to zoom-telebot.YYYY-MM-DD.log
    log_file = os.path.join(LOGS_DIR, "zoom-telebot.log")
    
    # Prepare TimedRotatingFileHandler
    # when='midnight', interval=1, backupCount=30 (keep 30 days)
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.suffix = "%Y-%m-%d" # Suffix for rotated files
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Log initial setup message
    logging.info(f"Logging initialized. Level: {settings.LOG_LEVEL}, File: {log_file}")

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    Usage: logger = get_logger(__name__)
    """
    return logging.getLogger(name)
