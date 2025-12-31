-- Zoom-Telebot SOC - Database Schema
-- Database Version: v2.0 (Cloud Recording Support)
-- Last Updated: December 31, 2025 20:09 WIB
-- Status: ✅ Production Ready
-- 
-- IMPORTANT: This file is schema-only (no data).
-- For migration details, see: ../docs/DATABASE_MIGRATIONS.md
-- For data migrations, see: ../scripts/migrate_shorteners.py
-- 
-- This schema is automatically deployed via db/db.py:init_db()
-- Migrations are automatically applied on bot startup

-- ==================================================
-- TABLE: users
-- PURPOSE: Telegram user access control and profiles
-- ==================================================
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,           -- Telegram user ID
    username TEXT,                         -- Telegram username
    status TEXT DEFAULT 'pending',         -- pending, whitelisted, banned
    role TEXT DEFAULT 'guest'              -- guest, user, admin, owner
);

-- ==================================================
-- TABLE: meetings
-- PURPOSE: Zoom meetings with cloud recording metadata
-- LATEST: v2.0 - Added cloud_recording_data (Dec 31, 2025)
-- ==================================================
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zoom_meeting_id TEXT UNIQUE,           -- Zoom meeting ID (unique key)
    topic TEXT,                            -- Meeting title
    start_time TEXT,                       -- ISO 8601 timestamp
    join_url TEXT,                         -- Zoom join URL
    status TEXT DEFAULT 'active',          -- active, deleted, expired
    created_by TEXT,                       -- telegram_id or "CreatedFromZoomApp"
    cloud_recording_data TEXT,             -- ✨ NEW v2.0: JSON blob with recording info
                                           -- Structure: {share_url, recording_files[], total_size, recording_count, last_checked}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==================================================
-- TABLE: meeting_live_status
-- PURPOSE: Track live meeting and recording status
-- LATEST: v1.1 - Added agent_id (Dec 2025)
-- ==================================================
CREATE TABLE IF NOT EXISTS meeting_live_status (
    zoom_meeting_id TEXT PRIMARY KEY,      -- FK to meetings.zoom_meeting_id
    live_status TEXT DEFAULT 'not_started', -- not_started, started, ended
    recording_status TEXT DEFAULT 'stopped', -- stopped, recording, paused
    recording_started_at TIMESTAMP,        -- First time recording was started
    agent_id INTEGER,                      -- ✨ NEW v1.1: Agent used for this meeting (FK to agents.id)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==================================================
-- TABLE: shortlinks
-- PURPOSE: URL shortener results for meeting sharing
-- ==================================================
CREATE TABLE IF NOT EXISTS shortlinks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_url TEXT NOT NULL,            -- Long Zoom URL
    short_url TEXT,                        -- Shortened URL from provider
    provider TEXT NOT NULL,                -- tinyurl, bitly, s.id, etc.
    custom_alias TEXT,                    -- User-provided custom alias
    zoom_meeting_id TEXT,                  -- FK to meetings.zoom_meeting_id (NULL if not for meeting)
    status TEXT DEFAULT 'active',          -- active, failed, deleted
    created_by INTEGER,                    -- Telegram ID of creator
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT                     -- Error if creation failed
);

-- ==================================================
-- TABLE: agents
-- PURPOSE: C2 agent information for remote control
-- ==================================================
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- Agent name/identifier
    base_url TEXT NOT NULL,                -- Agent API base URL
    api_key TEXT,                          -- API key for authentication
    os_type TEXT,                          -- Windows, Linux, macOS, etc.
    last_seen TIMESTAMP,                   -- Last heartbeat/activity
    hostname TEXT,                         -- Machine hostname
    ip_address TEXT,                       -- Agent IP address
    version TEXT DEFAULT 'v1.0'            -- Agent software version
);

-- ==================================================
-- TABLE: agent_commands
-- PURPOSE: Command queue for agent execution
-- ==================================================
CREATE TABLE IF NOT EXISTS agent_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,             -- FK to agents.id
    action TEXT NOT NULL,                  -- Command action (e.g., 'start_recording')
    payload TEXT,                          -- JSON parameters for command
    status TEXT DEFAULT 'pending',         -- pending, running, done, failed
    result TEXT,                           -- JSON result or error message
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==================================================
-- TABLE: fsm_states
-- PURPOSE: Persistent conversation state (aiogram FSM)
-- ==================================================
CREATE TABLE IF NOT EXISTS fsm_states (
    user_id INTEGER PRIMARY KEY,           -- Telegram user ID
    state TEXT,                            -- FSM state (e.g., 'ShortenerStates:waiting_for_url')
    data TEXT,                             -- JSON state context data
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==================================================
-- INDEXES (Performance Optimization)
-- ==================================================

-- Index on telegram_id for fast user lookups
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);

-- Index on zoom_meeting_id for meeting searches
CREATE INDEX IF NOT EXISTS idx_meetings_zoom_id ON meetings(zoom_meeting_id);

-- Index on meeting status for filtering
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(status);

-- Index on created_by for user-specific queries
CREATE INDEX IF NOT EXISTS idx_meetings_created_by ON meetings(created_by);

-- Index on shortlink provider for statistics
CREATE INDEX IF NOT EXISTS idx_shortlinks_provider ON shortlinks(provider);

-- Index on shortlink status for active queries
CREATE INDEX IF NOT EXISTS idx_shortlinks_status ON shortlinks(status);

-- Index on agent_id for command filtering
CREATE INDEX IF NOT EXISTS idx_commands_agent_id ON agent_commands(agent_id);

-- Index on command status for pending queries
CREATE INDEX IF NOT EXISTS idx_commands_status ON agent_commands(status);

-- ==================================================
-- MIGRATION HISTORY
-- ==================================================
-- 
-- Migration 1: Added agent_id to meeting_live_status
--   - Date: December 2025
--   - Type: Additive (safe)
--   - Status: Applied
-- 
-- Migration 2: Added cloud_recording_data to meetings
--   - Date: December 31, 2025 20:09 WIB
--   - Type: Additive (safe)
--   - Status: Applied
--   - Rationale: Enable caching of cloud recording URLs from Zoom API
--   - Background Task: Syncs every 30 minutes
-- 
-- ===================================================


-- Agents table
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
);

-- Agent commands table
CREATE TABLE IF NOT EXISTS agent_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    payload TEXT,
    status TEXT DEFAULT 'pending',
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FSM states table
CREATE TABLE IF NOT EXISTS fsm_states (
    user_id INTEGER PRIMARY KEY,
    state TEXT,
    data TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
