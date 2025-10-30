import aiosqlite
from typing import Optional, List, Dict
from config import settings
import logging
import os
import zipfile
import json
from datetime import datetime
import tempfile
import shutil

logger = logging.getLogger(__name__)


CREATE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        status TEXT DEFAULT 'pending', -- pending, whitelisted, banned
        role TEXT DEFAULT 'guest' -- guest, user, owner
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zoom_meeting_id TEXT UNIQUE,
        topic TEXT,
        start_time TEXT,
        join_url TEXT,
        status TEXT DEFAULT 'active', -- active, deleted, expired
        created_by TEXT, -- INTEGER (telegram_id) for bot-created, "CreatedFromZoomApp" for zoom-created
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shortlinks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_url TEXT NOT NULL,
        short_url TEXT,
        provider TEXT NOT NULL,
        custom_alias TEXT,
        zoom_meeting_id TEXT, -- NULL if not for meeting
        status TEXT DEFAULT 'active', -- active, failed, deleted
        created_by INTEGER, -- telegram_id of creator
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        error_message TEXT -- error if creation failed
    )
    """,
]


async def init_db():
    logger.info("Initializing database at %s", settings.db_path)
    async with aiosqlite.connect(settings.db_path) as db:
        for s in CREATE_SQL:
            await db.execute(s)
        
        # Run migrations
        await run_migrations(db)
        
        await db.commit()
    logger.info("Database initialized")


async def add_pending_user(telegram_id: int, username: Optional[str]):
    logger.debug("add_pending_user telegram_id=%s username=%s", telegram_id, username)
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, status, role) VALUES (?, ?, 'pending', 'guest')",
            (telegram_id, username),
        )
        await db.commit()
    logger.info("User %s added to pending list", telegram_id)


async def list_pending_users() -> List[Dict]:
    logger.debug("list_pending_users called")
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute("SELECT id, telegram_id, username, status, role FROM users WHERE status = 'pending'")
        rows = await cur.fetchall()
        return [dict(id=r[0], telegram_id=r[1], username=r[2], status=r[3], role=r[4]) for r in rows]


async def list_all_users() -> List[Dict]:
    logger.debug("list_all_users called")
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute("SELECT id, telegram_id, username, status, role FROM users ORDER BY id DESC")
        rows = await cur.fetchall()
        return [dict(id=r[0], telegram_id=r[1], username=r[2], status=r[3], role=r[4]) for r in rows]


async def update_user_status(telegram_id: int, status: str, role: Optional[str] = None):
    logger.debug("update_user_status telegram_id=%s status=%s role=%s", telegram_id, status, role)
    async with aiosqlite.connect(settings.db_path) as db:
        if role:
            await db.execute("UPDATE users SET status = ?, role = ? WHERE telegram_id = ?", (status, role, telegram_id))
        else:
            await db.execute("UPDATE users SET status = ? WHERE telegram_id = ?", (status, telegram_id))
        await db.commit()
    logger.info("User %s status updated to %s", telegram_id, status)


async def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict]:
    logger.debug("get_user_by_telegram_id %s", telegram_id)
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute("SELECT id, telegram_id, username, status, role FROM users WHERE telegram_id = ?", (telegram_id,))
        r = await cur.fetchone()
        if not r:
            logger.debug("get_user_by_telegram_id: not found %s", telegram_id)
            return None
        user = dict(id=r[0], telegram_id=r[1], username=r[2], status=r[3], role=r[4])
        logger.debug("get_user_by_telegram_id: found %s -> %s", telegram_id, user)
        return user


async def ban_toggle_user(telegram_id: int, banned: bool):
    status = 'banned' if banned else 'whitelisted'
    role = 'guest' if banned else 'user'
    logger.debug("ban_toggle_user %s banned=%s", telegram_id, banned)
    await update_user_status(telegram_id, status, role)


async def delete_user(telegram_id: int):
    """Delete a user row from the database by telegram_id."""
    logger.debug("delete_user %s", telegram_id)
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        await db.commit()
    logger.info("User %s deleted from database", telegram_id)


# Meetings functions
async def add_meeting(zoom_meeting_id: str, topic: str, start_time: str, join_url: str, created_by: int):
    logger.debug("add_meeting zoom_id=%s topic=%s created_by=%s", zoom_meeting_id, topic, created_by)
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT INTO meetings (zoom_meeting_id, topic, start_time, join_url, created_by, status) VALUES (?, ?, ?, ?, ?, 'active')",
            (zoom_meeting_id, topic, start_time, join_url, created_by),
        )
        await db.commit()
    logger.info("Meeting %s added to DB", zoom_meeting_id)


async def update_meeting_short_url(zoom_meeting_id: str, short_url: str):
    logger.debug("update_meeting_short_url zoom_id=%s short_url=%s", zoom_meeting_id, short_url)
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("UPDATE meetings SET short_url = ?, updated_at = CURRENT_TIMESTAMP WHERE zoom_meeting_id = ?", (short_url, zoom_meeting_id))
        await db.commit()
    logger.info("Meeting %s short URL updated", zoom_meeting_id)


async def update_meeting_short_url_by_join_url(join_url: str, short_url: str):
    logger.debug("update_meeting_short_url_by_join_url join_url=%s short_url=%s", join_url, short_url)
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("UPDATE meetings SET short_url = ?, updated_at = CURRENT_TIMESTAMP WHERE join_url = ?", (short_url, join_url))
        await db.commit()
    logger.info("Meeting with join_url %s short URL updated", join_url)

async def list_meetings() -> List[Dict]:
    logger.debug("list_meetings called")
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute("SELECT id, zoom_meeting_id, topic, start_time, join_url, status, created_by, created_at, updated_at FROM meetings ORDER BY created_at DESC")
        rows = await cur.fetchall()
        return [dict(id=r[0], zoom_meeting_id=r[1], topic=r[2], start_time=r[3], join_url=r[4], status=r[5], created_by=r[6], created_at=r[7], updated_at=r[8]) for r in rows]


async def list_meetings_with_shortlinks() -> List[Dict]:
    """List meetings with their associated shortlinks"""
    logger.debug("list_meetings_with_shortlinks called")
    async with aiosqlite.connect(settings.db_path) as db:
        # Get meetings
        meetings_cur = await db.execute("""
            SELECT id, zoom_meeting_id, topic, start_time, join_url, status, created_by, created_at, updated_at
            FROM meetings
            WHERE status = 'active'
            ORDER BY created_at DESC
        """)
        meetings_rows = await meetings_cur.fetchall()
        
        meetings = []
        for r in meetings_rows:
            meeting = dict(
                id=r[0],
                zoom_meeting_id=r[1],
                topic=r[2],
                start_time=r[3],
                join_url=r[4],
                status=r[5],
                created_by=r[6],
                created_at=r[7],
                updated_at=r[8]
            )
            
            # Get shortlinks for this meeting
            shortlinks_cur = await db.execute("""
                SELECT id, original_url, short_url, provider, custom_alias, status, created_at, error_message
                FROM shortlinks 
                WHERE zoom_meeting_id = ? AND status = 'active'
                ORDER BY created_at DESC
            """, (meeting['zoom_meeting_id'],))
            shortlinks_rows = await shortlinks_cur.fetchall()
            
            meeting['shortlinks'] = [
                dict(
                    id=r[0],
                    original_url=r[1],
                    short_url=r[2],
                    provider=r[3],
                    custom_alias=r[4],
                    status=r[5],
                    created_at=r[6],
                    error_message=r[7]
                ) for r in shortlinks_rows
            ]
            
            meetings.append(meeting)
        
        return meetings


async def update_meeting_status(zoom_meeting_id: str, status: str):
    """Update meeting status (active, deleted, expired)"""
    logger.debug("update_meeting_status zoom_id=%s status=%s", zoom_meeting_id, status)
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("UPDATE meetings SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE zoom_meeting_id = ?", (status, zoom_meeting_id))
        await db.commit()
    logger.info("Meeting %s status updated to %s", zoom_meeting_id, status)


async def sync_meetings_from_zoom(zoom_client) -> Dict[str, int]:
    """
    Sync meetings from Zoom API to database and update expired meetings.
    Returns dict with counts: {'added': int, 'updated': int, 'deleted': int, 'expired': int, 'errors': int}
    """
    logger.info("Starting Zoom meetings sync with expiry check")
    stats = {'added': 0, 'updated': 0, 'deleted': 0, 'expired': 0, 'errors': 0}

    try:
        from datetime import datetime, timezone

        # Get current time in UTC for expiry check
        now = datetime.now(timezone.utc)

        # Get meetings from Zoom
        zoom_data = await zoom_client.list_upcoming_meetings('me')
        zoom_meetings = zoom_data.get('meetings', [])
        zoom_ids = {str(meeting.get('id', '')) for meeting in zoom_meetings if meeting.get('id')}
        logger.info("Found %d active meetings in Zoom", len(zoom_ids))

        # Get existing meetings from DB (all statuses)
        existing_meetings = await list_meetings()
        existing_by_id = {m['zoom_meeting_id']: m for m in existing_meetings}
        existing_active = {m['zoom_meeting_id']: m for m in existing_meetings if m['status'] == 'active'}
        logger.info("Found %d total meetings in DB (%d active)", len(existing_by_id), len(existing_active))

        async with aiosqlite.connect(settings.db_path) as db:
            # Mark meetings that exist in DB but not in Zoom as deleted
            for zoom_id, meeting in existing_active.items():
                if zoom_id not in zoom_ids:
                    try:
                        await db.execute("UPDATE meetings SET status = 'deleted', updated_at = CURRENT_TIMESTAMP WHERE zoom_meeting_id = ?", (zoom_id,))
                        stats['deleted'] += 1
                        logger.debug("Marked meeting %s as deleted", zoom_id)
                    except Exception as e:
                        logger.exception("Failed to mark meeting %s as deleted: %s", zoom_id, e)
                        stats['errors'] += 1

            # Process meetings from Zoom
            for meeting in zoom_meetings:
                zoom_id = str(meeting.get('id', ''))
                if not zoom_id:
                    logger.warning("Meeting without ID: %s", meeting)
                    stats['errors'] += 1
                    continue

                topic = meeting.get('topic', 'No Topic')
                start_time = meeting.get('start_time', '')
                join_url = meeting.get('join_url', '')

                if zoom_id not in existing_active:
                    # Check if meeting exists but is not active (deleted/expired)
                    if zoom_id in existing_by_id:
                        # Reactivate existing meeting
                        try:
                            await db.execute(
                                "UPDATE meetings SET topic = ?, start_time = ?, join_url = ?, status = 'active', updated_at = CURRENT_TIMESTAMP WHERE zoom_meeting_id = ?",
                                (topic, start_time, join_url, zoom_id),
                            )
                            stats['updated'] += 1
                            logger.debug("Reactivated meeting %s: %s", zoom_id, topic)
                        except Exception as e:
                            logger.exception("Failed to reactivate meeting %s: %s", zoom_id, e)
                            stats['errors'] += 1
                    else:
                        # Add new meeting
                        try:
                            await db.execute(
                                "INSERT INTO meetings (zoom_meeting_id, topic, start_time, join_url, status, created_by) VALUES (?, ?, ?, ?, 'active', 'CreatedFromZoomApp')",
                                (zoom_id, topic, start_time, join_url),
                            )
                            stats['added'] += 1
                            logger.debug("Added meeting %s: %s", zoom_id, topic)
                        except Exception as e:
                            logger.exception("Failed to add meeting %s: %s", zoom_id, e)
                            stats['errors'] += 1
                else:
                    # Update existing meeting if needed
                    existing = existing_active[zoom_id]
                    needs_update = (
                        existing['topic'] != topic or
                        existing['start_time'] != start_time or
                        existing['join_url'] != join_url
                    )
                    if needs_update:
                        try:
                            await db.execute(
                                "UPDATE meetings SET topic = ?, start_time = ?, join_url = ?, updated_at = CURRENT_TIMESTAMP WHERE zoom_meeting_id = ?",
                                (topic, start_time, join_url, zoom_id)
                            )
                            stats['updated'] += 1
                            logger.debug("Updated meeting %s: %s", zoom_id, topic)
                        except Exception as e:
                            logger.exception("Failed to update meeting %s: %s", zoom_id, e)
                            stats['errors'] += 1

            # Check for expired meetings among all active meetings in DB
            cursor = await db.execute("""
                SELECT zoom_meeting_id, topic, start_time
                FROM meetings
                WHERE status = 'active' AND start_time IS NOT NULL
            """)
            active_meetings = await cursor.fetchall()

            for zoom_id, topic, start_time_str in active_meetings:
                try:
                    # Parse start_time - handle different formats
                    if start_time_str.endswith('Z'):
                        # ISO format with Z (UTC)
                        start_time = datetime.fromisoformat(start_time_str[:-1]).replace(tzinfo=timezone.utc)
                    else:
                        # Try parsing as ISO format, assume UTC if no timezone
                        start_time = datetime.fromisoformat(start_time_str)
                        if start_time.tzinfo is None:
                            start_time = start_time.replace(tzinfo=timezone.utc)

                    # Check if meeting has expired (current time > start time)
                    if now > start_time:
                        await db.execute(
                            "UPDATE meetings SET status = 'expired', updated_at = CURRENT_TIMESTAMP WHERE zoom_meeting_id = ?",
                            (zoom_id,)
                        )
                        stats['expired'] += 1
                        logger.debug("Marked meeting %s (%s) as expired", zoom_id, topic)

                except Exception as e:
                    logger.warning("Failed to process meeting %s: %s", zoom_id, e)
                    stats['errors'] += 1

            await db.commit()

        logger.info("Zoom sync with expiry check completed: added=%d, updated=%d, deleted=%d, expired=%d, errors=%d",
                   stats['added'], stats['updated'], stats['deleted'], stats['expired'], stats['errors'])
        return stats

    except Exception as e:
        logger.exception("Failed to sync meetings from Zoom: %s", e)
        stats['errors'] += 1
        return stats


async def update_expired_meetings() -> Dict[str, int]:
    """
    Update status of meetings that have passed their start time to 'expired'.
    Returns dict with counts: {'expired': int, 'errors': int}
    """
    logger.info("Checking for expired meetings")
    stats = {'expired': 0, 'errors': 0}

    try:
        from datetime import datetime, timezone

        # Get current time in UTC
        now = datetime.now(timezone.utc)

        async with aiosqlite.connect(settings.db_path) as db:
            # Get all active meetings
            cursor = await db.execute("""
                SELECT zoom_meeting_id, topic, start_time
                FROM meetings
                WHERE status = 'active' AND start_time IS NOT NULL
            """)
            active_meetings = await cursor.fetchall()

            for zoom_id, topic, start_time_str in active_meetings:
                try:
                    # Parse start_time - handle different formats
                    if start_time_str.endswith('Z'):
                        # ISO format with Z (UTC)
                        start_time = datetime.fromisoformat(start_time_str[:-1]).replace(tzinfo=timezone.utc)
                    else:
                        # Try parsing as ISO format, assume UTC if no timezone
                        start_time = datetime.fromisoformat(start_time_str)
                        if start_time.tzinfo is None:
                            start_time = start_time.replace(tzinfo=timezone.utc)

                    # Check if meeting has expired (current time > start time)
                    if now > start_time:
                        await db.execute(
                            "UPDATE meetings SET status = 'expired', updated_at = CURRENT_TIMESTAMP WHERE zoom_meeting_id = ?",
                            (zoom_id,)
                        )
                        stats['expired'] += 1
                        logger.debug("Marked meeting %s (%s) as expired", zoom_id, topic)

                except Exception as e:
                    logger.warning("Failed to process meeting %s: %s", zoom_id, e)
                    stats['errors'] += 1

            await db.commit()

        logger.info("Expired meetings update completed: expired=%d, errors=%d", stats['expired'], stats['errors'])
        return stats

    except Exception as e:
        logger.exception("Failed to update expired meetings: %s", e)
        stats['errors'] += 1
        return stats


async def run_migrations(db):
    """Run database migrations"""
    try:
        # Check for status column
        cur = await db.execute("PRAGMA table_info(meetings)")
        columns = await cur.fetchall()
        column_names = [col[1] for col in columns]
        column_types = {col[1]: col[2] for col in columns}
        
        if 'status' not in column_names:
            logger.info("Adding status column to meetings table")
            await db.execute("ALTER TABLE meetings ADD COLUMN status TEXT DEFAULT 'active'")
        
        if 'updated_at' not in column_names:
            logger.info("Adding updated_at column to meetings table")
            await db.execute("ALTER TABLE meetings ADD COLUMN updated_at TIMESTAMP")
            # Set default value for existing records
            await db.execute("UPDATE meetings SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
        
        # Check if created_by is still INTEGER, convert to TEXT
        if 'created_by' in column_types and column_types['created_by'].upper() == 'INTEGER':
            logger.info("Converting created_by column from INTEGER to TEXT")
            # SQLite doesn't support direct type change, so we recreate the column
            await db.execute("ALTER TABLE meetings ADD COLUMN created_by_new TEXT")
            await db.execute("UPDATE meetings SET created_by_new = CAST(created_by AS TEXT) WHERE created_by IS NOT NULL")
            await db.execute("UPDATE meetings SET created_by_new = 'CreatedFromZoomApp' WHERE created_by = '0'")
            await db.execute("DROP INDEX IF EXISTS idx_meetings_created_by")  # Drop any potential indexes
            await db.execute("ALTER TABLE meetings DROP COLUMN created_by")
            await db.execute("ALTER TABLE meetings RENAME COLUMN created_by_new TO created_by")
            
        # Update existing records to have proper created_by values
        await db.execute("UPDATE meetings SET created_by = 'CreatedFromZoomApp' WHERE created_by IS NULL OR created_by = '0'")
        await db.execute("UPDATE meetings SET status = 'active' WHERE status IS NULL")
        
    except Exception as e:
        logger.exception("Migration failed: %s", e)


# Shortlinks functions
async def add_shortlink(original_url: str, short_url: Optional[str], provider: str, custom_alias: Optional[str] = None, zoom_meeting_id: Optional[str] = None, created_by: Optional[int] = None, error_message: Optional[str] = None) -> int:
    """Add a new shortlink record. Returns the ID of the inserted record."""
    status = 'failed' if error_message else 'active'
    
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute("""
            INSERT INTO shortlinks (original_url, short_url, provider, custom_alias, zoom_meeting_id, status, created_by, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (original_url, short_url, provider, custom_alias, zoom_meeting_id, status, created_by, error_message))
        
        shortlink_id = cursor.lastrowid
        await db.commit()
        
        logger.info("Added shortlink record: id=%s, original_url=%s, short_url=%s, provider=%s, custom_alias=%s, status=%s", 
                   shortlink_id, original_url, short_url, provider, custom_alias, status)
        
        return shortlink_id


async def update_shortlink_status(shortlink_id: int, status: str, short_url: Optional[str] = None, error_message: Optional[str] = None):
    """Update shortlink status and optionally short_url or error_message."""
    async with aiosqlite.connect(settings.db_path) as db:
        if short_url:
            await db.execute("""
                UPDATE shortlinks SET status = ?, short_url = ?, error_message = NULL WHERE id = ?
            """, (status, short_url, shortlink_id))
        elif error_message:
            await db.execute("""
                UPDATE shortlinks SET status = ?, error_message = ? WHERE id = ?
            """, (status, error_message, shortlink_id))
        else:
            await db.execute("""
                UPDATE shortlinks SET status = ? WHERE id = ?
            """, (status, shortlink_id))
        
        await db.commit()
        logger.info("Updated shortlink %s status to %s", shortlink_id, status)


async def get_shortlinks_by_user(created_by: int, limit: int = 50) -> List[Dict]:
    """Get shortlinks created by a specific user."""
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute("""
            SELECT id, original_url, short_url, provider, custom_alias, zoom_meeting_id, status, created_at, error_message
            FROM shortlinks 
            WHERE created_by = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (created_by, limit))
        
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        return [dict(zip(columns, row)) for row in rows]


async def get_shortlink_stats() -> Dict:
    """Get statistics about shortlinks."""
    async with aiosqlite.connect(settings.db_path) as db:
        # Total shortlinks
        cursor = await db.execute("SELECT COUNT(*) FROM shortlinks")
        result = await cursor.fetchone()
        total = result[0] if result else 0
        
        # Active shortlinks
        cursor = await db.execute("SELECT COUNT(*) FROM shortlinks WHERE status = 'active'")
        result = await cursor.fetchone()
        active = result[0] if result else 0
        
        # Failed shortlinks
        cursor = await db.execute("SELECT COUNT(*) FROM shortlinks WHERE status = 'failed'")
        result = await cursor.fetchone()
        failed = result[0] if result else 0
        
        # Shortlinks by provider
        cursor = await db.execute("""
            SELECT provider, COUNT(*) as count 
            FROM shortlinks 
            GROUP BY provider 
            ORDER BY count DESC
        """)
        provider_rows = await cursor.fetchall()
        by_provider = {row[0]: row[1] for row in provider_rows}
        
        return {
            'total': total,
            'active': active,
            'failed': failed,
            'by_provider': by_provider
        }


# Backup and Restore Functions

async def backup_database() -> str:
    """Create SQL dump of the database.

    Returns path to the SQL dump file.
    """
    logger.info("Creating database backup")
    dump_file = tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False)

    try:
        async with aiosqlite.connect(settings.db_path) as db:
            # Get all table names
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = await cursor.fetchall()

            dump_file.write("-- Zoom-Telebot Database Backup\n")
            dump_file.write(f"-- Created at: {datetime.now().isoformat()}\n\n")

            for table_name, in tables:
                if table_name.startswith('sqlite_'):
                    continue  # Skip SQLite internal tables

                logger.debug("Dumping table: %s", table_name)

                # Write table schema
                cursor = await db.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                schema = await cursor.fetchone()
                if schema and schema[0]:
                    dump_file.write(f"{schema[0]};\n\n")

                # Write table data
                cursor = await db.execute(f"SELECT * FROM {table_name}")
                rows = await cursor.fetchall()
                rows_list = list(rows)  # Convert to list for len()

                if rows_list:
                    # Get column names
                    column_names = [description[0] for description in cursor.description]
                    columns_str = ', '.join(column_names)

                    dump_file.write(f"INSERT INTO {table_name} ({columns_str}) VALUES\n")

                    row_count = len(rows_list)
                    for i, row in enumerate(rows_list):
                        # Escape single quotes and handle None values
                        values = []
                        for value in row:
                            if value is None:
                                values.append('NULL')
                            elif isinstance(value, str):
                                values.append(f"'{value.replace(chr(39), chr(39) + chr(39))}'")
                            else:
                                values.append(str(value))

                        values_str = ', '.join(values)
                        dump_file.write(f"({values_str})")

                        if i < row_count - 1:
                            dump_file.write(",\n")
                        else:
                            dump_file.write(";\n")

                    dump_file.write("\n")

        dump_file.close()
        logger.info("Database backup created: %s", dump_file.name)
        return dump_file.name

    except Exception as e:
        dump_file.close()
        os.unlink(dump_file.name)
        logger.exception("Failed to create database backup")
        raise


def backup_shorteners() -> str:
    """Create backup of shorteners.json file.

    Returns path to the backup file.
    """
    logger.info("Creating shorteners backup")
    backup_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)

    try:
        shorteners_path = os.path.join(settings.DATA_DIR, "shorteners.json")
        with open(shorteners_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        json.dump(data, backup_file, indent=2, ensure_ascii=False)
        backup_file.close()

        logger.info("Shorteners backup created: %s", backup_file.name)
        return backup_file.name

    except Exception as e:
        backup_file.close()
        os.unlink(backup_file.name)
        logger.exception("Failed to create shorteners backup")
        raise


def create_backup_zip(db_dump_path: str, shorteners_path: str) -> str:
    """Create ZIP file containing database dump and shorteners backup.

    Returns path to the ZIP file with timestamp naming: DD-MM-YYYY-HH-MM.zip
    """
    now = datetime.now()
    zip_filename = f"{now.day:02d}-{now.month:02d}-{now.year}-{now.hour:02d}-{now.minute:02d}.zip"
    zip_path = os.path.join(tempfile.gettempdir(), zip_filename)

    logger.info("Creating backup ZIP: %s", zip_path)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add database dump
            zipf.write(db_dump_path, arcname='database_backup.sql')
            # Add shorteners backup
            zipf.write(shorteners_path, arcname='shorteners_backup.json')
            # Add metadata
            metadata = {
                'created_at': now.isoformat(),
                'version': '1.0',
                'description': 'Zoom-Telebot backup containing database and shorteners configuration'
            }
            zipf.writestr('backup_info.json', json.dumps(metadata, indent=2))

        logger.info("Backup ZIP created successfully: %s", zip_path)
        return zip_path

    except Exception as e:
        if os.path.exists(zip_path):
            os.unlink(zip_path)
        logger.exception("Failed to create backup ZIP")
        raise


async def restore_database(sql_dump_path: str) -> Dict[str, int]:
    """Restore database from SQL dump file.

    Returns statistics about restored data.
    """
    logger.info("Restoring database from: %s", sql_dump_path)

    stats = {'tables_created': 0, 'rows_inserted': 0}

    try:
        # Read SQL dump
        with open(sql_dump_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # Split into individual statements (basic approach)
        statements = []
        current_statement = ""
        in_string = False
        string_char = None

        for char in sql_content:
            if not in_string:
                if char in ("'", '"'):
                    in_string = True
                    string_char = char
                elif char == ';':
                    if current_statement.strip():
                        statements.append(current_statement.strip())
                    current_statement = ""
                    continue
            else:
                if char == string_char and (not current_statement or current_statement[-1] != '\\'):
                    in_string = False
                    string_char = None

            current_statement += char

        # Execute statements
        async with aiosqlite.connect(settings.db_path) as db:
            for statement in statements:
                if statement.strip() and not statement.strip().startswith('--'):
                    try:
                        await db.execute(statement)
                        if statement.upper().startswith('CREATE TABLE'):
                            stats['tables_created'] += 1
                        elif statement.upper().startswith('INSERT'):
                            stats['rows_inserted'] += 1
                    except Exception as e:
                        logger.warning("Failed to execute statement: %s - %s", statement[:100], e)

            await db.commit()

        logger.info("Database restore completed: %s", stats)
        return stats

    except Exception as e:
        logger.exception("Failed to restore database")
        raise


def restore_shorteners(backup_path: str) -> bool:
    """Restore shorteners.json from backup file.

    Returns True if successful.
    """
    logger.info("Restoring shorteners from: %s", backup_path)

    try:
        with open(backup_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate JSON structure
        if 'providers' not in data:
            raise ValueError("Invalid shorteners backup: missing 'providers' key")

        shorteners_path = os.path.join(settings.DATA_DIR, "shorteners.json")
        backup_path_current = shorteners_path + '.backup'

        # Backup current file
        if os.path.exists(shorteners_path):
            shutil.copy2(shorteners_path, backup_path_current)

        # Write new file
        with open(shorteners_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("Shorteners restore completed successfully")
        return True

    except Exception as e:
        logger.exception("Failed to restore shorteners")
        # Restore backup if it exists
        backup_path_current = os.path.join(settings.DATA_DIR, "shorteners.json.backup")
        if os.path.exists(backup_path_current):
            shutil.move(backup_path_current, os.path.join(settings.DATA_DIR, "shorteners.json"))
        raise


def extract_backup_zip(zip_path: str, extract_to: Optional[str] = None) -> Dict[str, str]:
    """Extract backup ZIP file.

    Returns dict with paths to extracted files.
    """
    if extract_to is None:
        extract_to = tempfile.mkdtemp()

    logger.info("Extracting backup ZIP: %s to %s", zip_path, extract_to)

    extracted_files = {}

    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(extract_to)

            for filename in zipf.namelist():
                extracted_files[filename] = os.path.join(extract_to, filename)

        logger.info("Backup ZIP extracted successfully: %s", extracted_files)
        return extracted_files

    except Exception as e:
        logger.exception("Failed to extract backup ZIP")
        raise
