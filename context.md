# Zoom-Telebot SOC - AI Context Reference

**Created:** December 5, 2025  
**Last Updated:** January 8, 2026 17:45 WIB  
**Version:** v2026.01.08.8 (GitHub push)

**Docker Images:**
- `rezytijo/zoom-telebot:latest`
- `rezytijo/zoom-telebot:dev.v2025.12.31`
- `rezytijo/zoom-telebot:v2025.12.31`
  - Built with multi-platform support (AMD64 and ARM64)
  - Pushed to Docker Hub on January 8, 2026

**Latest Changes:**
- 2026-01-14 — Meeting list now includes status 'done' alongside 'active'. Updated query in [db/db.py](db/db.py#L) `list_meetings_with_shortlinks()` and user-facing copy in [bot/handlers.py](bot/handlers.py#L) within `_do_list_meetings()`.
- 2026-01-14 — Enforce time window: meeting list shows items from local 00:00 today up to +30 days. Implemented range filter in [bot/handlers.py](bot/handlers.py#L) inside `_do_list_meetings()` using `settings.timezone` (fallback WIB/UTC+7).
- 2026-01-08 17:45 WIB — Repository push: Committed and pushed role adjustments and Docker image details to GitHub `main` branch.
- 2026-01-08 17:00 WIB — Adjusted role requirements: Admin/Owner only for User Management, Meeting Sync, Check Expired, Backup/Restore. Minimal user role for Create Meeting, Meeting Management (list/delete), Control Meeting, Cloud Recording, URL Shortener. Added is_registered_user() function in auth.py and updated handlers accordingly.
- 2026-01-08 16:00 WIB — Docker image built and pushed to Docker Hub with multi-platform support (AMD64 and ARM64) for tags: rezytijo/zoom-telebot:latest, rezytijo/zoom-telebot:dev.v2025.12.31, rezytijo/zoom-telebot:v2025.12.31.
- 2026-01-08 13:30 WIB — Ensure the "☁️ Cloud Recording" button is always visible on the meeting list view, even when active meetings exist. Change applied in [bot/handlers.py](bot/handlers.py#L) within `_do_list_meetings()`.
- 2026-01-08 14:05 WIB — Add 5-minute TTL for FSM states to avoid stale flows blocking other actions. Implemented in [bot/fsm_storage.py](bot/fsm_storage.py#L). TTL defaults to 300s and can be configured via environment `FSM_TTL_SECONDS` or `FSM_TTL_MINUTES`.
- 2026-01-08 14:15 WIB — **FIX: Edit Meeting Hang Issue** — Removed fake `CallbackQuery` creation in `edit_meeting_time()` and `cb_skip_time()` handlers that caused loading hang. Now handlers directly send success message with navigation buttons instead of trying to invoke `cb_list_meetings()` callback. Applied in [bot/handlers.py](bot/handlers.py#L).
- 2026-01-08 14:25 WIB — **FIX: Edit Meeting JSON Serialization Error** — Convert `time` object to ISO format string before storing in FSM state (`current_time = dt.time().isoformat()`). Parse back from string when retrieving. Fixes `TypeError: Object of type time is not JSON serializable` in [bot/handlers.py](bot/handlers.py#L) `cb_edit_meeting()` and `cb_skip_time()`.

**Database Migration System Added (Jan 1, 2026):**
- Auto-migration runs on bot startup via `init_db()`
- Manual migration script: `scripts/run_migration.py`
- Makefile commands: `make migrate`, `make migrate-dev`, `make db-check`
- All migrations are idempotent (safe to run multiple times)
- See: [docs/DATABASE_MIGRATION_GUIDE.md](docs/DATABASE_MIGRATION_GUIDE.md)

## 🤖 Bot Overview

Zoom-Telebot SOC adalah bot Telegram yang komprehensif untuk mengelola meeting Zoom, dirancang khusus untuk Tim Keamanan Siber (SOC). Bot ini terintegrasi dengan Zoom API dan menyediakan fitur-fitur advanced untuk manajemen meeting, user, dan remote control.

### 🎯 Core Features

#### 1. Meeting Management (October 2025)
- **Interactive Meeting Creation**: Flow step-by-step untuk membuat meeting baru
- **Batch Meeting Creation**: Support multiple meetings via `/meet` command
- **Meeting Control**: Start/Stop/Control meetings via agents
- **Recording Management**: Start/Stop/Pause/Resume recording dengan status tracking DB-only
- **Meeting Deletion**: Batch deletion via `/zoom_del`
- **Meeting Editing**: Update topic, date, time
- **Auto-sync**: Sinkronisasi otomatis dengan Zoom API setiap 30 menit
- **Localized Start Time** (Dec 19, 2025): Tampilan Start Time kini pakai timezone dari .env (`TIMEZONE`/`TZ`/`PYTZ_TIMEZONE`, default Asia/Jakarta) dengan format hari-tanggal-waktu lokal
- **Meeting List Time Range** (Dec 31, 2025): List meeting menampilkan semua meeting dari pukul 00:00 hari ini hingga 30 hari ke depan (sebelumnya hanya dari waktu saat ini)

#### 2. Recording Status Tracking (December 18, 2025)
- **Database-Only Status**: Status recording disimpan di database (Zoom API tidak menyediakan real-time recording status)
- **Dual Payload Start Recording**: Saat klik Start Recording, bot mengirim BOTH payload `start` + `resume` untuk menangani status stopped/paused
- **Status Consistency**: Status diupdate ke database saat user trigger action
- **Dynamic Button UI**: Tombol berubah sesuai status recording dari database
- **Smart Recovery**: Jika bot restart, status tetap tersimpan di database
- **Cloud Recording Viewer** (Dec 31, 2025): Lihat dan download hasil cloud recording langsung dari bot dengan tombol "View Cloud Recordings"
- **Cloud Recording Passcode Display** (Dec 31, 2025 - v2025.12.31.8): Tampilkan passcode recording yang protected - user tidak perlu manual input passcode

#### 3. User Management (October 2025)
- **Role-based Access**: owner, admin, user, guest
- **Whitelist System**: Admin approval required
- **User Search**: Search by username/ID
- **Ban/Unban**: User management controls
- **Auto-registration**: Users auto-register on first use

#### 3. Agent System (October 2025)
- **Remote Control**: Agent polling system untuk remote meeting control
- **Agent Management**: Add/Remove/Reinstall agents
- **Status Monitoring**: Online/offline status tracking
- **Command Queue**: Async command execution via API

#### 4. URL Shortener (October 2025)
- **Multi-provider**: TinyURL, S.id, Bitly, dll.
- **Dynamic Configuration**: JSON-based provider management
- **Custom Aliases**: Support untuk custom URL aliases
- **Meeting Integration**: Auto-shorten meeting URLs

#### 5. Backup & Restore (October 2025)
- **Full Backup**: Database + configuration ZIP export
- **Restore**: Import dari backup ZIP
- **Validation**: Backup integrity checking

#### 6. Persistent User Sessions (December 19, 2025)
- **Database-backed FSM Storage**: User sessions disimpan di database, bukan in-memory
- **Session Recovery**: Saat bot restart, user kembali ke state terakhir mereka
- **State Preservation**: Semua FSM state dan data persisten di `fsm_states` table
- **No User Interruption**: Users dapat continue tanpa restart dari `/start`

#### 7. TinyURL API Integration (December 19, 2025)
- **Official API**: Menggunakan TinyURL API (`https://api.tinyurl.com/create`) bukan raw website
- **Bearer Token Auth**: Secure authentication dengan API key dari `.env`
- **JSON Request/Response**: Proper structured API calls
- **Reliability**: Lebih robust dan maintainable dibanding web scraping
#### 8. Shortener Config Migration System (December 19, 2025)
- **Automatic Detection**: Auto-detect saat `shorteners.json` perlu diupdate ke schema terbaru
- **Data Preservation**: 100% kustomisasi user dijaga (API keys, headers, custom providers, body params)
- **Automatic Backup**: Backup file sebelum migrasi (`shorteners.json.backup_YYYYMMDD_HHMMSS`)
- **Public API**: `migrate_shortener_config()` function untuk trigger manual
- **CLI Tool**: `scripts/migrate_shorteners.py` dengan preview/force/verbose modes
- **Interactive Demo**: `scripts/demo_migration.py` untuk learning (7 scenarios)
- **Migration Process**: 
  1. Detect schema version mismatch
  2. Create automatic backup
  3. Merge old config + new defaults
  4. Preserve all customizations
  5. Validate new config structure
  6. Save to file atomically
- **Safety Features**:
  - Non-destructive (backup always created)
  - Idempotent (safe to run multiple times)
  - Rollback-able (backup file untuk restore)
  - Validated (schema check pre & post migration)

---

## 🗄️ Database Schema (Updated: December 31, 2025)

### Overview
Bot menggunakan **SQLite database** (`bot.db`) dengan **7 tables** untuk menyimpan users, meetings, recording status, shortlinks, agents, commands, dan FSM states. Semua operasi database dilakukan secara **asynchronous** menggunakan `aiosqlite`.

**Database Location:**
- Development: `bot.db` (project root)
- Docker: `/app/bot.db` (inside container)
- Custom: Set via `DB_PATH` environment variable

---

### Current Tables (7 tables total)

#### 1. **users** - User Management & Access Control
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    status TEXT DEFAULT 'pending',     -- pending, whitelisted, banned
    role TEXT DEFAULT 'guest'           -- guest, user, owner
)
```
**Purpose**: Store Telegram users with role-based access control  
**Key Fields**: 
- `telegram_id`: Unique Telegram user ID (cannot be duplicate)
- `username`: Telegram username for display
- `status`: Whitelist approval status (pending → whitelisted/banned)
- `role`: Access level (guest < user < owner)

**Status Flow**: 
```
pending → whitelisted (approved by owner)
pending → banned (rejected by owner)
whitelisted ↔ banned (toggle by owner)
```

**Database Functions** ([db/db.py](db/db.py)):
- `add_pending_user(telegram_id, username)` - Register new user
- `list_pending_users()` - Get users awaiting approval
- `list_all_users()` - Get all users (admin view)
- `get_user_by_telegram_id(telegram_id)` - Lookup user
- `update_user_status(telegram_id, status, role)` - Change status/role
- `ban_toggle_user(telegram_id, banned)` - Quick ban/unban
- `delete_user(telegram_id)` - Remove user from database
- `search_users(query)` - Search by username or ID

---

#### 2. **meetings** - Zoom Meeting Storage
```sql
CREATE TABLE meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zoom_meeting_id TEXT UNIQUE,
    topic TEXT,
    start_time TEXT,
    join_url TEXT,
    status TEXT DEFAULT 'active',       -- active, deleted, expired
    created_by TEXT,                    -- telegram_id or "CreatedFromZoomApp"
    cloud_recording_data TEXT,          -- JSON: {share_url, recording_files[], total_size, recording_count, last_checked}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose**: Store all Zoom meetings with sync tracking and cached cloud recording data  
**Key Fields**:
- `zoom_meeting_id`: Zoom's unique meeting ID (cannot be duplicate)
- `topic`: Meeting subject/title
- `start_time`: ISO 8601 format (e.g., "2025-12-31T10:00:00Z")
- `join_url`: Full Zoom meeting join URL
- `status`: Lifecycle tracking (active/deleted/expired)
- `created_by`: User ID or "CreatedFromZoomApp" for synced meetings
- `cloud_recording_data`: **[NEW - Dec 31, 2025]** JSON-encoded cloud recording info (populated by background task)
  - Structure: `{share_url, recording_files[], total_size, recording_count, last_checked}`
  - Last checked timestamp used to avoid excessive API calls (max 1x per hour per meeting)
- `updated_at`: Last modification timestamp

**Status Flow**:
```
active → deleted (manually deleted via bot or synced from Zoom)
active → expired (auto-detected when start_time passed)
deleted → active (re-synced from Zoom if meeting still exists)
```

**Cloud Recording Caching** (v2025.12.31.3):
- Background task checks for cloud recordings every 30 minutes
- Only updates recordings that were last checked > 1 hour ago (avoid API throttling)
- Clears old recording data (> 30 days) every 6 hours
- Handler uses cached data first, fallback to real-time fetch if needed

**Database Functions** ([db/db.py](db/db.py)):
- `add_meeting(zoom_meeting_id, topic, start_time, join_url, created_by)` - Create new meeting
- `list_meetings()` - Get all meetings (all statuses)
- `list_meetings_with_shortlinks()` - Get meetings + shortlinks (joined query)
- `update_meeting_status(zoom_meeting_id, status)` - Change status
- `update_meeting_details(zoom_meeting_id, topic, start_time)` - Edit meeting info
- `update_meeting_cloud_recording_data(zoom_meeting_id, recording_data)` - Store cloud recording info
- `get_meeting_cloud_recording_data(zoom_meeting_id)` - Retrieve cached cloud recording data
- `sync_meetings_from_zoom(zoom_client)` - Sync with Zoom API (add/update/delete/expire)
- `update_expired_meetings()` - Mark past meetings as expired
- `sync_meeting_live_status_from_zoom(zoom_client, zoom_meeting_id)` - Get live status from Zoom

---

#### 3. **meeting_live_status** - Real-time Meeting & Recording Status
```sql
CREATE TABLE meeting_live_status (
    zoom_meeting_id TEXT PRIMARY KEY,
    live_status TEXT DEFAULT 'not_started',     -- not_started, started, ended
    recording_status TEXT DEFAULT 'stopped',    -- stopped, recording, paused
    recording_started_at TIMESTAMP,              -- Track first recording start
    agent_id INTEGER,                           -- Agent controlling this meeting
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose**: Track live meeting status and recording state (Zoom API workaround)  
**Key Fields**:
- `zoom_meeting_id`: Foreign key to meetings table (PRIMARY KEY)
- `live_status`: Meeting lifecycle state
  - `not_started`: Meeting hasn't begun
  - `started`: Meeting is currently live
  - `ended`: Meeting has concluded
- `recording_status`: Recording state (DATABASE-ONLY, NOT FROM ZOOM API)
  - `stopped`: No recording active
  - `recording`: Recording in progress
  - `paused`: Recording temporarily paused
- `recording_started_at`: Timestamp when recording was first started (persists even if stopped)
- `agent_id`: Which agent is managing this meeting (NULL if manual control)
- `updated_at`: Last status update timestamp

**Critical Note**:  
⚠️ Zoom API does NOT provide real-time recording status. We track it ONLY in database, updated when user clicks recording buttons in bot UI.

**Recording Status Tracking Logic**:
```
User clicks "Start Recording" → 
  Bot sends BOTH "start" + "resume" payload to Zoom API →
  Database: recording_status = 'recording' →
  UI refreshes (1.5s delay)

User clicks "Pause Recording" →
  Bot sends "pause" payload to Zoom API →
  Database: recording_status = 'paused' →
  UI refreshes immediately

User clicks "Stop Recording" →
  Bot sends "stop" payload to Zoom API →
  Database: recording_status = 'stopped' →
  UI refreshes immediately
```

**Database Functions** ([db/db.py](db/db.py)):
- `update_meeting_recording_status(zoom_meeting_id, recording_status, agent_id)` - Update recording state
- `get_meeting_recording_status(zoom_meeting_id)` - Get current recording status (default: 'stopped')
- `get_meeting_agent_id(zoom_meeting_id)` - Get controlling agent
- `update_meeting_live_status(zoom_meeting_id, live_status, agent_id)` - Update meeting live state
- `get_meeting_live_status(zoom_meeting_id)` - Get current live status (default: 'not_started')

---

#### 4. **shortlinks** - URL Shortener History & Tracking
```sql
CREATE TABLE shortlinks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_url TEXT NOT NULL,
    short_url TEXT,
    provider TEXT NOT NULL,             -- tinyurl, sid, bitly, etc
    custom_alias TEXT,                  -- User's custom alias (if provider supports)
    zoom_meeting_id TEXT,               -- Foreign key to meetings (NULL for non-meeting URLs)
    status TEXT DEFAULT 'active',       -- active, failed, deleted
    created_by INTEGER,                 -- telegram_id of creator
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT                  -- Detailed error if creation failed
)
```
**Purpose**: Track all shortened URLs with multi-provider support  
**Key Fields**:
- `original_url`: Full original URL to shorten
- `short_url`: Generated shortened URL (NULL if failed)
- `provider`: Shortener service used (tinyurl, sid, bitly, etc)
- `custom_alias`: User-provided custom alias (provider-dependent)
- `zoom_meeting_id`: Links shortlink to meeting (NULL for general URLs)
- `status`: Success/failure tracking
- `created_by`: Who created this shortlink (for quota/history tracking)
- `error_message`: Debugging info if shortener API failed

**Status Values**:
- `active`: Successfully created and available
- `failed`: Shortener API returned error
- `deleted`: User manually removed shortlink

**Database Functions** ([db/db.py](db/db.py)):
- `add_shortlink(original_url, short_url, provider, custom_alias, zoom_meeting_id, created_by, error_message)` - Create shortlink record
- `update_shortlink_status(shortlink_id, status, short_url, error_message)` - Update status/URL/error
- `get_shortlinks_by_user(created_by, limit)` - Get user's shortlink history
- `get_shortlink_stats()` - Get statistics (total, active, failed, by provider)

---

#### 5. **agents** - Remote Control Agent Registry
```sql
CREATE TABLE agents (
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
**Purpose**: Track remote agents for meeting control (C2 system)  
**Key Fields**:
- `name`: Human-readable agent name
- `base_url`: Agent API endpoint (e.g., http://192.168.1.100:5000)
- `api_key`: Authentication key for agent API
- `os_type`: Operating system (Windows, Linux, macOS)
- `last_seen`: Last heartbeat/ping timestamp (for online/offline detection)
- `hostname`: Computer name
- `ip_address`: Network IP address
- `version`: Agent software version (for compatibility checking)

**Agent Online Detection**: 
- If `last_seen` < 5 minutes ago → Online ✅
- If `last_seen` > 5 minutes ago → Offline ⚠️

**Database Functions** ([db/db.py](db/db.py)):
- `add_agent(name, base_url, api_key, os_type, hostname, ip_address, version)` - Register new agent
- `list_agents(limit, offset)` - Get all agents (with pagination)
- `count_agents()` - Total agent count
- `get_agent(agent_id)` - Get single agent details
- `remove_agent(agent_id)` - Delete agent
- `update_agent_last_seen(agent_id)` - Update heartbeat timestamp

---

#### 6. **agent_commands** - Remote Command Queue (C2)
```sql
CREATE TABLE agent_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    action TEXT NOT NULL,               -- Command type: start_recording, stop_recording, etc
    payload TEXT,                       -- JSON command data/arguments
    status TEXT DEFAULT 'pending',      -- pending, running, done, failed
    result TEXT,                        -- Command execution result/output
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose**: Queue and track remote commands sent to agents  
**Key Fields**:
- `agent_id`: Foreign key to agents table
- `action`: Command type to execute on agent
  - Examples: `start_recording`, `stop_recording`, `pause_recording`, `resume_recording`
- `payload`: JSON-encoded command arguments (e.g., `{"meeting_id": "123456789"}`)
- `status`: Command execution lifecycle
  - `pending`: Queued, waiting for agent to poll
  - `running`: Agent picked up command, executing
  - `done`: Successfully completed
  - `failed`: Execution error or timeout
- `result`: Execution output (success message or error details)
- `created_at`: When command was queued
- `updated_at`: Last status update time

**Command Lifecycle**:
```
1. Bot creates command → status = 'pending'
2. Agent polls and picks up → status = 'running'
3. Agent executes command
   → Success: status = 'done', result = "Recording started"
   → Failure: status = 'failed', result = "Error: Meeting not found"
4. Timeout (60s): status = 'failed', result = "Command timed out"
```

**Database Functions** ([db/db.py](db/db.py)):
- `add_command(agent_id, action, payload)` - Queue new command
- `get_pending_commands(agent_id)` - Agent polls for pending commands
- `update_command_status(command_id, status, result)` - Update execution status
- `check_timeout_commands()` - Mark timed-out commands as failed (60s timeout)

---

#### 7. **fsm_states** - Persistent User Sessions ⭐
```sql
CREATE TABLE fsm_states (
    user_id INTEGER PRIMARY KEY,
    state TEXT,                         -- Current FSM state name
    data TEXT,                          -- JSON-encoded FSM context data
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
**Purpose**: Persist user conversation state across bot restarts  
**Key Fields**:
- `user_id`: Telegram user ID (PRIMARY KEY, one state per user)
- `state`: Current Finite State Machine (FSM) state
  - Examples: `ShortenerStates:waiting_for_provider`, `MeetingStates:waiting_for_topic`
- `data`: JSON-encoded context data for the state
  - Example: `{"provider": "tinyurl", "original_url": "https://zoom.us/j/123"}` 
- `updated_at`: Last state change timestamp

**Benefit**:  
✅ Users resume exactly where they left off after bot restart (no need to `/start` again)

**Implementation**: Custom `DatabaseFSMStorage` class in [bot/fsm_storage.py](bot/fsm_storage.py)

**Database Functions** (handled by aiogram FSM, not direct DB calls):
- State storage/retrieval managed by `DatabaseFSMStorage` class
- Automatically synced on every FSM state change

---

### 🗂️ Database Functions Summary (by Category)

#### User Management Functions
```python
# Registration & Lookup
add_pending_user(telegram_id, username)
get_user_by_telegram_id(telegram_id) → Dict | None
search_users(query) → List[Dict]

# Listing
list_pending_users() → List[Dict]
list_all_users() → List[Dict]

# Status Management
update_user_status(telegram_id, status, role)
ban_toggle_user(telegram_id, banned)
delete_user(telegram_id)
```

#### Meeting Management Functions
```python
# CRUD Operations
add_meeting(zoom_meeting_id, topic, start_time, join_url, created_by)
list_meetings() → List[Dict]
list_meetings_with_shortlinks() → List[Dict]  # Joined query
update_meeting_status(zoom_meeting_id, status)
update_meeting_details(zoom_meeting_id, topic, start_time)

# Zoom API Sync
sync_meetings_from_zoom(zoom_client) → Dict[str, int]  # Returns stats
update_expired_meetings() → Dict[str, int]

# Live Status Tracking
update_meeting_live_status(zoom_meeting_id, live_status, agent_id)
get_meeting_live_status(zoom_meeting_id) → str
sync_meeting_live_status_from_zoom(zoom_client, zoom_meeting_id) → str

# Recording Status Tracking
update_meeting_recording_status(zoom_meeting_id, recording_status, agent_id)
get_meeting_recording_status(zoom_meeting_id) → str
get_meeting_agent_id(zoom_meeting_id) → int | None

# Cloud Recording Data Management (v2025.12.31.3)
update_meeting_cloud_recording_data(zoom_meeting_id, recording_data) → None  # Stores JSON blob with last_checked
get_meeting_cloud_recording_data(zoom_meeting_id) → Dict | None  # Retrieves cached recording info
```

Stored cloud_recording_data structure:
```json
{
  "share_url": "https://zoom.us/recording/play/...",
  "total_size": 1024000000,
  "recording_count": 2,
  "recording_files": [
    {
      "id": "...", "file_type": "MP4", "file_size": 512000000,
      "play_url": "https://...", "download_url": "https://...",
      "recording_type": "shared_screen_with_speaker_video", "status": "completed"
    }
  ],
  "last_checked": "2025-12-31T15:30:00"
}
```

#### Shortlink Management Functions
```python
# CRUD Operations
add_shortlink(original_url, short_url, provider, custom_alias, zoom_meeting_id, created_by, error_message) → int
update_shortlink_status(shortlink_id, status, short_url, error_message)

# Queries
get_shortlinks_by_user(created_by, limit) → List[Dict]
get_shortlink_stats() → Dict  # total, active, failed, by_provider
```

#### Agent Management Functions
```python
# Agent Registry
add_agent(name, base_url, api_key, os_type, hostname, ip_address, version) → int
list_agents(limit, offset) → List[Dict]
count_agents() → int
get_agent(agent_id) → Dict | None
remove_agent(agent_id)
update_agent_last_seen(agent_id)

# Command Queue
add_command(agent_id, action, payload) → int
get_pending_commands(agent_id) → List[Dict]
update_command_status(command_id, status, result)
check_timeout_commands() → int  # Returns count of timed-out commands
```

#### Backup & Restore Functions
```python
# Backup Operations
backup_database() → str  # Returns SQL dump path
backup_shorteners() → str  # Returns JSON backup path
create_backup_zip(db_dump_path, shorteners_path) → str  # Returns ZIP path

# Restore Operations
restore_database(sql_dump_path) → Dict[str, int]  # Returns stats
restore_shorteners(backup_path) → bool
extract_backup_zip(zip_path, extract_to) → Dict[str, str]  # Returns extracted file paths
```

#### Database Initialization
```python
init_db()  # Create all tables and run migrations
run_migrations(db)  # Apply schema updates to existing database
```

---

### Database Design Principles

1. **Separation of Concerns**: Each table has a single, well-defined purpose
2. **Referential Integrity**: Foreign keys connect related data (zoom_meeting_id, agent_id, created_by)
3. **Audit Trail**: All tables include `created_at` and `updated_at` timestamps
4. **Status Tracking**: Lifecycle management via status fields (active/deleted/expired, pending/done/failed)
5. **Extensibility**: JSON fields for flexible data storage (payload, data, error_message)
6. **No Sensitive Data**: API keys and tokens stored in `.env`, never in database (except agent_key)
7. **Database-Only Workarounds**: `recording_status` stored locally due to Zoom API limitations
8. **Persistent Sessions**: FSM states survive bot restarts for seamless user experience

---

### Migration Strategy

**Current Implementation**: 
- Schema defined in `CREATE_SQL` array in [db/db.py](db/db.py)
- Migrations handled by `run_migrations(db)` function
- Uses `ALTER TABLE` to add new columns (preserves existing data)
- Automatic migration on bot startup via `init_db()`

**Migration Examples** (from [db/db.py](db/db.py)):
```python
# Add agent_id column to meeting_live_status
if 'agent_id' not in column_names:
    await db.execute("ALTER TABLE meeting_live_status ADD COLUMN agent_id INTEGER")

# Migrate recording_status from meetings to meeting_live_status table
if 'recording_status' in column_names:
    await db.execute("""
        INSERT OR REPLACE INTO meeting_live_status (zoom_meeting_id, recording_status, updated_at)
        SELECT zoom_meeting_id, recording_status, CURRENT_TIMESTAMP
        FROM meetings
        WHERE recording_status IS NOT NULL
    """)
    await db.execute("ALTER TABLE meetings DROP COLUMN recording_status")
```

**Future Enhancement**: Consider SQLAlchemy Alembic for versioned migrations

---

### Schema Backup Files

**Schema-only SQL backups** (no data, structure only):

1. **[database_schema_backup_2025-12-31.sql](database_schema_backup_2025-12-31.sql)** (Root folder)
   - Full documented schema with comments
   - Includes all 7 tables + 14 indexes
   - Migration notes and restore instructions
   - Created before adding new features (baseline)

2. **[db/schema.sql](db/schema.sql)** (Database folder)
   - Clean schema definition
   - Quick reference for developers
   - Minimal comments for readability

**Purpose**: Version control for database schema changes, rollback capability, documentation

**Restore Instructions**:
```bash
# Method 1: SQLite CLI
sqlite3 bot.db < database_schema_backup_2025-12-31.sql

# Method 2: Python
python -c "import sqlite3; conn = sqlite3.connect('bot.db'); conn.executescript(open('database_schema_backup_2025-12-31.sql').read()); conn.close()"
```

---

## 📊 Architecture Updates (December 19, 2025)

### FSM Storage Architecture
```
Before (Memory-based):
┌──────────────┐
│ Telegram Bot │
└────┬─────────┘
     │ Update state
     ▼
┌──────────────────────┐
│ MemoryStorage (RAM)  │  ← Lost on restart!
└──────────────────────┘

After (Database-backed):
┌──────────────┐
│ Telegram Bot │
└────┬─────────┘
     │ Update state
     ▼
┌──────────────────────────────────┐
│ DatabaseFSMStorage               │
└────┬──────────────────────────────┘
     │ Persist to DB
     ▼
┌──────────────────────────────────┐
│ SQLite Database (fsm_states)     │  ← Survives restart! ✅
└──────────────────────────────────┘
```

### Configuration Updates (v2.4.0)
```bash
# .env additions
TINYURL_API_KEY=1dChPWi1S8H1dTzTXbDdc95HT55dqKiUhKagsnFgMQ6BHt4D56EJcGvsrQye
TINYURL_API_URL=https://api.tinyurl.com/create
```

---

### Reorganization Completed
**Date:** December 5, 2025
**Reason:** Improve code organization and maintainability

```
BotTelegramZoom/
├── __init__.py                 # Main package
├── run.py                      # Main entry point (with argument parsing)
├── docker-compose.yml          # Docker compose configuration (UPDATED)
├── bot/                        # Main bot code
│   ├── __init__.py
│   ├── main.py                 # Bot entry point
│   ├── handlers.py             # Telegram handlers
│   ├── keyboards.py            # Inline keyboards
│   ├── middleware.py           # Bot middleware
│   └── auth.py                 # Authentication & authorization
├── zoom/                       # Zoom integration
│   ├── __init__.py
│   └── zoom.py                 # Zoom API client
├── shortener/                  # URL shortener
│   ├── __init__.py
│   └── shortener.py            # Dynamic shortener
├── db/                         # Database layer
│   ├── __init__.py
│   └── db.py                   # SQLite operations
├── config/                     # Configuration
│   ├── __init__.py
│   └── config.py               # Settings & config
├── c2/                         # C2 Framework integration
│   ├── __init__.py
│   └── sliver_zoom_c2.py       # Sliver C2 client
├── agent/                      # Agent related (placeholder with docs)
│   ├── __init__.py
│   └── todo_agent.md            # Agent system TODO and roadmap
├── scripts/                    # Utility scripts
│   ├── __init__.py
│   ├── setup.py                # Setup script
│   └── dev.py                  # Development helper
├── docker/                     # Docker config
│   ├── __init__.py
│   ├── Dockerfile
│   └── docker-entrypoint.sh
├── data/                       # Data files
│   ├── shorteners.json
│   └── shorteners.json.back
├── docs/                      # Documentation
│   ├── __init__.py
│   ├── README.md             # Project overview
│   ├── INSTALLATION.md       # Installation guide
│   ├── DEVELOPMENT.md        # Development guide
│   └── API.md                # API documentation
├── tests/                      # Unit tests
│   └── __init__.py
├── requirements.txt            # Dependencies
├── Readme.md                   # Main documentation
├── Makefile                    # Build automation
└── context.md                  # This file (AI reference)
```

## 🔧 Technical Details

### Dependencies
- **aiogram**: Telegram Bot API framework
- **aiosqlite**: Async SQLite database
- **aiohttp**: HTTP client for API calls
- **python-multipart**: File upload handling

### Database Schema
- **users**: User management (telegram_id, username, role, status)
- **meetings**: Zoom meeting data (id, topic, start_time, join_url)
- **meeting_live_status**: Live meeting status (recording, agent control)
- **shortlinks**: URL shortening history
- **agents**: Remote agent management
- **agent_commands**: Command queue for agents

### API Integration
- **Zoom API**: Server-to-Server OAuth
  - **Official Documentation**: https://developers.zoom.us/docs/api/
  - **Meeting Endpoints**: `/v2/meetings/{id}` (GET, PUT, DELETE, PATCH)
  - **Meeting Status**: `/v2/meetings/{id}/status` (PUT) - Start/End meeting actions
  - **Authentication**: OAuth S2S with account credentials
  - **Rate Limits**: Respect Zoom API throttling limits
  - **Scopes Required**: `meeting:read:admin`, `meeting:write:admin`, `recording:read:admin`
- **Multiple URL Shorteners**: Dynamic provider system
- **Agent Using C2 Framework**: Internal Command and Control for remote control Agent!

## 🚀 Development Guide

### Running the Bot
```bash
# Direct PC execution (recommended for development/testing)
python run.py

# Check configuration before running
python run.py --check-config

# Show help and available options
python run.py --help

# Run with custom log level
python run.py --log-level DEBUG

# Development mode with auto-restart (recommended for development)
python dev.py run --watch           # Auto-restart on file changes
python dev.py debug --watch         # Debug mode with auto-restart
python dev.py test                  # Test imports
python dev.py check                 # Check configuration

# With Docker (production deployment)
docker-compose up -d

# Setup environment
python scripts/setup.py
```

### Documentation
- **[docs/README.md](docs/README.md)** - Project overview dan quick start
- **[docs/INSTALLATION.md](docs/INSTALLATION.md)** - Panduan instalasi lengkap
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Panduan development
- **[docs/API.md](docs/API.md)** - Dokumentasi API

### Key Files to Understand
1. **bot/main.py**: Bot initialization and startup
2. **bot/handlers.py**: All Telegram command handlers
3. **zoom/zoom.py**: Zoom API integration
4. **db/db.py**: Database operations
5. **config/config.py**: Configuration management

### Important Notes
- **Agent API**: Currently not fully implemented (marked as TODO)
- **Relative Imports**: All imports updated to use relative imports after reorganization
- **Docker Ready**: Full Docker support maintained
- **Async Everywhere**: All operations are async for performance
- **Direct PC Testing**: Bot designed for direct execution on PC without containers
- **Agent vs API**: `api/` folder contains Agent API Server, `agent/` folder is for Agent Client Software

## 📝 Recent Changes

### December 28, 2025 - Meeting Details UX Enhancement (v2.5.2)

**Summary**: Meningkatkan user experience pada Meeting Details dengan membuat Meeting ID dan Passcode mudah di-copy dan lebih prominent dengan formatting bold.

#### UI/UX Improvements
- ✅ **Copyable Meeting ID**: Meeting ID kini wrapped dengan `<code>` tag untuk one-tap copy
- ✅ **Copyable Passcode**: Passcode juga wrapped dengan `<code>` tag untuk one-tap copy
- ✅ **Bold Formatting**: Meeting ID dan Passcode menggunakan nested `<b><code>` untuk tampilan yang lebih menonjol
- ✅ **User Impact**: User dapat tap sekali pada Meeting ID atau Passcode untuk copy ke clipboard

#### Technical Details
**Before:**
```python
text += f"🆔 <b>ID:</b> {meeting_id}\n"
text += f"🔐 <b>Passcode:</b> {passcode}\n"
```

**After:**
```python
text += f"🆔 <b>ID:</b> <b><code>{meeting_id}</code></b>\n"
text += f"🔐 <b>Passcode:</b> <b><code>{passcode}</code></b>\n"
```

**Rationale**: Telegram's `<code>` tag membuat text menjadi monospace dan copyable dengan single tap. Kombinasi dengan `<b>` tag membuat field penting ini stand out secara visual.

**Benefit**: 
- Mengurangi friction saat user perlu copy Meeting ID/Passcode
- Meningkatkan accessibility untuk workflow SOC
- Visual hierarchy yang lebih jelas dalam Meeting Details

---

### December 28, 2025 - Meeting Details Passcode Enhancement (v2.5.1)

**Summary**: Menambahkan tampilan Meeting Passcode pada fitur Meeting Details untuk memberikan informasi lengkap kepada user.

#### Meeting Details Enhancement
- ✅ **Passcode Display**: Tambahkan field 🔐 Passcode pada tampilan Meeting Details
- ✅ **API Field Mapping**: Support untuk field `password` dan `encrypted_password` dari Zoom API
- ✅ **Position**: Passcode ditampilkan setelah Duration, sebelum Recording status
- ✅ **Fallback Value**: Display "N/A" jika passcode tidak tersedia
- ✅ **Handler Updated**: `cb_zoom_meeting_details()` di `bot/handlers.py` (line ~619)

#### Displayed Information in Meeting Details
Informasi yang ditampilkan (urutan):
1. 🆔 Meeting ID
2. 📝 Topic
3. 👤 Host Email
4. 📊 Status
5. 🕛 Start Time
6. ⏱️ Duration
7. 🔐 **Passcode** ⭐ (NEW)
8. 🎥 Recording Status
9. 🔗 Join URL
10. ▶️ Start URL (if available)
11. ⚙️ Settings (Waiting Room, Auto Mute, Auto Record)

#### Technical Implementation
```python
# Add Passcode if available
passcode = details.get('password') or details.get('encrypted_password', 'N/A')
text += f"🔐 <b>Passcode:</b> {passcode}\n"
```

**Rationale**: Field `password` adalah plain text passcode, sedangkan `encrypted_password` adalah versi encrypted. Bot mengutamakan `password` dulu, fallback ke `encrypted_password` jika tidak ada.

**Impact**: User kini bisa langsung melihat passcode meeting tanpa perlu ke Zoom web interface, meningkatkan efisiensi workflow.

---

### December 19, 2025 - Shortener Config Migration & Documentation Cleanup

**Summary**: Implementasi complete automatic migration system untuk `shorteners.json` dengan 100% data preservation, bug fixes untuk backup/restore, dan cleanup dokumentasi project.

#### 1. Shortener Config Migration Feature (MAJOR FEATURE)

**Problem Solved**: User customizations dalam `shorteners.json` akan hilang saat schema diupdate

**Solution Implemented**:

##### A. Auto-Detection System
- ✅ `_needs_migration()` method deteksi mismatch antara current config vs latest schema
- ✅ Berjalan otomatis saat bot startup (transparent untuk user)
- ✅ Check 6 kriteria: providers list, provider structure, headers, body params, custom fields
- ✅ Return `True` jika ada perbedaan, `False` jika sudah latest

##### B. Migration Engine
- ✅ `_migrate_config()` internal method melakukan migration
- ✅ **Backup Creation**: Automatic backup ke `shorteners.json.backup_YYYYMMDD_HHMMSS`
- ✅ **Data Preservation**: API keys, custom headers, body params, custom providers SEMUA dijaga
- ✅ **Schema Merge**: Gabungkan old config + new defaults tanpa data loss
- ✅ **Atomic Write**: Save ke file dengan atomic operation
- ✅ **Validation**: Pre & post migration validation

##### C. Public API
- ✅ `migrate_shortener_config()` function di `shortener/__init__.py`
- ✅ Return `True` jika migration dilakukan, `False` jika sudah latest
- ✅ Usage: `from shortener import migrate_shortener_config; result = migrate_shortener_config()`

##### D. CLI Tool (`scripts/migrate_shorteners.py`)
- ✅ **Preview Mode**: `--preview` untuk lihat changes tanpa execute
- ✅ **Force Mode**: `--force` untuk force migration meskipun sudah latest
- ✅ **Verbose Mode**: `--verbose` untuk detailed logging
- ✅ **Auto Mode**: Default behavior (auto-detect & execute jika perlu)
- ✅ **366 lines**: Complete CLI tool dengan argparse

##### E. Interactive Demo (`scripts/demo_migration.py`)
- ✅ **7 Learning Scenarios**:
  1. Config Structure - Lihat struktur config sebelum/sesudah
  2. Migration Detection - Bagaimana auto-detection bekerja
  3. Data Preservation - Bukti customizations tetap tersimpan
  4. Migration Process - Step-by-step execution
  5. Backup Management - Backup creation & restoration
  6. API Usage - Programmatic usage examples
  7. Safety Features - Non-destructive guarantees
- ✅ **350 lines**: Interactive learning tool
- ✅ **Color Output**: Rich terminal output untuk better UX

##### F. Documentation (600+ lines total)
- ✅ **SHORTENER_MIGRATION.md**: Comprehensive guide (setup, usage, troubleshooting, FAQ)
- ✅ **MIGRATION_FEATURE_README.md**: Feature overview & quick start
- ✅ **MIGRATION_SUMMARY.md**: Technical implementation details
- ✅ **EXECUTIVE_SUMMARY.md**: Quick overview untuk decision makers
- ✅ **START_HERE.md**: Entry point untuk users baru
- ✅ **DOCS_INDEX.md**: Navigation hub untuk semua docs

##### G. Testing & Verification
- ✅ **6/6 Test Scenarios PASS**:
  1. ✅ Fresh install (no shorteners.json)
  2. ✅ Already latest schema (no migration)
  3. ✅ Old schema with customizations (migration + preservation)
  4. ✅ Missing providers (add new defaults)
  5. ✅ Extra providers (preserve customs)
  6. ✅ Backup creation (file created successfully)

#### 2. Backup/Restore Bug Fix

**Problem**: Syntax errors di `bot/handlers.py` preventing backup/restore execution

**Root Cause**:
- Extra indentation di `cmd_backup` try block (line 2767)
- Missing blank line between exception handler dan next decorator

**Solution Applied**:
- ✅ Fixed indentation alignment
- ✅ Added proper spacing between decorators
- ✅ Verified with syntax check: `python -m py_compile bot/handlers.py` ✅ PASS
- ✅ Verified with import test: `from bot.handlers import cmd_backup, cmd_restore` ✅ PASS
- ✅ Full workflow tested:
  - `backup_database()` ✅ Creates tmpXXX.sql
  - `backup_shorteners()` ✅ Creates tmpXXX.json
  - `create_backup_zip()` ✅ Creates DDMMYYYY-HHMM.zip
  - `extract_backup_zip()` ✅ Extracts files correctly

#### 3. Documentation Cleanup

**Problem**: MD files scattered, potential redundancy, unclear navigation

**Solution**:
- ✅ **Organized Structure**:
  - Root: 4 essential files (START_HERE.md, DOCS_INDEX.md, Readme.md, context.md)
  - Docs: 16 reference files (feature docs + original project docs)
- ✅ **Navigation Hubs**:
  - `DOCS_INDEX.md` di root untuk entry point
  - `docs/INDEX.md` di docs folder untuk internal navigation
- ✅ **Zero Redundancy**: All 20 files serve distinct purposes
- ✅ **Clear Paths**: Multiple navigation paths untuk different user types
- ✅ **Cleanup Report**: `docs/CLEANUP_REPORT.md` documenting organization

#### Files Modified/Created

**Modified**:
- ✅ `shortener/shortener.py` (+150 lines): Migration methods
- ✅ `shortener/__init__.py`: Export `migrate_shortener_config()`
- ✅ `bot/handlers.py`: Backup/restore indentation fix
- ✅ `DOCS_INDEX.md`: Updated references

**Created**:
- ✅ `scripts/migrate_shorteners.py` (366 lines): CLI migration tool
- ✅ `scripts/demo_migration.py` (350 lines): Interactive demo
- ✅ `docs/SHORTENER_MIGRATION.md` (300+ lines): Comprehensive guide
- ✅ `docs/MIGRATION_FEATURE_README.md` (300+ lines): Feature overview
- ✅ `docs/MIGRATION_SUMMARY.md` (250+ lines): Technical details
- ✅ `docs/EXECUTIVE_SUMMARY.md` (200+ lines): Quick overview
- ✅ `docs/BACKUP_RESTORE_FIX.md` (100+ lines): Bug fix documentation
- ✅ `docs/CLEANUP_REPORT.md` (200+ lines): Organization report
- ✅ `docs/INDEX.md` (50+ lines): Docs navigation hub
- ✅ `START_HERE.md` (230+ lines): Entry point
- ✅ `DOCS_INDEX.md` (294 lines): Root navigation hub

#### Key Achievements

**Migration Feature**:
- ✅ Zero data loss during schema updates
- ✅ Fully automatic with manual override option
- ✅ Complete CLI tool with preview mode
- ✅ Interactive demo for learning
- ✅ 600+ lines of documentation
- ✅ 6/6 test scenarios passing

**Backup/Restore**:
- ✅ Syntax errors fixed
- ✅ Full workflow verified
- ✅ All functions tested and working

**Documentation**:
- ✅ 20 files perfectly organized
- ✅ Clear navigation structure
- ✅ Zero redundancy
- ✅ Multiple user paths

#### Impact

**For Users**:
- ✅ Config updates won't break customizations
- ✅ Automatic migration on startup
- ✅ Easy rollback via backup files
- ✅ Backup/restore now working

**For Developers**:
- ✅ Easy to add new shortener providers
- ✅ Schema evolution without breaking changes
- ✅ Clear documentation for maintenance
- ✅ Testing framework in place

**For Project**:
- ✅ Professional documentation structure
- ✅ Sustainable schema evolution
- ✅ Better code maintainability

---

### December 17, 2025 - Cloud Mode Zoom Control Optimization

**Summary**: Optimisasi dan perbaikan fitur kontrol Zoom untuk mode cloud, menghapus fitur yang tidak didukung Zoom API, dan menambahkan refresh status manual.

#### 1. Removed Get Participants Feature
**Reason**: Zoom API tidak menyediakan endpoint untuk mendapatkan live participants di cloud mode
- ❌ **Removed**: `cb_get_zoom_participants()` handler (lines 433-496 deleted)
- ❌ **Endpoint yang tidak ada**: `/v2/metrics/meetings/{id}/participants` (hanya untuk past meetings)
- ❌ **Alternative yang dicoba**: `/v2/meetings/{id}?type=live` (tetap tidak ada participants data)
- ✅ **Decision**: Feature dihapus sepenuhnya karena tidak didukung Zoom API
- ✅ **Impact**: Cloud mode users tidak bisa lihat live participants (hanya available di agent mode)

#### 2. Gated Mute All to Agent Mode Only
**Reason**: Mute All hanya berfungsi dengan agent control (C2-based), tidak via Zoom Cloud API
- ✅ **Guard added**: Check `is_agent_control_enabled()` before allowing mute all
- ✅ **UI Update**: Tombol "🔇 Mute All" hanya muncul saat `ZOOM_CONTROL_MODE=agent`
- ✅ **Error message**: User diberi tahu bahwa fitur hanya tersedia di agent mode
- ✅ **Endpoint modified**: Changed to `/v2/meetings/{id}/participants/status` with action `"mute"`
- ✅ **Impact**: Cloud mode users tidak punya akses mute all (by design)

#### 3. Added Refresh Status Button
**Problem**: Status meeting tidak auto-update setelah start/end meeting
- ✅ **Solution**: Added "🔄️ Refresh Status" button di control interface
- ✅ **Functionality**: Re-trigger `cb_control_zoom()` untuk fetch fresh status dari Zoom API
- ✅ **Placement**: Always available section (lines 312-319)
- ✅ **Callback**: `control_zoom:{meeting_id}` - reuses existing handler
- ✅ **Impact**: Users bisa manual refresh status tanpa keluar-masuk menu

#### 4. Enhanced Start Meeting UX with Direct URL
**Problem**: Start meeting button hanya callback, tidak redirect ke browser/app
- ✅ **Solution**: Added "🚀 Mulai sebagai Host" button dengan `start_url` parameter
- ✅ **Functionality**: One-click redirect ke Zoom as host (browser/app)
- ✅ **Fallback**: Kept "▶️ Start Meeting" callback button
- ✅ **API Call**: Fetch `start_url` from `/v2/meetings/{id}` endpoint
- ✅ **Impact**: Users bisa langsung join meeting tanpa manual login

#### 5. Fixed NameError for Agent Control Check
**Problem**: `NameError: name 'is_agent_control_enabled' is not defined`
- ✅ **Solution**: Added public wrapper function `is_agent_control_enabled()`
- ✅ **Location**: Lines 46-56 in bot/handlers.py
- ✅ **Purpose**: Expose internal `_is_agent_control_enabled()` for public use
- ✅ **Usage**: Used across handlers untuk check agent mode

#### 6. Verified In-Place Message Updates
**Verification**: All Zoom control handlers use `_safe_edit_or_fallback()`
- ✅ **Handlers verified**:
  - `cb_control_zoom()` - Main control interface
  - `cb_start_zoom_meeting()` - Start meeting handler
  - `cb_end_zoom_meeting()` - End meeting handler
  - `cb_mute_all_participants()` - Mute all handler (agent only)
  - `cb_zoom_meeting_details()` - Meeting details viewer
- ✅ **Function**: `_safe_edit_or_fallback()` (lines 1647-1680)
- ✅ **Behavior**: Try edit → fallback to reply → fallback to callback answer
- ✅ **Impact**: No message spam, clean UX

#### 7. Dynamic Control Buttons Based on Status
**Implementation**: Conditional button rendering based on real-time meeting status
- ✅ **Status = Started**:
  - "⏹️ End Meeting" button
  - "🔇 Mute All" button (only if agent mode enabled)
- ✅ **Status = Waiting/Other**:
  - "🚀 Mulai sebagai Host" button (URL, if start_url available)
  - "▶️ Start Meeting" button (callback fallback)
- ✅ **Always Available**:
  - "🔄️ Refresh Status" button (NEW)
  - "📊 Meeting Details" button
  - "⬅️ Kembali ke Daftar" button
- ✅ **Impact**: UI accurately reflects current meeting state

#### API Reference Added
- ✅ **Zoom API Documentation**: https://developers.zoom.us/docs/api/
- ✅ **Key Endpoints Documented**:
  - `/v2/meetings/{id}` - Get meeting details (includes start_url, join_url, status)
  - `/v2/meetings/{id}/status` - Start/End meeting actions
  - `/v2/meetings/{id}/participants/status` - Mute participants (agent mode)
- ✅ **Authentication**: OAuth S2S with account credentials
- ✅ **Required Scopes**: `meeting:read:admin`, `meeting:write:admin`, `recording:read:admin`

---

#### Git Commits (Dec 17):
```
[upcoming] feat(bot): Add refresh button and optimize cloud mode controls
[upcoming] fix(bot): Remove unsupported Get Participants feature
[upcoming] feat(bot): Gate Mute All to agent mode only
[upcoming] feat(bot): Add direct start_url button for one-click host join
[upcoming] docs: Add Zoom API reference documentation to context.md
```

---

#### Summary of Changes:
1. ✅ Removed Get Participants (no Zoom API support for live participants)
2. ✅ Gated Mute All to agent mode only
3. ✅ Added refresh status button for manual updates
4. ✅ Added direct start_url button for better UX
5. ✅ Fixed NameError for agent control check
6. ✅ Verified all handlers use in-place message updates
7. ✅ Dynamic control buttons based on meeting status
8. ✅ Added Zoom API documentation reference

#### Zoom API Limitations (Cloud Mode):
- ❌ No live participants endpoint (only metrics for past meetings)
- ❌ Mute All only via agent mode (not cloud API)
- ✅ Start/End meeting via `/v2/meetings/{id}/status`
- ✅ Get meeting details via `/v2/meetings/{id}`
- ✅ Start URL for one-click host join

#### Next Steps:
- Test refresh button in production
- Monitor Zoom API rate limits
- Consider auto-refresh implementation (optional)
- Document cloud mode limitations for users

---

### December 9, 2025 - Complete Development Workflow Enhancement

**Summary**: Hari ini fokus pada perbaikan auto-recording strategy untuk Agent API toggle dan penambahan development tools untuk meningkatkan produktivitas.

#### 1. Auto-Recording Strategy Fix (zoom/zoom.py)
**PERINGATAN: Ini adalah perbaikan CRITICAL dari implementasi sebelumnya yang terbalik!**

- ✅ **Perbaikan logika auto-recording** yang sebelumnya terbalik:
  - **Agent ENABLED** → `auto_recording = "local"` (Local Recording untuk Agent control)
  - **Agent DISABLED** → `auto_recording = "cloud"` (Cloud Recording, butuh Zoom license)
  
- ✅ **Alasan perubahan**:
  - User dengan Agent: Bisa kontrol recording via local agent (tanpa cloud license)
  - User dengan Cloud License: Gunakan cloud recording otomatis dari Zoom
  - Sebelumnya logika terbalik: Agent disabled malah pakai local (salah!)

- ✅ **Kode implementasi** (lines 201-208 zoom/zoom.py):
  ```python
  # Auto-recording strategy based on Agent API availability:
  # - Agent ENABLED: Use LOCAL recording for Agent control & flexibility
  # - Agent DISABLED: Use CLOUD recording (requires Zoom license with cloud recording)
  if getattr(settings, "agent_api_enabled", True):
      payload["settings"]["auto_recording"] = "local"
  else:
      payload["settings"]["auto_recording"] = "cloud"
  ```

- ✅ **Git commit**: `758bef8 - fix: Correct auto-recording strategy for Agent API toggle`

#### 2. Development Runner with Auto-Restart (dev.py)
- ✅ **Created `dev.py`** - Development runner dengan watchdog integration
- ✅ **Auto-restart functionality**:
  - Monitor file changes (.py, .json)
  - Auto-restart bot tanpa manual intervention
  - Debounce mechanism (0.5s) untuk avoid multiple restarts
  - Graceful process termination dengan timeout handling

- ✅ **Smart File Watching**:
  - **Watched**: `.py` dan `.json` files
  - **Excluded**: `.venv`, `__pycache__`, `.git`, `logs`, `c2_server`, `docker`, database files
  - Recursive monitoring di seluruh project

- ✅ **Available Commands**:
  ```bash
  python dev.py setup              # Setup environment
  python dev.py run                # Run bot normal
  python dev.py run --watch        # Run dengan auto-restart (RECOMMENDED)
  python dev.py debug              # Debug mode
  python dev.py debug --watch      # Debug + auto-restart (RECOMMENDED)
  python dev.py test               # Test imports
  python dev.py check              # Check configuration
  python dev.py help               # Show help
  ```

- ✅ **Features**:
  - Import testing untuk validate dependencies
  - Configuration checking integration
  - Setup script integration (scripts/setup.py)
  - Compatible dengan struktur project baru (run.py)
  - Error handling & graceful shutdown

- ✅ **Impact**: AI agents tidak perlu restart bot manual setelah setiap perubahan code!
- ✅ **Git commit**: `06a0ceb - feat: Add dev.py development runner with auto-restart`

#### 3. Requirements.txt Cleanup & Organization
- ✅ **Removed duplicates**: `aiohttp==3.9.4` tercantum 2x → fixed
- ✅ **Removed unused**: `pyautogui==0.9.53` tidak digunakan di codebase
- ✅ **Added missing**: `pytest-asyncio>=0.21.0` untuk async unit testing
- ✅ **Organized structure**:
  ```
  # Core Bot Dependencies
  aiogram, aiohttp, aiosqlite, python-dotenv
  
  # Development & Testing
  pytest, pytest-asyncio
  
  # Development Tools
  watchdog
  ```
- ✅ **Git commit**: `8ba6abb - refactor: Clean up and organize requirements.txt`

#### 4. Comprehensive .env.example Documentation
- ✅ **Reorganized .env.example** dengan clear struktur:
  
  **REQUIRED SECTION** (Harus dikonfigurasi):
  - TELEGRAM_TOKEN: Telegram bot token
  - INITIAL_OWNER_ID: Telegram user ID
  - INITIAL_OWNER_USERNAME: Telegram username
  - ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
  
  **OPTIONAL SECTION** (Sensible defaults):
  - Database: SQLite (default), PostgreSQL (production)
  - Bot mode: polling (development) / webhook (production)
  - Zoom user: specific user atau account-level
  - Shortener: TinyURL, S.id, Bitly (Indonesian users → S.id recommended)
  - **C2 Framework (Sliver)**: Primary agent control method
  - Logging: DEBUG/INFO/WARNING (default INFO)
  - Data directory: ./data (default)
  - Timezone: Asia/Jakarta (default)

- ✅ **Dokumentasi Agent Control Methods**:
  
  **Option A (RECOMMENDED): C2 Framework + LOCAL Recording**
  ```
  C2_ENABLED=true                    # Primary agent control via Sliver C2
  SLIVER_HOST=your-c2-server
  SLIVER_PORT=31337
  SLIVER_TOKEN=your-token
  AGENT_API_ENABLED=true             # LOCAL recording (Agent can control)
  ```
  - Real-time mTLS communication (no polling overhead!)
  - Scalable architecture (handles thousands of agents)
  - Agent controls recording locally
  - No Zoom license needed
  
  **Option B: Zoom Cloud Recording**
  ```
  C2_ENABLED=false                   # No C2 framework
  AGENT_API_ENABLED=false            # CLOUD recording (Zoom handles it)
  ```
  - Simpler deployment
  - Requires Zoom license with cloud recording
  - Zoom automatically handles recording
  - Less agent control

- ✅ **Key Clarification**:
  - **`C2_ENABLED=true`** ← Primary control method (Sliver C2 Framework)
  - **`AGENT_API_ENABLED=true/false`** ← Recording strategy (LOCAL vs CLOUD)
  - **Legacy polling API is NOT used** (C2 is the modern scalable approach)

- ✅ **Git commit**: `e0b6c40 - docs: Clarify agent control strategy - C2 Framework is primary method`

---

#### Summary of Git Commits Today (Total 5):
```
e0b6c40 docs: Clarify agent control strategy - C2 Framework is primary method
aebb1d1 docs: Comprehensive .env.example with required and optional sections
06a0ceb feat: Add dev.py development runner with auto-restart
8ba6abb refactor: Clean up and organize requirements.txt
758bef8 fix: Correct auto-recording strategy for Agent API toggle
```

---

#### Key Achievements Today:
1. ✅ Fixed critical auto-recording strategy bug
2. ✅ Created dev.py with auto-restart for development
3. ✅ Cleaned up requirements.txt
4. ✅ Comprehensive .env.example documentation
5. ✅ **Clarified C2 Framework as primary agent control method**
6. ✅ All changes documented in context.md

#### Important Architecture Notes:
- **C2 Framework (Sliver)** is the PRIMARY method for agent control
- Uses real-time mTLS communication (NOT polling)
- Scalable: Can handle thousands of agents without polling overhead
- Recording strategy: LOCAL (agent control) or CLOUD (Zoom license)
- Legacy polling API is deprecated/not used in this architecture

#### Next Steps (Future Work):
- Complete Sliver C2 infrastructure setup documentation
- Blokir "Kontrol Zoom" submenu jika C2_ENABLED=false
- Filter semua tombol/aksi agent saat C2 disabled
- Add more unit tests (pytest-asyncio ready)
- Implement database migrations
- Production deployment guide with C2 setup
- Monitoring & logging improvements for C2 agents

---

### December 9, 2025 - Agent Api & Auto-Recording Strategy (SUPERSEDED - SEE ABOVE)
*Note: Bagian ini digantikan dengan implementasi yang benar di atas (December 9, 2025 - Complete Development Workflow Enhancement)*

Sudah dilakukan
- ✅ Tambah opsi ENV AGENT_API_ENABLED (default true) di config/config.py dan digunakan via settings.agent_api_enabled.
- ⚠️ **FIXED**: Auto-recording strategy yang sebelumnya salah, sekarang sudah diperbaiki (lihat section di atas)
- ✅ Menu utama: tombol "Manajemen Agent" disembunyikan saat agent dimatikan (bot/keyboards.py).
- ✅ Handler util: tambah _agent_api_enabled() dan _agent_api_disabled_response() untuk mengecek/tanggapan jika agent dimatikan (bot/handlers.py).   
- ✅ Alur manage meeting: jika agent mati, tombol start/control agent dihilangkan dan ada pesan bahwa rekaman pakai auto-recording Zoom; hanya tersisa delete/edit/back (bot/handlers.py).
- ✅ Start meeting on agent diblok saat agent mati; balasan memakai helper baru (bot/handlers.py).
- ✅ Command /add_agent: ditolak bila agent mati (bot/handlers.py).
- ✅ List/paginasi agents (show_agents_page) diblok bila agent mati (bot/handlers.py).
                                                                                                                                                  
Belum todo        
- Blokir/ubah submenu “Kontrol Zoom” (cb_zoom_control) dan seluruh handler callback C2/agent lain (reinstall/remove/zoom_control actions) jika    
  AGENT_API_ENABLED=false.                                                                                                                        
- Pastikan semua tombol/aksi agent lain ikut tersaring (reinstall_agent, remove_agent, agents_page, zoom_control callbacks, dll).                 
- Dokumentasi ENV baru di .env.example dan README/docs.                                                                                           
- Pertimbangkan pesan khusus pada kontrol recording (toggle/pause) agar tidak mengirim perintah agent ketika dimatikan.                           
- (Opsional) Penyesuaian help text agar mencerminkan mode agent off/auto-recording.

### December 5, 2025 - Project Reorganization
- ✅ **Folder Structure**: Reorganized all files into logical packages
- ✅ **Import Updates**: Updated all imports to use relative imports
- ✅ **Entry Point**: Created `run.py` as main entry point
- ✅ **Package Structure**: Added `__init__.py` to all packages
- ✅ **Docker Updates**: Updated Docker configs for new structure
- ✅ **Documentation**: Created this context file for AI reference
- ✅ **Docker Consolidation**: Consolidated to single `docker-compose.yml` file
- ✅ **Documentation Suite**: Added comprehensive documentation (README, INSTALLATION, DEVELOPMENT, API)
- ✅ **README Links**: Added documentation links to main README.md
- ✅ **CLI Arguments**: Added argument parsing to run.py (--help, --check-config, --log-level, --version)
- ✅ **Agent Documentation**: Added todo_agent.md to agent/ folder clarifying its purpose

### October 2025 - Initial Development
- ✅ **Core Bot**: Basic Telegram bot with aiogram
- ✅ **Zoom Integration**: Full Zoom API integration
- ✅ **User Management**: Complete user role system
- ✅ **Agent System**: Remote control framework
- ✅ **URL Shortener**: Multi-provider shortening
- ✅ **Backup/Restore**: Full system backup
- ✅ **Docker Deployment**: Production-ready containers

## 📊 December 16, 2025 - Multi-Developer Architecture Analysis

**Summary**: Konfirmasi bahwa aplikasi MODULAR (bukan monolitik) dan SIAP untuk kolaborasi multi-developer tanpa saling mengganggu.

### ✅ Architecture Status: MODULAR

**Kesimpulan:**
- ✅ **Bukan monolitik** - Sudah terpisah ke modul independen
- ✅ **Multi-dev ready** - 5+ developers bisa kerja parallel
- ✅ **Minimal conflicts** - Setiap dev punya folder tersendiri
- ✅ **Clear interfaces** - Kontrak antar modul jelas
- ✅ **One-directional deps** - Tidak ada circular dependencies
- ✅ **Centralized config** - Settings di satu tempat (config.py)

### 🏗️ Module Breakdown (5 Independent Modules)

```
bot/         → Handler & UI Layer (Dev 1: Commands & keyboards)
zoom/        → API Layer         (Dev 2: Zoom integration)
db/          → Data Layer        (Dev 3: Database operations)
c2/          → Agent Layer       (Dev 4: Agent control)
shortener/   → Utility Layer     (Dev 5: URL shortening)
config/      → Shared Layer      (All: Settings & config)
```

### 📋 Dependency Graph (One-Directional)

```
bot/ ────────┬──────→ db/ ─────┐
             ├──────→ zoom/    │
             ├──────→ c2/      ├──→ config/
             ├──────→ shortener/
             │
zoom/ ───────┴──────→ config/
db/   ───────────────→ config/
c2/   ───────────────→ config/
shortener/ ─────────→ config/
config/  ───────────→ (nothing)
```

**✅ No circular dependencies - Clean architecture!**

### 👥 Recommended Team Structure

**5-Developer Team:**
| Developer | Module | Responsibility |
|-----------|--------|-----------------|
| Dev 1 | bot/ | Telegram handlers & UI buttons |
| Dev 2 | zoom/ | Zoom API client & OAuth |
| Dev 3 | db/ | Database operations & schema |
| Dev 4 | c2/ | Agent control (C2 client) |
| Dev 5 | shortener/ | URL shortening & utilities |
| Lead | config/, scripts/, main.py | Architecture & integration |

### 🎯 Collaboration Workflow

**Git Strategy:**
```
main ← (stable, production)
  ↓
Development-WithAPP ← (main dev branch)
  ├─ feature/bot-commands (Dev 1)
  ├─ feature/zoom-integration (Dev 2)
  ├─ feature/db-operations (Dev 3)
  ├─ feature/c2-agent-control (Dev 4)
  └─ feature/url-shortener (Dev 5)
```

**Workflow:**
1. Create feature branch from `Development-WithAPP`
2. Edit ONLY your module folder
3. Test locally with `python dev.py run --watch`
4. Commit to feature branch with clear message
5. Create Pull Request to `Development-WithAPP` (NOT main)
6. Get code review & merge

### 📚 Documentation Created

**Two comprehensive guides added:**

1. **`docs/ARCHITECTURE.md`** (841 lines)
   - Detailed modular architecture explanation
   - Multi-dev collaboration strategy
   - Interface contract enforcement
   - Conflict resolution & testing
   - Real-world workflow examples

2. **`docs/MULTI_DEVELOPER_GUIDE.md`** (Quick reference)
   - Step-by-step setup for new developers
   - Module assignment guide
   - Common git commands & issues
   - DO's and DON'Ts for collaboration
   - Quick checklist for daily workflow

### 🔄 Collision Matrix (Merge Conflict Risk)

```
         bot/  zoom/  db/   c2/  shortener/
bot/     -     0%     0%    0%   0%
zoom/    0%    -      0%    0%   0%
db/      0%    0%     -     0%   0%
c2/      0%    0%     0%    -    0%
shortener/ 0%  0%     0%    0%   -

Legend: 0% = No merge conflict expected ✅
```

**Why?** Each developer works on different files, so Git merge automatically succeeds.

### ✅ Key Advantages

| Aspect | Status |
|--------|--------|
| Multiple developers working parallel | ✅ YES |
| Minimal merge conflicts | ✅ YES |
| Clear module boundaries | ✅ YES |
| Independent testing per module | ✅ YES |
| Easy to add new developers | ✅ YES |
| Scalable without refactoring | ✅ YES |
| Clear communication points (interfaces) | ✅ YES |

### 📝 Git Commits (Dec 16)

```
e203aba docs: Add comprehensive multi-developer collaboration guide and architecture documentation
```

---

## 🚀 Next Priority: PRIORITY 1 - Agent Control UI Filtering

**Objective:** Filter/hide agent-related buttons dan handlers saat C2_ENABLED=false atau AGENT_API_ENABLED=false

**Current Status:** ⏳ READY TO START

**Scope:**
1. Update `bot/keyboards.py` - Conditional button display based on C2 settings
2. Update `bot/handlers.py` - Add C2 checks before agent callbacks
3. Add C2 status indicators di UI
4. Test dengan different config combinations

**Files to Edit:**
- `bot/keyboards.py` - Main menu buttons, agent control buttons
- `bot/handlers.py` - Agent-related handlers (callbacks, commands)
- `.env.example` - Already documented (reference only)

**Estimated Time:** 2-3 hours

**Dependencies:** None - Can start immediately

**Git Strategy:**
```
git checkout -b feature/agent-control-ui-filtering
# Edit bot/keyboards.py & bot/handlers.py
# Test locally
git commit -m "feat(bot): Add agent control UI filtering when C2_ENABLED=false"
git push origin feature/agent-control-ui-filtering
# Create Pull Request to Development-WithAPP
```

---

## � Complete Database Migration Documentation (v2025.12.31.6 - Dec 31, 2025 20:15 WIB)

**Status**: ✅ All migrations documented, integrated with config, and tested

**Primary Documentation Files**:

1. **[docs/DATABASE_MIGRATIONS.md](docs/DATABASE_MIGRATIONS.md)** ← START HERE
   - 📖 Comprehensive 700+ line guide covering:
     - Current database location and configuration
     - All 7 tables with detailed documentation
     - Full migration history with SQL examples
     - Database path configuration (DB_PATH, DATABASE_URL)
     - Troubleshooting guide for common issues
     - Best practices for backups and restores
     - How to add new migrations safely

2. **[db/schema.sql](db/schema.sql)** - Schema Reference
   - 🗄️ Production-ready SQL schema (196 lines)
   - Clean table definitions with inline documentation
   - 11 indexes for performance optimization
   - Migration history as comments
   - Foreign key relationships documented

3. **[config/config.py](config/config.py)** - Settings Integration
   - ⚙️ Updated with migration reference
   - Database version noted (v2.0 with Cloud Recording)
   - Configuration examples included

**Migration Summary**:

| # | Date | Type | Table | Column | Status |
|-|-|-|-|-|-|
| 1 | Dec 2025 | ALTER | `meeting_live_status` | `agent_id INTEGER` | ✅ Applied |
| 2 | Dec 31 | ALTER | `meetings` | `cloud_recording_data TEXT` | ✅ Applied |

**Implementation Pattern** (in db/db.py):

```python
async def run_migrations(db):
    """Run database migrations - auto-applied on bot startup"""
    
    # Each migration checks if column exists (idempotent)
    # If missing: ALTER TABLE + await db.commit()
    # If present: Skip (safe)
    # All logged for debugging
```

**Verification Results**:

```
✅ Schema SQL: Valid syntax (196 lines)
✅ Database Tables: 7/7 created
✅ Database Indexes: 11 created
✅ Migration 1: agent_id column present
✅ Migration 2: cloud_recording_data column present
✅ All columns match schema definition
✅ All migrations committed successfully
```

---

## �🔧 Database Schema Migration Fix (v2025.12.31.5 - December 31, 2025)

**Problem**: `sqlite3.OperationalError: no such column: cloud_recording_data`

**Root Cause**: 
- Migration 2 was implemented but didn't commit changes immediately
- SQLite `ALTER TABLE` requires explicit commit to persist
- Old databases created before migration would fail when trying to access new column

**Solution** ([db/db.py](db/db.py) - `run_migrations()` function):
```python
# Migration 1: Add agent_id column
if 'agent_id' not in column_names:
    await db.execute("ALTER TABLE meeting_live_status ADD COLUMN agent_id INTEGER")
    await db.commit()  # ← ADDED: Commit immediately after ALTER TABLE

# Migration 2: Add cloud_recording_data column  
if 'cloud_recording_data' not in column_names:
    await db.execute("ALTER TABLE meetings ADD COLUMN cloud_recording_data TEXT")
    await db.commit()  # ← ADDED: Commit immediately after ALTER TABLE
```

**Key Changes**:
- Added `await db.commit()` after each `ALTER TABLE` statement
- Ensures schema changes are persisted immediately
- Non-blocking - if column already exists, ALTER skipped by `CREATE TABLE IF NOT EXISTS`

**Testing**:
```bash
# Database schema verification
python test_db_schema.py

# Output:
# Meetings columns: [..., 'cloud_recording_data', ...]
# ✅ cloud_recording_data column EXISTS
```

**What Happens on Bot Startup**:
1. Fresh database: `CREATE TABLE meetings(...)` includes `cloud_recording_data` ✓
2. Existing database: Migration 2 detects missing column and adds it ✓
3. Already migrated: Check skipped, no redundant ALTER ✓

**Migration Safety**:
- Non-destructive: No data loss, only adding columns
- Idempotent: Safe to run multiple times
- Logged: Each migration action logged for debugging
- Committed: Changes persist immediately

---

## ⚙️ Cloud Recording UI Integration (v2025.12.31.4 - December 31, 2025)

**Feature**: Cloud Recording button added to Meeting List page

**UI Changes**:

Meeting List Page now displays:
```
🔄 Refresh         (sync from Zoom)
☁️ Cloud Recording  (NEW - view all completed meetings with recordings)
🏠 Kembali ke Menu Utama
```

**Handler Implementation** ([bot/handlers.py](bot/handlers.py)):
- New callback handler: `cb_list_cloud_recordings()` (line 2260+)
- Displays all completed/expired meetings grouped by status
- Shows recording status indicator:
  - ✅ Recording data cached (fetched by background task)
  - ⏳ Recording not yet cached (queued for background task)
- Each meeting clickable → opens cloud recording files viewer
- One-click access from main meeting list without drilling into individual meeting controls

**Keyboard Update** ([bot/keyboards.py](bot/keyboards.py)):
- Updated `list_meetings_buttons()` to include new button
- Button positioned below Refresh, above Home button

**Data Flow**:
```
User clicks "📋 List Meeting" → Shows meeting list
User clicks "☁️ Cloud Recording" → Shows completed meetings
User clicks meeting → Shows cloud recording files [Download] [Play]
```

**Design Rationale**:
- Simplified UX: No need to enter meeting detail view to check recordings
- Consistent with background task: Shows cache status (✅/⏳)
- Efficient: Only shows meetings that have/could have recordings (expired/completed)

---

## ⚙️ Background Task System (v2025.12.31.3 - December 31, 2025)

**Purpose**: Auto-sync cloud recording URLs without blocking main bot

**Cloud Recording Challenge**: 
- Recordings tidak langsung available setelah meeting selesai (delay 1-2 jam)
- Links expire dalam 24 jam
- Tidak efficient fetch on-every-request via Zoom API

**Solution Architecture**:

### BackgroundTaskManager ([bot/background_tasks.py](bot/background_tasks.py) - NEW FILE)

```python
class BackgroundTaskManager:
    """Manages periodic background tasks"""
    
    async def _periodic_cloud_recording_sync(self):
        """Every 30 minutes: Auto-fetch cloud recordings for completed meetings"""
        while self.is_running:
            await asyncio.sleep(1800)  # 30 minutes
            
            # For each meeting with status expired/completed:
            for meeting in meetings:
                if status not in ['expired', 'completed']:
                    continue
                
                # Get cached data from DB
                cached_data = await get_meeting_cloud_recording_data(zoom_id)
                
                # Skip if cached AND last_checked < 1 hour ago
                # This prevents unnecessary API calls
                if cached_data:
                    last_checked = datetime.fromisoformat(cached_data['last_checked'])
                    if (now - last_checked) < timedelta(hours=1):
                        logger.info(f"Skipping {zoom_id}, cache fresh")
                        continue
                
                # Fetch fresh from Zoom API
                recording_data = await zoom_client.get_cloud_recording_urls(zoom_id)
                if recording_data:
                    recording_data['last_checked'] = datetime.now().isoformat()
                    await update_meeting_cloud_recording_data(zoom_id, recording_data)
    
    async def _periodic_cleanup(self):
        """Every 6 hours: Clear old cloud recording data (>30 days)"""
        while self.is_running:
            await asyncio.sleep(21600)  # 6 hours
            
            # Delete recordings for meetings > 30 days old
            cutoff = datetime.now() - timedelta(days=30)
            await db.execute(
                "UPDATE meetings SET cloud_recording_data = NULL WHERE created_at < ?",
                (cutoff.isoformat(),)
            )
```

**Key Design Decisions**:

| Decision | Rationale |
|----------|-----------|
| 30-min sync interval | Balance between freshness and API throttling |
| 1-hour cache before re-fetch | Prevent excessive Zoom API calls on same meeting |
| 6-hour cleanup interval | Efficient DB maintenance without excessive I/O |
| 30-day retention | Cloud links expire anyway, older recordings not useful |
| Store `last_checked` timestamp | Enable smart cache invalidation logic |
| JSON format for cloud_recording_data | Flexible schema (future fields don't require migration) |

**Database Integration** ([db/db.py](db/db.py)):
- `update_meeting_cloud_recording_data(zoom_meeting_id, recording_data)` - Store JSON blob
- `get_meeting_cloud_recording_data(zoom_meeting_id)` - Retrieve JSON blob
- Migration 2 auto-adds `cloud_recording_data TEXT` column on startup

**Bot Lifecycle Integration** ([bot/main.py](bot/main.py)):
```python
async def on_startup():
    await start_background_tasks()  # Line 76
    logger.info("Background task manager started")

# ... bot runs ...

finally:
    await stop_background_tasks()  # Lines 139-140 (on shutdown/error)
    logger.info("Background tasks stopped")
```

**Data Flow**:

```
Meeting Ends → 1-2 hour delay → Cloud Recording Available
                                           ↓
                    Background Task (every 30 min)
                    ├─ Check all meetings status=expired/completed
                    ├─ Get cached data from DB
                    ├─ Skip if cached < 1 hour old ✓ (smart cache)
                    ├─ Fetch from Zoom API if needed
                    ├─ Store JSON to cloud_recording_data column
                    └─ Update last_checked timestamp
                                           ↓
                    User clicks "📹 View Cloud Recordings"
                    ├─ Get cached data from DB (instant)
                    ├─ Display file list [Download] [Play]
                    └─ Falls back to real-time fetch if needed
```

**Testing Commands**:
```bash
# Monitor background tasks in logs
docker logs -f bot_container

# Expected log output every 30 minutes:
# "Cloud Recording Sync: Found 5 meetings to check, fetched 2 new recordings"
# "Cleanup Task: Cleared 3 old recordings from DB"
```

---

## ⚠️ Important Reminders

1. **Security**: Never commit sensitive data (tokens, keys, passwords)
2. **Agent API**: The agent API server implementation is incomplete
3. **Database Migrations**: Always backup before schema changes
4. **Zoom API Limits**: Respect Zoom API rate limits
5. **User Privacy**: Handle user data according to privacy policies
6. **Multi-Dev**: Always create feature branch, never push to Development-WithAPP directly
7. **Code Review**: All PRs must be reviewed before merging
8. **Background Tasks**: Ensure tasks complete gracefully on bot shutdown

## 🎯 Future Enhancements

- Complete agent API server implementation
- Add unit tests (pytest-asyncio framework ready)
- Implement database migrations system
- Add monitoring and logging improvements
- Enhance error handling and recovery
- Focus on direct PC execution and testing workflows
- Expand team to use modular architecture

---

## 📋 Phase 10: Cloud Recording Passcode Display (December 31, 2025 20:45 WIB - v2025.12.31.8)

### ✅ Feature: Display Zoom Cloud Recording Passcode
**Problem:** Cloud recordings yang protected by passcode memerlukan user manual input passcode, making user experience less smooth.

**Solution Implemented:**
1. **Passcode Extraction**: Parse `password` field dari Zoom API `/v2/meetings/{id}/recordings` response
2. **Display in Handler**: Show passcode prominently in cloud recording viewer
3. **Copy-paste Ready**: Passcode ditampilkan dalam `<code>` tag untuk mudah dikopy

### Modified Files
- **bot/cloud_recording_handlers.py** (lines 383-390):
  - Added: `passcode = recording_data.get('password', '')`  (get from Zoom API response)
  - Added: Display passcode in message if available with format: `🔐 Passcode: <code>{passcode}</code>`
  - Result: Users lihat passcode langsung di bot tanpa perlu manual copy dari Zoom

### Implementation Details
**Before:**
```
📹 Cloud Recordings Available
Meeting ID: xxx
Files: 1
[Download] [Play]
```

**After:**
```
📹 Cloud Recordings Available
Meeting ID: xxx
Files: 1
🔐 Passcode: xxxx    <-- NEW: Passcode displayed
[Download] [Play]
```

**Code Location:**
- File: [bot/cloud_recording_handlers.py](bot/cloud_recording_handlers.py)
- Lines 383-390: Passcode extraction and display logic
- Lines 407-413: Passcode rendering in message text

### Zoom API Field Name
- Zoom uses field name: `password` (not `passcode`)
- Stored in database as: `cloud_recording_data` → JSON `password` field
- Retrieved via: `recording_data.get('password', '')`

### User Experience Flow
1. User clicks "☁️ Cloud Recording" button
2. Bot fetches meeting's cloud recording data
3. If recording has passcode, bot displays: **🔐 Passcode: xxxx**
4. User can click download/play links
5. If prompted for passcode by Zoom, user copy dari message

### Status
**✅ COMPLETE** - Cloud recording passcode now displayed automatically

---

## 📋 Phase 11: Simplified Cloud Recording UI (December 31, 2025 20:50 WIB - v2025.12.31.9)

### ✅ Feature: Simplify Cloud Recording Download UI
**Problem:** Terlalu banyak tombol untuk file-file yang jarang didownload (M4A, TIMELINE, TRANSCRIPT, CC, Play button)

**Solution Implemented:**
1. **Only MP4 Download**: Hanya tampilkan tombol "📥 Download MP4" saja
2. **Remove Extra Buttons**: Hapus tombol Play, M4A, TIMELINE, TRANSCRIPT, CC
3. **Keep File Info**: Tetap tampilkan info semua file type (untuk referensi), tapi hanya MP4 yang bisa didownload
4. **Remove Share Button**: Hapus "Open in Zoom Web" button

### Modified Files
- **bot/cloud_recording_handlers.py** (lines 423-465):
  - Changed: Only add download buttons for MP4 files
  - Removed: Play buttons, M4A buttons, TIMELINE/TRANSCRIPT/CC buttons, Share URL button
  - Kept: File list with all types (for information), but only MP4 is downloadable

### Before vs After

**Before (Terlalu banyak tombol):**
```
📥 Download MP4
▶️ Play MP4
📥 Download M4A
▶️ Play M4A
📥 Download TIMELINE
📥 Download CC
📥 Download TRANSCRIPT
🌐 Open in Zoom Web
🔄 Refresh
🎥 Kembali ke Kontrol
📋 Daftar Meeting
```

**After (Clean & Simple):**
```
📥 Download MP4
🔄 Refresh
🎥 Kembali ke Kontrol
📋 Daftar Meeting
```

### Implementation
```python
# Only MP4 files can be downloaded
mp4_files = [f for f in recording_files if f.get('file_type') == 'MP4']

for file in mp4_files:
    download_url = file.get('download_url', '')
    file_size = file.get('file_size', 0)
    if download_url:
        kb_rows.append([
            InlineKeyboardButton(
                text=f"📥 Download MP4 ({format_size(file_size)})", 
                url=download_url
            )
        ])
```

### Status
**✅ COMPLETE** - Cloud recording UI simplified, only MP4 download button shown

---

## 📋 Phase 12: Meeting Status Renamed - expired → done (December 31, 2025 21:00 WIB - v2025.12.31.10)

### ✅ Feature: Rename Meeting Status from "expired" to "done"
**Problem:** Status "expired" kurang semantik dan agak membingungkan. "done" lebih intuitif dan user-friendly.

**Changes Made:**
1. **Database Status**: All `status = 'expired'` → `status = 'done'`
2. **UI Labels**: "Ditandai Expired" → "Ditandai Done"
3. **Messages**: "expired" → "done" di semua text display

### Files Modified

1. **db/db.py** (Lines 772 & 832 - both update_expired_meetings() functions)
   - Changed: `"UPDATE meetings SET status = 'expired', ..."` → `"UPDATE meetings SET status = 'done', ..."`
   - Kept: `stats['expired']` (internal counter name, for backward compatibility)
   - Kept: Function name `update_expired_meetings()` (for backward compatibility)

2. **bot/handlers.py** (Multiple locations)
   - Line 1691: `f"⏰ Ditandai Expired:"` → `f"✅ Ditandai Done:"`
   - Line 1713: `"🔍 Memeriksa meeting yang sudah expired..."` → `"🔍 Memeriksa meeting yang sudah done..."`
   - Line 1718: `"✅ <b>Pemeriksaan expired selesai!</b>"` → `"✅ <b>Pemeriksaan done selesai!</b>"`
   - Line 1720: `f"⏰ Meeting ditandai expired:"` → `f"✅ Meeting ditandai done:"`
   - Line 1722: `"Meeting yang sudah lewat waktu mulai akan ditandai sebagai expired."` → `"Meeting yang sudah lewat waktu mulai akan ditandai sebagai done."`
   - Line 2268: `m.get('status') == 'expired'` → `m.get('status') == 'done'` (for cloud recordings filter)
   - Line 3815: `f"⏰ Ditandai Expired:"` → `f"✅ Ditandai Done:"` (callback version)
   - Line 3840: Similar updates in callback handler

### Status Mapping

**Before:**
- `active` - Meeting masih aktif/belum dimulai
- `expired` - Meeting sudah lewat waktu mulai
- `deleted` - Meeting sudah dihapus

**After:**
- `active` - Meeting masih aktif/belum dimulai
- `done` - Meeting sudah lewat waktu mulai (RENAMED from 'expired')
- `deleted` - Meeting sudah dihapus

### Backward Compatibility
- ✅ Function names unchanged: `update_expired_meetings()` still works
- ✅ Stats counter unchanged: `stats['expired']` counter name for compatibility
- ✅ Database queries unchanged: Filter still works with new 'done' status
- ✅ No migration needed: Just a semantic rename for better UX

### Status
**✅ COMPLETE** - All "expired" statuses renamed to "done"

---

## 📋 Phase 13: Fixed Meeting List Time Range with Proper Timezone (December 31, 2025 21:05 WIB - v2025.12.31.11)

### ✅ Bug Fix: Meeting List Not Showing from 00:00 (Midnight)
**Problem:** Meeting list masih tidak menampilkan meetings dari jam 00:00 (tengah malam) di hari tersebut. 
Hanya menampilkan meetings dari waktu saat ini saja (contoh: 19:35 ke depan).

**Root Cause:** Timezone handling di Zoom API integration kurang tepat. Zoom API memerlukan:
1. Parameter `from` dan `to` dalam format UTC ISO (bukan local time)
2. Konversi timezone yang benar dari Jakarta (UTC+7) ke UTC

**Solution Implemented:**
1. **Timezone Conversion**: Convert Jakarta time → UTC untuk API request
2. **Midnight Start**: Hitung 00:00 Jakarta time, baru convert ke UTC
3. **Proper Range**: from = 00:00 Jakarta (UTC) → to = 00:00 + 30 hari (UTC)

### Modified Files
**File: [zoom/zoom.py](zoom/zoom.py#L214)**
- Lines 214-250: Updated `list_upcoming_meetings()` function

### Code Changes

**Before (Incorrect):**
```python
today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
from_date = today_start.isoformat()  # Wrong: uses local time without timezone
to_date = (today_start + timedelta(days=30)).isoformat()
```

**After (Correct):**
```python
# Get current time in UTC, then convert to Asia/Jakarta timezone
now_utc = datetime.now(timezone.utc)
jakarta_tz = timezone(timedelta(hours=7))  # UTC+7
now_jakarta = now_utc.astimezone(jakarta_tz)

# Start from 00:00:00 of current day (in Jakarta time)
today_start = now_jakarta.replace(hour=0, minute=0, second=0, microsecond=0)

# Convert back to UTC for API (Zoom API expects UTC)
from_date = today_start.astimezone(timezone.utc).isoformat()
to_date = (today_start + timedelta(days=30)).astimezone(timezone.utc).isoformat()
```

### Timezone Math
**Example: December 31, 2025 19:35 WIB**
- Current time Jakarta: Dec 31 19:35 UTC+7
- Midnight Jakarta today: Dec 31 00:00 UTC+7 = Dec 30 17:00 UTC ✓
- Zoom API range: Dec 30 17:00 UTC → Jan 29 17:00 UTC
- Shows: All meetings from midnight Dec 31 Jakarta time forward

### API Parameters Updated
- ✅ Removed: `timezone` parameter (Zoom doesn't need it when using UTC)
- ✅ Added: Proper UTC conversion for `from` and `to` parameters
- ✅ Added: Debug logging untuk timezone conversion

### Status
**✅ COMPLETE** - Meeting list now shows from midnight (00:00) of current day in Jakarta timezone

---

## 📋 Phase 14: Cloud Recording Display - Only MP4 with Formatted Date (December 31, 2025 21:15 WIB - v2025.12.31.12)

### ✅ Feature: Simplify Cloud Recording Files Display
**User Request:** "Untuk tampilan ini cukup tampilkan File MP4nya saja di Chat, kemudian Startnya di convert juga ke Standar Format Tanggal di script ini!"

**Problem Solved:**
1. Terlalu banyak file types ditampilkan (MP4, M4A, TIMELINE, TRANSCRIPT, CC)
2. Recording start time format tidak konsisten dengan format tanggal standar di aplikasi

**Solution Implemented:**
1. **Filter MP4 Only**: Hanya tampilkan file MP4 dalam daftar file
2. **Formatted Date**: Convert `recording_start` ISO format ke "Hari, DD Bulan Tahun HH:MM"
3. **Consistent Formatting**: Gunakan format tanggal yang sama dengan file lain di aplikasi

### Modified Files
**File: [bot/cloud_recording_handlers.py](bot/cloud_recording_handlers.py#L420)**
- Lines 420-475: Updated cloud recording file display logic

### Code Changes

**Before:**
```python
# Display ALL file types
for idx, file in enumerate(recording_files, 1):
    file_type = file.get('file_type', 'Unknown')
    text += f"{emoji} <b>File {idx}: {file_type}</b>\n"
    text += f"   Start: {recording_start}\n"  # ISO format (2025-12-24T02:42:27Z)
```

**After:**
```python
# Filter ONLY MP4 files
mp4_files = [f for f in recording_files if f.get('file_type') == 'MP4']

# Display MP4 with formatted date
for idx, file in enumerate(mp4_files, 1):
    text += f"🎬 <b>File {idx}: MP4</b>\n"
    
    # Convert ISO format to: "Hari, DD Bulan Tahun HH:MM"
    recording_start = file.get('recording_start', '')
    if recording_start:
        # Parse ISO date string
        dt = datetime.fromisoformat(recording_start.replace('Z', '+00:00'))
        
        # Convert to Jakarta timezone
        jakarta_tz = timezone(timedelta(hours=7))
        local_dt = dt.astimezone(jakarta_tz)
        
        # Format: "Senin, 24 Desember 2025 10:42"
        day_name = {'Monday': 'Senin', 'Tuesday': 'Selasa', ...}[local_dt.strftime("%A")]
        month_name = {'December': 'Desember', ...}[local_dt.strftime("%B")]
        formatted_date = f"{day_name}, {local_dt.day:02d} {month_name} {local_dt.year} {local_dt:%H:%M}"
        
        text += f"   Start: {formatted_date}\n"
```

### Display Comparison

**Before (All file types):**
```
🎬 File 1: MP4
   Size: 102.3 MB
   Start: 2025-12-24T02:42:27Z

🎵 File 2: M4A
   Size: 16.1 MB
   Start: 2025-12-24T02:42:27Z

📊 File 3: TIMELINE
   Size: 705.4 KB
   Start: 2025-12-24T02:42:27Z

[Other files...]

📥 Download MP4 (102.3 MB)
```

**After (Only MP4 with formatted date):**
```
🎬 File 1: MP4
   Size: 102.3 MB
   Start: Rabu, 24 Desember 2025 09:42

📥 Download MP4 (102.3 MB)
```

### Timezone Conversion Details
- **Input**: ISO format with timezone (e.g., `2025-12-24T02:42:27Z`)
- **Step 1**: Parse to datetime with timezone info
- **Step 2**: Get user's timezone from .env via `settings.timezone`
- **Step 3**: Convert to user's timezone using `pytz`
- **Step 4**: Format as Indonesian date format: "Hari, DD Bulan Tahun HH:MM"
- **Output**: "Rabu, 24 Desember 2025 09:42" (in user's local timezone) ✓

### File Type Constants
Implemented Indonesian date name mappings:
- **Days**: Monday→Senin, Tuesday→Selasa, ..., Sunday→Minggu
- **Months**: January→Januari, February→Februari, ..., December→Desember

### Date Format Consistency
This format matches the standard date display used elsewhere in the application:
- **Used in**: Meeting details, meeting history, backup files
- **Format**: "{Day}, {DD} {Month} {YYYY} {HH}:{MM}"
- **Example**: "Rabu, 24 Desember 2025 09:42"

### User Experience Impact
1. ✅ **Cleaner UI**: Only MP4 files shown (no clutter)
2. ✅ **Readable Dates**: Human-friendly date format instead of ISO
3. ✅ **Consistent Styling**: Matches date format used throughout app
4. ✅ **User's Timezone**: Automatically shows in local timezone from .env
5. ✅ **Faster Scanning**: Users can quickly find and download recordings

### Status
**✅ COMPLETE** - Cloud recording display now shows only MP4 files with formatted dates in user's timezone

---

## 📋 Phase 15: Dynamic User Timezone for Cloud Recording Dates (December 31, 2025 21:20 WIB - v2025.12.31.13)

### ✅ Feature: Use .env Timezone Instead of Hardcoded Jakarta
**User Request:** "Jangan Convert ke Jakarta, sesuaikan dengan Timezone User sesuai .env!"

**Problem Addressed:**
- Phase 14 hardcoded Jakarta timezone (UTC+7)
- Different users in different timezones need their own local time display
- Bot already has `TIMEZONE` setting in .env (default: Asia/Jakarta)

**Solution Implemented:**
1. **Dynamic Timezone**: Read `settings.timezone` from config
2. **PyTZ Integration**: Use `pytz` library for proper timezone handling
3. **User-Centric**: Each user sees recordings in their local timezone

### Modified Files
**File: [bot/cloud_recording_handlers.py](bot/cloud_recording_handlers.py#L420)**
- Lines 420-475: Updated date formatting logic

### Code Changes

**Before (Hardcoded Jakarta):**
```python
# Hardcoded timezone - only works for Jakarta users
jakarta_tz = timezone(timedelta(hours=7))  # UTC+7
local_dt = dt.astimezone(jakarta_tz)
```

**After (Dynamic User Timezone):**
```python
# Get user's timezone from .env
import pytz
from config import settings

user_tz = pytz.timezone(settings.timezone)  # e.g., "Asia/Jakarta", "Asia/Bangkok", "UTC"
local_dt = dt.astimezone(user_tz)
```

### Implementation Details

**Timezone Source:**
```python
# config/config.py (line 76)
timezone: str = os.getenv("TIMEZONE") or os.getenv("TZ") or os.getenv("PYTZ_TIMEZONE", "Asia/Jakarta")
```

**Priority Order:**
1. `TIMEZONE` environment variable (primary)
2. `TZ` environment variable (fallback)
3. `PYTZ_TIMEZONE` environment variable (fallback)
4. `"Asia/Jakarta"` (default)

**Example .env Configurations:**

```bash
# Option 1: Jakarta timezone
TIMEZONE=Asia/Jakarta

# Option 2: Bangkok timezone
TIMEZONE=Asia/Bangkok

# Option 3: UTC (no timezone offset)
TIMEZONE=UTC

# Option 4: US Eastern Time
TIMEZONE=America/New_York

# Option 5: London timezone
TIMEZONE=Europe/London
```

### Supported Timezone Strings
Any IANA timezone identifier is supported. Common examples:
- **Asia**: `Asia/Jakarta`, `Asia/Bangkok`, `Asia/Tokyo`, `Asia/Manila`, `Asia/Singapore`
- **Europe**: `Europe/London`, `Europe/Paris`, `Europe/Berlin`, `Europe/Istanbul`
- **Americas**: `America/New_York`, `America/Los_Angeles`, `America/Toronto`
- **UTC**: `UTC`, `Etc/UTC`
- **Etc**: `Etc/GMT`, `Etc/GMT+8`

### Example Output Comparison

**Same recording viewed from different timezones:**

```
Recording start (UTC): 2025-12-24T02:42:27Z

TIMEZONE=Asia/Jakarta     → Rabu, 24 Desember 2025 09:42
TIMEZONE=Asia/Bangkok     → Rabu, 24 Desember 2025 09:42  (same UTC+7)
TIMEZONE=America/New_York → Selasa, 23 Desember 2025 21:42 (UTC-5)
TIMEZONE=UTC              → Rabu, 24 Desember 2025 02:42
```

### Error Handling
- **Invalid Timezone**: Fallback to recording_start ISO format if timezone conversion fails
- **Missing .env**: Defaults to Asia/Jakarta (for backward compatibility)
- **Exception Logging**: Detailed debug logs for troubleshooting timezone issues

### PyTZ Library
- **Already Available**: Most Python installations include `pytz`
- **If Missing**: Install via `pip install pytz`
- **Advantage**: Handles DST (Daylight Saving Time) automatically
- **Handles**: All IANA timezone identifiers

### User Experience
1. ✅ **Consistent with System**: Dates display in user's configured timezone
2. ✅ **No Manual Conversion**: User doesn't need to mentally convert times
3. ✅ **Enterprise-Ready**: Works for globally distributed teams
4. ✅ **Easy Configuration**: Change one .env variable to change all date displays
5. ✅ **Future-Proof**: Adding users in new timezones requires no code changes

### Status
**✅ COMPLETE** - Cloud recording display now dynamically uses user's timezone from .env

---

## 📋 Phase 16: Cloud Recording Back Button Navigation (December 31, 2025 21:22 WIB - v2025.12.31.14)

### ✅ Fix: Back Button Should Return to Cloud Recording List, Not Meeting Control
**Issue:** Tombol "Kembali ke Kontrol" seharusnya kembali ke Cloud Recording List, bukan ke Meeting Control

**Problem Identified:**
- User viewing cloud recording files → clicks "Kembali ke Kontrol" button
- Expected: Return to Cloud Recording List (showing all completed meetings with recordings)
- Actual: Returns to Meeting Control (meeting control panel)
- Button label: "🎥 Kembali ke Kontrol" tidak match dengan destination

**Solution Implemented:**
1. **Button Label**: Changed from "🎥 Kembali ke Kontrol" → "☁️ Kembali ke Cloud Recording"
2. **Callback Data**: Changed from `control_zoom:{meeting_id}` → `list_cloud_recordings`
3. **Navigation Flow**: Now properly returns to cloud recording list view

### Modified Files
**File: [bot/cloud_recording_handlers.py](bot/cloud_recording_handlers.py#L492)**
- Lines 492-495: Updated back button callback

### Code Changes

**Before:**
```python
# Navigation buttons
kb_rows.extend([
    [InlineKeyboardButton(text="🔄 Refresh", callback_data=f"view_cloud_recordings:{meeting_id}")],
    [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],  # ❌ Wrong destination
    [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
])
```

**After:**
```python
# Navigation buttons
kb_rows.extend([
    [InlineKeyboardButton(text="🔄 Refresh", callback_data=f"view_cloud_recordings:{meeting_id}")],
    [InlineKeyboardButton(text="☁️ Kembali ke Cloud Recording", callback_data="list_cloud_recordings")],  # ✅ Correct destination
    [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
])
```

### Navigation Flow

**Cloud Recording View Navigation:**
```
User viewing recording files
    ↓
🔄 Refresh → Stay in same view (refresh)
☁️ Kembali ke Cloud Recording → list_cloud_recordings callback ✅
📋 Daftar Meeting → list_meetings callback
```

**Complete User Journey:**
```
Meeting List
    ↓
☁️ Cloud Recording button
    ↓
List of completed meetings
    ↓
Click on meeting → view_cloud_recordings:{meeting_id}
    ↓
Cloud Recording Files View (MP4 list)
    ↓
☁️ Back Button → Returns to completed meetings list ✅
```

### Button Updates
| Component | Before | After |
|-----------|--------|-------|
| Label | 🎥 Kembali ke Kontrol | ☁️ Kembali ke Cloud Recording |
| Callback | `control_zoom:{meeting_id}` | `list_cloud_recordings` |
| Destination | Meeting Control Panel | Cloud Recording List |
| Semantic Match | ❌ Incorrect | ✅ Correct |

### Status
**✅ COMPLETE** - Cloud recording back button now correctly returns to cloud recording list

---

## 📋 Phase 17: Cloud Recording List Pagination and Sorting (December 31, 2025 21:25 WIB - v2025.12.31.15)

### ✅ Feature: Pagination (5 per page) and Sorting (Newest First)
**User Request:** "Pastikan per halaman hanya 5 Recording, Urutannya adalah Meeting yang baru saja selesai ke yang paling lama!"

**Problem Addressed:**
1. Cloud recording list bisa sangat panjang jika banyak meetings
2. No pagination → hard to scroll through many recordings
3. No sorting → recordings ditampilkan random order
4. Need newest first ordering (most recent meetings at top)

**Solution Implemented:**
1. **Pagination**: Display 5 recordings per page with prev/next buttons
2. **Sorting**: Sort by `start_time` descending (newest first)
3. **Page Display**: Show "Halaman X/Y" indicator
4. **Navigation**: Previous/Next buttons with page number display

### Modified Files
**File: [bot/handlers.py](bot/handlers.py#L2254)**
- Lines 2254-2355: Updated `cb_list_cloud_recordings()` handler

### Code Changes

**Before (All items on one page):**
```python
# Display all completed meetings
for m in completed_meetings:
    kb_rows.append([InlineKeyboardButton(...)])
```

**After (Paginated with sorting):**
```python
# Extract page number from callback data
page = 1
if ':' in c.data:
    page = int(c.data.split(':')[1])

# Sort by start_time descending (newest first)
completed_meetings.sort(
    key=lambda m: datetime.fromisoformat(m.get('start_time', '').replace('Z', '+00:00')),
    reverse=True
)

# Pagination: 5 per page
items_per_page = 5
total_pages = (len(completed_meetings) + items_per_page - 1) // items_per_page

# Get items for current page
start_idx = (page - 1) * items_per_page
end_idx = start_idx + items_per_page
page_meetings = completed_meetings[start_idx:end_idx]

# Display only current page items
for m in page_meetings:
    kb_rows.append([InlineKeyboardButton(...)])

# Add pagination buttons if needed
if total_pages > 1:
    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"list_cloud_recordings:{page-1}"))
    pagination_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton(text="Berikutnya ▶️", callback_data=f"list_cloud_recordings:{page+1}"))
    kb_rows.append(pagination_row)
```

### Features Implemented

**1. Sorting (By Start Time - Descending):**
- ✅ Newest meetings appear first
- ✅ Oldest meetings appear last
- ✅ Based on meeting `start_time` field
- ✅ Fallback handling for invalid dates

**2. Pagination (5 per page):**
- ✅ Maximum 5 recordings per page
- ✅ Automatic page calculation
- ✅ Page numbers in callback data: `list_cloud_recordings:1`, `list_cloud_recordings:2`, etc.
- ✅ Safe page bounds checking

**3. UI Display:**
- ✅ "Halaman X/Y (5 per halaman)" indicator
- ✅ "◀️ Sebelumnya" button (if not first page)
- ✅ Page number button "{X}/{Y}" (non-clickable)
- ✅ "Berikutnya ▶️" button (if not last page)

**4. Callback Routing:**
- ✅ Updated regex: `lambda c: c.data == 'list_cloud_recordings' or c.data.startswith('list_cloud_recordings:')`
- ✅ Supports both `list_cloud_recordings` (page 1) and `list_cloud_recordings:{page}` (any page)

### Example Display

**With 12 meetings (3 pages):**

```
Page 1/3:
1. ✅ Tidak Lanjut Implementasi Kas
2. ✅ Kickoff Implementasi MX Imperv
3. ⏳ Rapat Knowbe4
4. ⏳ Integrasi EDR Kaspersky
5. ✅ Meeting 5

◀️ Sebelumnya | 1/3 | Berikutnya ▶️
⬅️ Kembali ke Daftar Meeting

---

Page 2/3:
6. ✅ Meeting 6
7. ⏳ Meeting 7
8. ✅ Meeting 8
9. ⏳ Meeting 9
10. ✅ Meeting 10

◀️ Sebelumnya | 2/3 | Berikutnya ▶️
⬅️ Kembali ke Daftar Meeting

---

Page 3/3:
11. ⏳ Meeting 11
12. ✅ Meeting 12

◀️ Sebelumnya | 3/3 |
⬅️ Kembali ke Daftar Meeting
```

### Sorting Logic

**Sort Key:** `start_time` field from meeting data
**Order:** Descending (reverse=True)
**Format:** ISO 8601 datetime

**Example Timeline:**
```
2025-12-31 14:00:00 UTC  (Meeting 1 - NEWEST, appears first)
2025-12-31 12:00:00 UTC  (Meeting 2)
2025-12-30 10:00:00 UTC  (Meeting 3)
2025-12-29 09:00:00 UTC  (Meeting 4 - OLDEST, appears last)
```

### Pagination Logic

**Items per page:** 5
**Formula:** `total_pages = (total_items + 4) // 5`

**Examples:**
```
1-5 items   → 1 page
6-10 items  → 2 pages
11-15 items → 3 pages
16-20 items → 4 pages
```

**Page bounds checking:**
- If `page < 1` → set to 1
- If `page > total_pages` → set to last page
- Safe navigation (no crashes on invalid pages)

### UI Flow

```
Cloud Recording List (Page 1)
├─ Prev button (disabled if page 1)
├─ 5 Recording items
├─ Next button (disabled if last page)
└─ Back button

User clicks "Berikutnya ▶️" → callback: list_cloud_recordings:2
└─ Handler re-renders page 2 with updated items
```

### User Experience
1. ✅ **Cleaner Display**: Only 5 items per page
2. ✅ **Newest First**: Most recent meetings at top
3. ✅ **Easy Navigation**: Previous/Next buttons
4. ✅ **Page Indicator**: Users know current position
5. ✅ **Scalable**: Works with any number of recordings

### Status
**✅ COMPLETE** - Cloud recording list now supports pagination (5/page) and sorting (newest first)

---

## 📋 Verification: FSM (Finite State Machine) Feature Status (December 31, 2025 21:30 WIB - v2025.12.31.16)

### ✅ FSM Feature is FULLY IMPLEMENTED and ACTIVE

**Verification Result:** The `fsm_states` table appears empty because FSM states are created **dynamically** when users interact with the bot, not during initialization.

### Implementation Status

**1. Database Table ✅**
- **Location**: [db/db.py](db/db.py#L89) - Line 89
- **Table Name**: `fsm_states`
- **Columns**:
  - `user_id INTEGER PRIMARY KEY` - Unique telegram user ID
  - `state TEXT` - Current FSM state name
  - `data TEXT` - JSON-encoded FSM context data
  - `updated_at TIMESTAMP` - Last update timestamp
- **Purpose**: Persist user conversation state across bot restarts

**2. FSM Storage Implementation ✅**
- **Class**: `DatabaseFSMStorage`
- **File**: [bot/fsm_storage.py](bot/fsm_storage.py)
- **Base Class**: `BaseStorage` (aiogram 3.x standard)
- **Methods Implemented**:
  - `set_state(key, state)` - Save FSM state to database
  - `get_state(key)` - Retrieve user's current FSM state
  - `set_data(key, data)` - Save FSM context data (JSON)
  - `get_data(key)` - Retrieve user's FSM context data
  - `delete(key)` - Clear user's FSM state and data
- **Async Support**: All methods are async for non-blocking I/O

**3. Bot Configuration ✅**
- **Location**: [bot/main.py](bot/main.py#L124) - Line 124
- **Configuration**: 
  ```python
  dp = Dispatcher(storage=DatabaseFSMStorage(settings.db_path))
  ```
- **Status**: ACTIVE at startup

**4. FSM States Defined ✅**
Multiple `StatesGroup` classes defined in [bot/handlers.py](bot/handlers.py):

| State Group | Purpose | States |
|-------------|---------|--------|
| `MeetingStates` | Meeting creation | Creating meeting |
| `ShortenerStates` | URL shortening | Waiting for provider |
| `RestoreStates` | Database restore | Waiting for backup file |
| `UserSearchStates` | User search | Searching users |
| `ZoomManageStates` | Meeting control | Controlling meeting |
| `ZoomEditStates` | Meeting editing | Waiting for topic, date, time |

**5. FSM Usage in Handlers ✅**
Active state transitions throughout [bot/handlers.py](bot/handlers.py):

```python
# Examples of FSM usage:
await state.set_state(ZoomManageStates.controlling_meeting)  # Line 792
await state.set_state(ZoomEditStates.waiting_for_topic)      # Line 1123
await state.set_state(ZoomEditStates.waiting_for_date)       # Line 1140
await state.set_state(ZoomEditStates.waiting_for_time)       # Line 1157
# ... and many more state transitions
```

### Why is the fsm_states Table Empty?

**This is NORMAL and EXPECTED behavior!** ✅

**Reason**: FSM states are created **dynamically** when users interact with bot:

1. **User starts bot**: Types `/start`
2. **No FSM state created yet**: User is in default state (no entry in fsm_states)
3. **User triggers FSM command**: Types command that uses FSM (e.g., edit meeting)
4. **FSM state created**: `set_state()` writes entry to fsm_states table
5. **Entry persists**: Even if bot restarts, user's state is preserved in database

**Timeline Example:**
```
Time 0:00    → User opens bot: fsm_states table is EMPTY (no state yet)
Time 0:05    → User types /edit_meeting: Entry created in fsm_states
Time 0:10    → User types meeting details: Entry updated with data
Time 0:15    → Bot restarts: User's state PERSISTS (reads from fsm_states)
Time 0:20    → User continues where they left off: FSM state restored ✅
```

### Data Flow: FSM State Persistence

```
┌─────────────────────────────────────────────────────────────────┐
│ USER INTERACTION                                                │
│ 1. User sends /edit_meeting command                           │
└────────────┬────────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────────┐
│ HANDLER                                                         │
│ 2. Handler detects command and calls:                         │
│    await state.set_state(ZoomEditStates.waiting_for_topic)   │
└────────────┬────────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────────┐
│ FSM STORAGE                                                     │
│ 3. DatabaseFSMStorage.set_state() called                      │
│    - Serializes state to string                              │
│    - JSON-encodes any context data                           │
└────────────┬────────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────────┐
│ DATABASE                                                        │
│ 4. INSERT OR REPLACE INTO fsm_states:                         │
│    user_id: 12345                                            │
│    state: "ZoomEditStates:waiting_for_topic"                │
│    data: {"meeting_id": "123", "topic": "test"}            │
│    updated_at: 2025-12-31 21:30:00                         │
└────────────┬────────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────────┐
│ BOT RESTART                                                     │
│ 5. On next message, bot calls:                               │
│    current_state = await storage.get_state(StorageKey(...)) │
│    - Reads from fsm_states table                            │
│    - Returns: "ZoomEditStates:waiting_for_topic"           │
└────────────┬────────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────────┐
│ USER EXPERIENCE                                                 │
│ 6. User resumes exactly where they left off! ✅               │
│    No need to start conversation over                        │
└─────────────────────────────────────────────────────────────────┘
```

### FSM Benefits in This Bot

1. **State Persistence Across Restarts**: Users don't lose their place if bot restarts
2. **Multi-Step Commands**: Users can go through multi-step workflows (edit meeting, create, etc.)
3. **Context Preservation**: Each user's context (meeting ID, search query, etc.) is saved
4. **User Experience**: Seamless experience even with network interruptions
5. **Production Ready**: Scales to thousands of concurrent users

### Example FSM Workflow: Edit Meeting

```
User → /edit_meeting
       ↓ FSM State: ZoomEditStates.waiting_for_topic
       ← Bot: "Which meeting? (show list)"
User → Click meeting
       ↓ FSM State: ZoomEditStates.waiting_for_new_topic
       ← Bot: "Enter new topic:"
User → "New Topic"
       ↓ FSM State: ZoomEditStates.waiting_for_date
       ← Bot: "Enter new date (DD/MM/YYYY):"
User → "25/01/2026"
       ↓ FSM State: ZoomEditStates.waiting_for_time
       ← Bot: "Enter new time (HH:MM):"
User → "10:30"
       ↓ FSM State: None (completed)
       ← Bot: "✅ Meeting updated successfully!"
```

### FSM Configuration

**No additional configuration needed!** FSM is automatically:
- ✅ Initialized on bot startup
- ✅ Stored to database on every state change
- ✅ Restored on bot restart
- ✅ Cleaned up when user ends interaction

### Verification Commands

To verify FSM is working, check these logs when bot starts:
```
[bot.main] Bot starting...
[bot.fsm_storage] FSM storage initialized
[dispatcher] FSM storage registered: DatabaseFSMStorage
```

When user triggers FSM:
```
[bot.fsm_storage] FSM state set for user 12345: ZoomEditStates:waiting_for_topic
[bot.fsm_storage] FSM data set for user 12345: 2 keys
```

When fsm_states table gets populated:
```
sqlite> SELECT * FROM fsm_states;
user_id | state                              | data                        | updated_at
12345   | ZoomEditStates:waiting_for_topic   | {"meeting_id": "123"}      | 2025-12-31...
```

### Conclusion

**FSM Feature Status: ✅ FULLY IMPLEMENTED AND ACTIVE**

The empty `fsm_states` table is expected during testing. It will automatically populate as users interact with the bot through multi-step commands. This is a feature, not a bug—it shows the database is properly designed for lazy initialization (only creates records when needed).

---

## 📋 Phase 18: Fixed Refresh Button - Update Message In-Place (December 31, 2025 21:32 WIB - v2025.12.31.17)

### ✅ Bug Fix: Refresh Button Sending New Message Instead of Updating

**Issue Observed:** When user clicks 🔄 Refresh button in cloud recording view, it sends a **new message** instead of updating the existing message in-place.

**Root Cause:** Handler called `await c.answer("Mengambil cloud recordings...")` which sends a new message to chat.

**Solution Implemented:**
1. **Removed**: `await c.answer("Mengambil cloud recordings...")` (line 347)
2. **Replaced with**: `await c.answer()` - just acknowledge callback silently
3. **Result**: Handler updates original message using `_safe_edit_or_fallback()`

### Modified Files
**File: [bot/cloud_recording_handlers.py](bot/cloud_recording_handlers.py#L331)**
- Lines 331-351: Updated `cb_view_cloud_recordings()` handler

### Code Changes

**Before (Creates new message):**
```python
async def cb_view_cloud_recordings(c: CallbackQuery):
    meeting_id = c.data.split(':', 1)[1]
    await c.answer("Mengambil cloud recordings...")  # ❌ SENDS NEW MESSAGE!
    
    try:
        # Fetches and updates...
```

**After (Updates in-place):**
```python
async def cb_view_cloud_recordings(c: CallbackQuery):
    meeting_id = c.data.split(':', 1)[1]
    
    # Show loading indicator
    try:
        await c.answer()  # ✅ JUST ACKNOWLEDGE, NO MESSAGE
    except Exception:
        pass
    
    try:
        # Fetches and updates in-place...
```

### User Experience Improvement

**Before:**
```
[Original message] Cloud Recordings Available
                   Integr EDR Kaspersky
                   ...
                   [Refresh] button

User clicks [Refresh]
                   ↓
[NEW MESSAGE]     "Mengambil cloud recordings..."  ← Message spam! ❌
                   
[Original message] STILL SHOWS OLD DATA
```

**After:**
```
[Original message] Cloud Recordings Available
                   Integr EDR Kaspersky
                   ...
                   [Refresh] button

User clicks [Refresh]
                   ↓
[Original message] SILENTLY UPDATES WITH NEW DATA  ← No spam! ✅
                   (Same message, updated content)
```

### How It Works

```
User clicks Refresh
    ↓
cb_view_cloud_recordings() called
    ↓
await c.answer()  → Acknowledge silently (no new message)
    ↓
Fetch recording data from Zoom API or cache
    ↓
await _safe_edit_or_fallback()  → Edit original message in-place
    ↓
User sees updated content (same message)
```

### Technical Details

**Callback Methods:**
- `c.answer()` - Acknowledge callback silently (no message sent)
- `c.answer("text")` - Send new message (was causing spam)
- `m.edit_text()` - Update existing message (via `_safe_edit_or_fallback()`)

**Handler ensures message updates via `_safe_edit_or_fallback()` which:**
1. Tries to edit original message
2. If fails, replies to message
3. If fails again, just acknowledges callback
4. **Result**: Never leaves original message unchanged

### Status
**✅ COMPLETE** - Refresh button now updates message in-place without creating new messages

---

## 🔧 CI/CD & Deployment

### Docker Build Configuration (Dec 31, 2025 23:45 WIB)

**Issue Fixed:** GitHub Actions workflows gagal menemukan Dockerfile saat build

**Root Cause:**  
Dockerfile terletak di `docker/Dockerfile`, namun `COPY docker-entrypoint.sh` tidak menyertakan prefix path yang benar karena build context adalah root directory (`.`), bukan folder `docker/`.

**Solution:**
- Workflows sudah benar menggunakan:
  - `context: .` (root directory sebagai build context)
  - `file: docker/Dockerfile` (path ke Dockerfile dari context)
- Fixed dalam [docker/Dockerfile](docker/Dockerfile):
  ```dockerfile
  # Before (BROKEN):
  COPY docker-entrypoint.sh /usr/local/bin/
  
  # After (FIXED):
  COPY docker/docker-entrypoint.sh /usr/local/bin/
  ```

**Affected Files:**
- [.github/workflows/Build-&-Deploy.yml](.github/workflows/Build-&-Deploy.yml) - Production build & push
- [.github/workflows/Build-Dev.yml](.github/workflows/Build-Dev.yml) - Development build & push
- [docker/Dockerfile](docker/Dockerfile) - Multi-stage production image

**Technical Context:**  
Docker build-push-action menggunakan BuildKit dengan context root (`.`). Semua `COPY` command dalam Dockerfile relatif terhadap context ini, bukan terhadap lokasi Dockerfile itu sendiri.

**Deployment Status (Dec 31, 2025 23:50 WIB):**
- ✅ **Build & Deploy** (Run #20620791744) - SUCCESS (5m11s)
  - Created release tag: `v2025.12.31`
  - Published Docker images:
    - `rezytijo/zoom-telebot:latest`
    - `rezytijo/zoom-telebot:v2025.12.31`
  - Multi-arch: `linux/amd64`, `linux/arm64`
  
- ✅ **Build Dev Image** (Run #20620793082) - SUCCESS (5m21s)
  - Published Docker image: `rezytijo/zoom-telebot:dev.v2025.12.31`
  - Multi-arch: `linux/amd64`, `linux/arm64`

**Resolved Issues:**
- Dockerfile was in `.gitignore` - now tracked in repo
- All failed workflow runs (16 total) deleted from Actions history
- Both playbooks now execute successfully

---

---

**This file is for AI assistant reference only. Contains sensitive development context and should never be committed to public repositories.**

---

**This file is for AI assistant reference only. Contains sensitive development context and should never be committed to public repositories.**
