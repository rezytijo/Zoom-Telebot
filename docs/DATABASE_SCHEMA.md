# Database Schema - Recording Status Tracking

## Overview

The database schema already includes support for recording status tracking via the `meeting_live_status` table.

## Database Tables

### 1. `meeting_live_status` (Recording Status Table)

Stores real-time meeting status and recording information:

```sql
CREATE TABLE IF NOT EXISTS meeting_live_status (
    zoom_meeting_id TEXT PRIMARY KEY,
    live_status TEXT DEFAULT 'not_started',        -- not_started, started, ended
    recording_status TEXT DEFAULT 'stopped',        -- stopped, recording, paused
    recording_started_at TIMESTAMP,                 -- first time recording was started
    agent_id INTEGER,                               -- agent used for this meeting
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Columns:**
- `zoom_meeting_id`: Meeting ID (primary key, links to meetings.zoom_meeting_id)
- `live_status`: Current meeting status
  - `not_started` - Meeting hasn't started yet
  - `started` - Meeting is live
  - `ended` - Meeting has ended
- `recording_status`: **[NEW v2.3.0]** Current recording status
  - `stopped` - Recording is not active
  - `recording` - Recording is currently active
  - `paused` - Recording is paused
- `recording_started_at`: Timestamp of when recording was first started
- `agent_id`: Optional agent ID associated with this meeting
- `updated_at`: Last update timestamp

## Automatic Schema Updates

The bot automatically creates and updates the database schema on startup:

1. **Initial Creation**: If the database doesn't exist, all tables are created
2. **Migrations**: Existing databases are updated with new columns via `run_migrations()` function
3. **No Data Loss**: All migrations use `ALTER TABLE` to add new columns, preserving existing data

## Recording Status Tracking (v2.3.0)

### How It Works

Since Zoom API doesn't provide real-time recording status:
- Status is tracked **exclusively in the database**
- Updated when user clicks recording control buttons
- Survives bot restarts (persisted in database)

### Status Lifecycle

1. **User clicks Start Recording**
   - Bot sends BOTH `start` + `resume` payloads to Zoom API
   - Database updates: `recording_status = 'recording'`
   - UI refreshes after 1.5s delay

2. **User clicks Pause Recording**
   - Bot sends `pause` payload to Zoom API
   - Database updates: `recording_status = 'paused'`
   - UI refreshes immediately

3. **User clicks Resume Recording**
   - Bot sends `resume` payload to Zoom API
   - Database updates: `recording_status = 'recording'`
   - UI refreshes immediately

4. **User clicks Stop Recording**
   - Bot sends `stop` payload to Zoom API
   - Database updates: `recording_status = 'stopped'`
   - UI refreshes immediately

## Functions

Located in `db/db.py`:

```python
# Update recording status
async def update_meeting_recording_status(zoom_meeting_id: str, recording_status: str, agent_id: Optional[int] = None)

# Get current recording status
async def get_meeting_recording_status(zoom_meeting_id: str) -> Optional[str]

# Get meeting live status
async def get_meeting_live_status(zoom_meeting_id: str) -> Optional[str]

# Update meeting live status
async def update_meeting_live_status(zoom_meeting_id: str, live_status: str, agent_id: Optional[int] = None)
```

## Database File Location

- **Development**: `bot.db` (in project root)
- **Docker**: `/app/bot.db` (inside container)
- **Custom**: Set via `DB_PATH` environment variable or `DATABASE_URL`

## Backup & Recovery

The database is backed up in `.zip` files via `/backup` command and can be restored via `/restore` command. This includes all recording status history.

## Migration from Earlier Versions

If you're upgrading from v2.2.0 or earlier:

1. **No action needed** - The bot will automatically migrate the database on startup
2. **Existing meetings** - Recording status will default to `'stopped'`
3. **Future actions** - Status will be updated correctly when buttons are clicked

No data loss occurs during migration.
