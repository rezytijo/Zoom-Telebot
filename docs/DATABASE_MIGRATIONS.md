# Database Migrations Guide

**Last Updated:** December 31, 2025  
**Current Schema Version:** v2.0 (Cloud Recording Support)

## Overview

This document describes all database migrations applied to the Zoom Telebot database. Migrations are automatically applied on bot startup via `init_db()` in [db/db.py](../db/db.py).

## Database Location

**Config Key:** `DB_PATH` (in `config/config.py`)  
**Default Value:** `./zoom_telebot.db` (SQLite)  
**Environment Variable:** `DATABASE_URL` or `DB_PATH`

```python
# From config/config.py
db_path: str = _db_path_from_database_url(os.getenv("DATABASE_URL"))
```

## Current Database Schema

### Tables (7 total)

#### 1. users
```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    status TEXT DEFAULT 'pending',      -- pending, whitelisted, banned
    role TEXT DEFAULT 'guest'           -- guest, user, admin, owner
)
```
**Purpose:** Store Telegram user information and access control  
**Indexes:** UNIQUE on telegram_id

#### 2. meetings ⭐ (Latest: v2.0 - Cloud Recording Support)
```sql
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zoom_meeting_id TEXT UNIQUE,
    topic TEXT,
    start_time TEXT,
    join_url TEXT,
    status TEXT DEFAULT 'active',       -- active, deleted, expired
    created_by TEXT,                    -- telegram_id or "CreatedFromZoomApp"
    cloud_recording_data TEXT,          -- ✨ NEW v2.0: JSON blob with recording info
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose:** Store Zoom meetings with cloud recording metadata  
**Indexes:** UNIQUE on zoom_meeting_id  
**Latest Addition (v2.0):** `cloud_recording_data` column for caching recording URLs

#### 3. meeting_live_status ⭐ (Latest: v1.1 - Agent Support)
```sql
CREATE TABLE IF NOT EXISTS meeting_live_status (
    zoom_meeting_id TEXT PRIMARY KEY,
    live_status TEXT DEFAULT 'not_started',     -- not_started, started, ended
    recording_status TEXT DEFAULT 'stopped',    -- stopped, recording, paused
    recording_started_at TIMESTAMP,
    agent_id INTEGER,                           -- ✨ NEW v1.1: Agent used for meeting
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose:** Track live meeting and recording status  
**Latest Addition (v1.1):** `agent_id` column for agent-based recording control

#### 4. shortlinks
```sql
CREATE TABLE IF NOT EXISTS shortlinks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_url TEXT NOT NULL,
    short_url TEXT,
    provider TEXT NOT NULL,             -- tinyurl, bitly, s.id, etc.
    custom_alias TEXT,
    zoom_meeting_id TEXT,
    status TEXT DEFAULT 'active',       -- active, failed, deleted
    created_by INTEGER,                 -- telegram_id
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT
)
```
**Purpose:** Store URL shortener results for meetings

#### 5. agents
```sql
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key TEXT,
    os_type TEXT,
    last_seen TIMESTAMP,
    hostname TEXT,
    ip_address TEXT,
    version TEXT DEFAULT 'v1.0'
)
```
**Purpose:** Store C2 agent information for remote meeting control

#### 6. agent_commands
```sql
CREATE TABLE IF NOT EXISTS agent_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    payload TEXT,
    status TEXT DEFAULT 'pending',      -- pending, running, done, failed
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose:** Queue commands for agents to execute

#### 7. fsm_states
```sql
CREATE TABLE IF NOT EXISTS fsm_states (
    user_id INTEGER PRIMARY KEY,
    state TEXT,
    data TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose:** Persist Telegram FSM (Finite State Machine) conversation state across restarts

---

## Migration History

### Migration 1: Add agent_id to meeting_live_status (v1.1)

**When Applied:** December 2025  
**Type:** Additive column (safe)  
**Status:** ✅ Complete

```python
# Check if column exists
cursor = await db.execute("PRAGMA table_info(meeting_live_status)")
columns = await cursor.fetchall()
column_names = [col[1] for col in columns]

# Add column if missing
if 'agent_id' not in column_names:
    await db.execute("ALTER TABLE meeting_live_status ADD COLUMN agent_id INTEGER")
    await db.commit()
```

**What Changed:**
- Added `agent_id INTEGER` column to `meeting_live_status` table
- Allows tracking which agent was used for each meeting

**Database Impact:**
- Non-destructive (only adds column)
- Existing rows: `agent_id = NULL`
- No data loss

**How to Verify:**
```bash
sqlite3 zoom_telebot.db "PRAGMA table_info(meeting_live_status);"
# Should show: agent_id | INTEGER
```

---

### Migration 2: Add cloud_recording_data to meetings (v2.0)

**When Applied:** December 31, 2025 20:09 WIB  
**Type:** Additive column (safe)  
**Status:** ✅ Complete

```python
# Check if column exists
cursor = await db.execute("PRAGMA table_info(meetings)")
columns = await cursor.fetchall()
column_names = [col[1] for col in columns]

# Add column if missing
if 'cloud_recording_data' not in column_names:
    await db.execute("ALTER TABLE meetings ADD COLUMN cloud_recording_data TEXT")
    await db.commit()
```

**What Changed:**
- Added `cloud_recording_data TEXT` column to `meetings` table
- Stores JSON blob with cloud recording information

**Column Content Structure:**
```json
{
  "share_url": "https://zoom.us/recording/play/...",
  "total_size": 512000000,
  "recording_count": 2,
  "recording_files": [
    {
      "id": "...",
      "file_type": "MP4",
      "file_size": 300000000,
      "play_url": "https://...",
      "download_url": "https://...",
      "recording_type": "shared_screen_with_speaker_video",
      "status": "completed"
    }
  ],
  "last_checked": "2025-12-31T15:30:00"
}
```

**Database Impact:**
- Non-destructive (only adds column)
- Existing rows: `cloud_recording_data = NULL`
- No data loss

**How to Verify:**
```bash
sqlite3 zoom_telebot.db "PRAGMA table_info(meetings);"
# Should show: cloud_recording_data | TEXT
```

---

## Migration Application Flow

### On Fresh Database Installation

1. **init_db()** creates all tables from CREATE_SQL array
2. Cloud recording support included in CREATE TABLE statement
3. Migrations checked and skipped (columns already exist)
4. Database ready for use

### On Existing Database

1. **init_db()** runs CREATE TABLE IF NOT EXISTS (no-op for existing tables)
2. **run_migrations()** called:
   - Migration 1: Check agent_id column, add if missing
   - Migration 2: Check cloud_recording_data column, add if missing
3. Each migration commits independently
4. Database schema upgraded safely

### Automatic Execution

```python
# From db/db.py - init_db()
async def init_db():
    logger.info("Initializing database at %s", settings.db_path)
    async with aiosqlite.connect(settings.db_path) as db:
        for s in CREATE_SQL:
            await db.execute(s)
        
        # Run migrations
        await run_migrations(db)
        
        await db.commit()
    logger.info("Database initialized")
```

**Called On:**
- Bot startup via `bot/main.py` line 99
- Development scripts that import db module

---

## Configuration

### Database Path Configuration

**File:** `config/config.py`

```python
@dataclass
class Settings:
    # Database
    database_url: str | None = os.getenv("DATABASE_URL")
    db_path: str = _db_path_from_database_url(os.getenv("DATABASE_URL"))
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | Not set | Full database URL (sqlite format) |
| `DB_PATH` | `./zoom_telebot.db` | SQLite file path (fallback) |

### Examples

```bash
# Use default SQLite
export DB_PATH="./zoom_telebot.db"

# Or use full URL
export DATABASE_URL="sqlite+aiosqlite:///./zoom_telebot.db"

# Or use absolute path
export DATABASE_URL="sqlite+aiosqlite:////tmp/zoom_telebot.db"
```

---

## Troubleshooting

### Issue: "no such column" error

**Cause:** Migration didn't run or didn't commit

**Solution:**
1. Delete old database: `rm zoom_telebot.db`
2. Restart bot: `python run.py`
3. Fresh database created with all columns

### Issue: Migration failed

**Check logs:**
```bash
python run.py --log-level DEBUG 2>&1 | grep -i migration
```

**Common Causes:**
- Column already exists (safe, will skip)
- SQLite locked by another process
- Permission denied on database file

### Issue: Database file not found

**Check config:**
```bash
python -c "from config import settings; print(settings.db_path)"
```

**Ensure directory exists:**
```bash
mkdir -p $(dirname $(python -c "from config import settings; print(settings.db_path)"))
```

---

## Best Practices

### Before Production Deployment

1. **Backup existing database:**
   ```bash
   cp zoom_telebot.db zoom_telebot.db.backup
   ```

2. **Test migrations on staging:**
   ```bash
   # Copy to staging environment
   # Run bot with test data
   python run.py --log-level DEBUG
   ```

3. **Verify schema after upgrade:**
   ```bash
   python test_db_schema.py
   ```

### Backup Strategies

**Automatic backup on startup:**
```python
import shutil
from config import settings
from datetime import datetime

# Before init_db()
backup_path = f"{settings.db_path}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.backup"
shutil.copy(settings.db_path, backup_path)
```

### Monitoring Migrations

**Check migration status in logs:**
```
2025-12-31 12:08:57 - db.db - INFO - Initializing database at ./zoom_telebot.db
2025-12-31 12:08:57 - db.db - INFO - Running database migrations
2025-12-31 12:08:57 - db.db - DEBUG - Migration 1 skipped: agent_id column already exists
2025-12-31 12:08:57 - db.db - DEBUG - Migration 2 skipped: cloud_recording_data column already exists
2025-12-31 12:08:57 - db.db - INFO - Database migrations completed
2025-12-31 12:08:57 - db.db - INFO - Database initialized
```

---

## Adding New Migrations

### How to Add a Migration

1. **Create migration function in `run_migrations()`:**

```python
# Migration 3: Add new_column to some_table (vX.X)
try:
    cursor = await db.execute("PRAGMA table_info(some_table)")
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]
    
    if 'new_column' not in column_names:
        logger.info("Adding new_column to some_table")
        await db.execute("ALTER TABLE some_table ADD COLUMN new_column TEXT")
        await db.commit()  # ← Important: commit immediately
        logger.info("Migration 3 completed: new_column added")
    else:
        logger.debug("Migration 3 skipped: new_column already exists")
        
except Exception as e:
    logger.error("Migration 3 failed: %s", e)
    raise
```

2. **Update CREATE_SQL to include new column in fresh installs**
3. **Update this documentation**
4. **Test on staging database**
5. **Backup production database before deploying**

---

## Related Files

- **Database Layer:** [db/db.py](../db/db.py)
- **Database Package:** [db/__init__.py](../db/__init__.py)
- **Configuration:** [config/config.py](../config/config.py)
- **Schema Backup:** [db/schema.sql](../db/schema.sql)
- **Bot Initialization:** [bot/main.py](../bot/main.py) (line 99)
- **Background Tasks:** [bot/background_tasks.py](../bot/background_tasks.py)

---

**Last Review:** December 31, 2025 20:09 WIB  
**Status:** ✅ All migrations tested and verified
