#!/usr/bin/env python3
"""
Database Schema Verification Script
Verifies that the database has all required tables and columns
"""

import asyncio
import aiosqlite
from config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def verify_schema():
    """Verify database schema is correct and up to date"""
    logger.info("🔍 Verifying database schema...")
    
    async with aiosqlite.connect(settings.db_path) as db:
        # Check required tables
        required_tables = [
            'users',
            'meetings',
            'meeting_live_status',
            'shortlinks',
            'agents',
            'agent_commands'
        ]
        
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = [row[0] for row in await cursor.fetchall()]
        
        logger.info(f"✅ Found {len(existing_tables)} tables: {', '.join(existing_tables)}")
        
        missing_tables = [t for t in required_tables if t not in existing_tables]
        if missing_tables:
            logger.error(f"❌ Missing tables: {', '.join(missing_tables)}")
            return False
        
        # Check meeting_live_status columns (most important for recording status)
        cursor = await db.execute("PRAGMA table_info(meeting_live_status)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        required_columns = [
            'zoom_meeting_id',
            'live_status',
            'recording_status',  # Critical for recording tracking
            'recording_started_at',
            'agent_id',
            'updated_at'
        ]
        
        logger.info(f"✅ meeting_live_status columns: {', '.join(column_names)}")
        
        missing_columns = [c for c in required_columns if c not in column_names]
        if missing_columns:
            logger.error(f"❌ Missing columns in meeting_live_status: {', '.join(missing_columns)}")
            return False
        
        # Check sample data
        cursor = await db.execute("SELECT COUNT(*) FROM meetings")
        meeting_count = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT COUNT(*) FROM meeting_live_status")
        status_count = (await cursor.fetchone())[0]
        
        logger.info(f"📊 Database stats:")
        logger.info(f"   - {meeting_count} meetings")
        logger.info(f"   - {status_count} recording status entries")
        
        logger.info("✅ Database schema verification passed!")
        return True


if __name__ == "__main__":
    success = asyncio.run(verify_schema())
    exit(0 if success else 1)
