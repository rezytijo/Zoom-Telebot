#!/usr/bin/env python3
"""
Manual Database Migration Runner
Runs all pending migrations on existing database.
Safe to run multiple times - migrations are idempotent.

Usage:
    python scripts/run_migration.py
    
Or within Docker container:
    docker exec -it <container_name> python scripts/run_migration.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from db.db import run_migrations
import aiosqlite

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Run database migrations."""
    logger.info("=" * 60)
    logger.info("Database Migration Runner")
    logger.info("=" * 60)
    logger.info("Database Path: %s", settings.db_path)
    
    # Check if database exists
    db_path = Path(settings.db_path)
    if not db_path.exists():
        logger.error("❌ Database file not found: %s", settings.db_path)
        logger.error("Please ensure the bot has been initialized first.")
        return 1
    
    logger.info("✓ Database file found")
    logger.info("")
    
    try:
        # Open database connection
        async with aiosqlite.connect(settings.db_path) as db:
            logger.info("🔄 Running migrations...")
            logger.info("")
            
            # Run migrations
            await run_migrations(db)
            
            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ Migration completed successfully!")
            logger.info("=" * 60)
            logger.info("")
            logger.info("Next steps:")
            logger.info("  1. Restart the bot to apply changes")
            logger.info("  2. Verify functionality")
            logger.info("")
            
            return 0
            
    except Exception as e:
        logger.error("")
        logger.error("=" * 60)
        logger.error("❌ Migration failed!")
        logger.error("=" * 60)
        logger.exception("Error details: %s", e)
        logger.error("")
        logger.error("Troubleshooting:")
        logger.error("  1. Ensure no other processes are using the database")
        logger.error("  2. Check database file permissions")
        logger.error("  3. Verify database is not corrupted")
        logger.error("")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\nMigration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        sys.exit(1)
