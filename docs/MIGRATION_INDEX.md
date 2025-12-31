# Migration Documentation Index

**Status:** ✅ Complete and Production-Ready  
**Version:** v2025.12.31.6  
**Last Updated:** December 31, 2025 20:15 WIB

## Quick Navigation

### 🎯 For New Developers
Start here to understand the database migrations:

1. **[docs/DATABASE_MIGRATIONS.md](../docs/DATABASE_MIGRATIONS.md)** ← BEGIN HERE
   - Complete guide with examples
   - Configuration reference
   - Troubleshooting guide
   - Best practices

### 🔧 For DevOps/Deployment
Database configuration and setup:

1. **[config/config.py](../config/config.py)** - Settings & Configuration
   - Database URL configuration
   - Environment variables (DB_PATH, DATABASE_URL)
   - Default values

2. **[db/schema.sql](../db/schema.sql)** - Schema Reference
   - Production SQL schema
   - Clean definitions for reference
   - Index definitions

### 💻 For Developers
Implementation details:

1. **[db/db.py](../db/db.py)** - Migration Implementation
   - `run_migrations()` function (line 98+)
   - `init_db()` initialization (line 143+)
   - Migration 1 & 2 code

2. **[bot/main.py](../bot/main.py)** - Bot Initialization
   - Database initialization call (line 99)
   - Startup flow

### 📚 For System Architects
Overall system documentation:

1. **[context.md](../context.md)** - AI Context Reference
   - Search for: "Complete Database Migration Documentation"
   - Database schema overview
   - Migration status

## Migration Summary

### Current Schema Version
**v2.0** with Cloud Recording Support

### Applied Migrations

| # | Date | Column | Table | Type | Status |
|---|------|--------|-------|------|--------|
| 1 | Dec 2025 | `agent_id` | `meeting_live_status` | ALTER | ✅ Applied |
| 2 | Dec 31, 2025 | `cloud_recording_data` | `meetings` | ALTER | ✅ Applied |

### Tables (7 total)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `users` | Telegram users & access control | telegram_id, username, role, status |
| `meetings` | Zoom meetings | zoom_meeting_id, topic, **cloud_recording_data** |
| `meeting_live_status` | Meeting status tracking | zoom_meeting_id, **agent_id**, recording_status |
| `shortlinks` | URL shortener results | original_url, short_url, provider |
| `agents` | C2 agents for remote control | name, base_url, api_key |
| `agent_commands` | Command queue | agent_id, action, status |
| `fsm_states` | Telegram FSM persistence | user_id, state, data |

## Configuration Files

### Environment Variables

```bash
# Database path (highest priority)
export DB_PATH="./zoom_telebot.db"

# Or full database URL
export DATABASE_URL="sqlite+aiosqlite:///./zoom_telebot.db"
```

### Loading in Code

```python
from config import settings
db_path = settings.db_path  # Auto-loaded from env
```

## Migration Execution Flow

```
Bot Startup (bot/main.py:99)
    ↓
await init_db() (db/db.py:143)
    ├─ CREATE TABLE IF NOT EXISTS for all 7 tables
    │  (from CREATE_SQL array)
    ├─ CREATE INDEXes (11 total)
    ↓
await run_migrations(db) (db/db.py:98)
    ├─ Migration 1: Check & add agent_id column
    │  └─ await db.commit()
    ├─ Migration 2: Check & add cloud_recording_data column
    │  └─ await db.commit()
    ↓
await db.commit() (final commit)
    ↓
Database Ready ✅
```

## File Reference

| File | Size | Purpose |
|------|------|---------|
| docs/DATABASE_MIGRATIONS.md | 11.85 KB | 📖 Comprehensive guide (700+ lines) |
| db/schema.sql | 8.31 KB | 🗄️ Production schema definition |
| config/config.py | 3.91 KB | ⚙️ Settings & configuration |
| context.md | 74.11 KB | 📝 AI context reference |
| db/db.py | — | 💻 Migration implementation |
| bot/main.py | — | 🚀 Bot initialization |

## Verification Checklist

Run this to verify your migration setup:

```python
import sqlite3
from config import settings

# 1. Check config
print(f"Database path: {settings.db_path}")

# 2. Check database exists
import os
if os.path.exists(settings.db_path):
    print("✅ Database file exists")
else:
    print("❌ Database file missing - will be created on startup")

# 3. Check schema
conn = sqlite3.connect(settings.db_path)
cursor = conn.cursor()

# Check tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [t[0] for t in cursor.fetchall()]
print(f"✅ Tables ({len(tables)}): {tables}")

# Check migrations
cursor.execute("PRAGMA table_info(meeting_live_status)")
if any(c[1] == 'agent_id' for c in cursor.fetchall()):
    print("✅ Migration 1: agent_id column present")
else:
    print("❌ Migration 1: agent_id column missing")

cursor.execute("PRAGMA table_info(meetings)")
if any(c[1] == 'cloud_recording_data' for c in cursor.fetchall()):
    print("✅ Migration 2: cloud_recording_data column present")
else:
    print("❌ Migration 2: cloud_recording_data column missing")

conn.close()
```

## Adding New Migrations

See [docs/DATABASE_MIGRATIONS.md](../docs/DATABASE_MIGRATIONS.md) section: "Adding New Migrations"

## Troubleshooting

### Issue: "no such column" error
**Solution:** See [docs/DATABASE_MIGRATIONS.md](../docs/DATABASE_MIGRATIONS.md) → Troubleshooting → "no such column" error

### Issue: Migration failed
**Solution:** See [docs/DATABASE_MIGRATIONS.md](../docs/DATABASE_MIGRATIONS.md) → Troubleshooting → "Migration failed"

### Issue: Database locked
**Solution:** See [docs/DATABASE_MIGRATIONS.md](../docs/DATABASE_MIGRATIONS.md) → Troubleshooting → "SQLite locked"

## Backup & Restore

For backup procedures, see:
[docs/DATABASE_MIGRATIONS.md](../docs/DATABASE_MIGRATIONS.md) → "Best Practices" → "Backup Strategies"

## Support

For detailed information, always refer to:
**[docs/DATABASE_MIGRATIONS.md](../docs/DATABASE_MIGRATIONS.md)** ← Primary Reference

---

**Last Review:** December 31, 2025 20:15 WIB  
**Status:** ✅ Production Ready
