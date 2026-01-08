# Database Migration Guide

## Quick Fix untuk Error "no such column: cloud_recording_data"

Error ini terjadi karena database production tidak memiliki kolom terbaru yang diperlukan oleh kode.

### Solusi 1: Jalankan Migration Script (Recommended)

**Di dalam Docker container:**
```bash
docker exec -it <container_name> python scripts/run_migration.py
```

**Di local development:**
```bash
python scripts/run_migration.py
```

**Kemudian restart bot:**
```bash
docker restart <container_name>
# atau jika manual:
# systemctl restart zoom-telebot
```

---

### Solusi 2: Restart Bot (Auto-Migration)

Bot akan otomatis menjalankan migration saat startup jika `init_db()` dipanggil.

```bash
docker restart <container_name>
```

Migration akan dijalankan otomatis dan log akan menampilkan:
```
Running database migrations
Adding cloud_recording_data column to meetings table
Migration 2 completed: cloud_recording_data column added
```

---

### Solusi 3: Manual Migration via SQL

Jika kedua cara di atas tidak bekerja, jalankan SQL manual:

**Masuk ke database:**
```bash
docker exec -it <container_name> sqlite3 /app/zoom_telebot.db
```

**Jalankan SQL:**
```sql
-- Check if column exists
PRAGMA table_info(meetings);

-- Add column if missing
ALTER TABLE meetings ADD COLUMN cloud_recording_data TEXT;

-- Verify
PRAGMA table_info(meetings);

-- Exit
.quit
```

**Restart bot:**
```bash
docker restart <container_name>
```

---

## Migration Details

### Migration 1: Add agent_id to meeting_live_status
- **Date:** December 2025
- **Status:** Applied
- **Type:** Additive (safe)
- **Changes:** Adds `agent_id INTEGER` column to track which agent controls each meeting

### Migration 2: Add cloud_recording_data to meetings
- **Date:** December 31, 2025
- **Status:** Applied
- **Type:** Additive (safe)
- **Changes:** Adds `cloud_recording_data TEXT` column to cache Zoom cloud recording metadata
- **Format:** JSON blob with structure:
  ```json
  {
    "share_url": "https://zoom.us/rec/share/...",
    "recording_files": [...],
    "total_size": 1234567,
    "recording_count": 2,
    "last_checked": "2025-12-31T20:00:00Z"
  }
  ```

---

## Verification

After migration, verify the schema:

```bash
docker exec -it <container_name> python -c "
import asyncio
import aiosqlite
from config import settings

async def check():
    async with aiosqlite.connect(settings.db_path) as db:
        cur = await db.execute('PRAGMA table_info(meetings)')
        cols = await cur.fetchall()
        print('Meetings table columns:')
        for col in cols:
            print(f'  - {col[1]} ({col[2]})')
        
        # Check if cloud_recording_data exists
        col_names = [col[1] for col in cols]
        if 'cloud_recording_data' in col_names:
            print('\n✅ cloud_recording_data column exists!')
        else:
            print('\n❌ cloud_recording_data column MISSING!')

asyncio.run(check())
"
```

Expected output:
```
Meetings table columns:
  - id (INTEGER)
  - zoom_meeting_id (TEXT)
  - topic (TEXT)
  - start_time (TEXT)
  - join_url (TEXT)
  - status (TEXT)
  - created_by (TEXT)
  - cloud_recording_data (TEXT)  ← Should be present
  - created_at (TIMESTAMP)
  - updated_at (TIMESTAMP)

✅ cloud_recording_data column exists!
```

---

## Troubleshooting

### Error: "database is locked"
- Stop the bot before running migration
- Ensure no other processes are accessing the database

### Error: "no such table: meetings"
- Database might be corrupted or not initialized
- Run `python scripts/setup.py` to reinitialize

### Migration appears successful but error persists
1. Verify bot restarted after migration
2. Check bot is using correct database file path
3. Verify environment variable `DATABASE_URL` or `DB_PATH`

---

## Future Migrations

To add new migrations, edit `db/db.py` function `run_migrations()`:

```python
async def run_migrations(db):
    # Migration 3: Add new column
    try:
        cursor = await db.execute("PRAGMA table_info(table_name)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'new_column' not in column_names:
            logger.info("Adding new_column to table_name")
            await db.execute("ALTER TABLE table_name ADD COLUMN new_column TEXT")
            await db.commit()
            logger.info("Migration 3 completed")
        else:
            logger.debug("Migration 3 skipped: column exists")
    except Exception as e:
        logger.error("Migration 3 failed: %s", e)
        raise
```

All migrations are **idempotent** - safe to run multiple times.
