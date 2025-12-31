-- ================================================================
-- Zoom-Telebot SOC - Database Schema Backup
-- ================================================================
-- Created: December 31, 2025 10:00 WIB
-- Version: v2025.12.31.0
-- Purpose: Schema-only backup before adding new features
-- Database: SQLite 3
-- Tables: 7
-- ================================================================

-- ================================================================
-- TABLE 1: users - User Management & Access Control
-- ================================================================
-- Purpose: Store Telegram users with role-based access control
-- Status Flow: pending → whitelisted OR banned
-- ================================================================

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE,
    username TEXT,
    status TEXT DEFAULT 'pending',      -- pending, whitelisted, banned
    role TEXT DEFAULT 'guest'            -- guest, user, owner
);

-- ================================================================
-- TABLE 2: meetings - Zoom Meeting Storage
-- ================================================================
-- Purpose: Store all Zoom meetings with sync tracking
-- Status Flow: active → deleted OR expired
-- Cloud Recording: cloud_recording_data stored as JSON (fetched by background task)
-- ================================================================

CREATE TABLE IF NOT EXISTS meetings (
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
);

-- ================================================================
-- TABLE 3: meeting_live_status - Real-time Meeting & Recording Status
-- ================================================================
-- Purpose: Track live meeting status and recording state
-- Note: Zoom API does NOT provide real-time recording status
--       We track it in database (updated via bot UI buttons)
-- ================================================================

CREATE TABLE IF NOT EXISTS meeting_live_status (
    zoom_meeting_id TEXT PRIMARY KEY,
    live_status TEXT DEFAULT 'not_started',     -- not_started, started, ended
    recording_status TEXT DEFAULT 'stopped',    -- stopped, recording, paused
    recording_started_at TIMESTAMP,              -- First recording start timestamp
    agent_id INTEGER,                           -- Agent controlling this meeting
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (zoom_meeting_id) REFERENCES meetings(zoom_meeting_id)
);

-- ================================================================
-- TABLE 4: shortlinks - URL Shortener History & Tracking
-- ================================================================
-- Purpose: Track all shortened URLs with multi-provider support
-- Providers: TinyURL, S.id, Bitly, etc
-- ================================================================

CREATE TABLE IF NOT EXISTS shortlinks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_url TEXT NOT NULL,
    short_url TEXT,
    provider TEXT NOT NULL,             -- tinyurl, sid, bitly, etc
    custom_alias TEXT,                  -- User's custom alias (provider-dependent)
    zoom_meeting_id TEXT,               -- Foreign key to meetings (NULL for non-meeting URLs)
    status TEXT DEFAULT 'active',       -- active, failed, deleted
    created_by INTEGER,                 -- telegram_id of creator
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,                 -- Detailed error if creation failed
    FOREIGN KEY (zoom_meeting_id) REFERENCES meetings(zoom_meeting_id)
);

-- ================================================================
-- TABLE 5: agents - Remote Control Agent Registry
-- ================================================================
-- Purpose: Track remote agents for meeting control (C2 system)
-- Online Detection: last_seen < 5 minutes = Online
-- ================================================================

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

-- ================================================================
-- TABLE 6: agent_commands - Remote Command Queue (C2)
-- ================================================================
-- Purpose: Queue and track remote commands sent to agents
-- Lifecycle: pending → running → done OR failed
-- Timeout: 60 seconds (auto-marked as failed)
-- ================================================================

CREATE TABLE IF NOT EXISTS agent_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    action TEXT NOT NULL,               -- start_recording, stop_recording, etc
    payload TEXT,                       -- JSON command data/arguments
    status TEXT DEFAULT 'pending',      -- pending, running, done, failed
    result TEXT,                        -- Command execution result/output
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- ================================================================
-- TABLE 7: fsm_states - Persistent User Sessions
-- ================================================================
-- Purpose: Persist user conversation state across bot restarts
-- Benefit: Users resume exactly where they left off
-- Implementation: Custom DatabaseFSMStorage class
-- ================================================================

CREATE TABLE IF NOT EXISTS fsm_states (
    user_id INTEGER PRIMARY KEY,
    state TEXT,                         -- Current FSM state name
    data TEXT,                          -- JSON-encoded FSM context data
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================================================
-- INDEXES (Performance Optimization)
-- ================================================================

-- Users table indexes
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

-- Meetings table indexes
CREATE INDEX IF NOT EXISTS idx_meetings_zoom_id ON meetings(zoom_meeting_id);
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(status);
CREATE INDEX IF NOT EXISTS idx_meetings_created_by ON meetings(created_by);
CREATE INDEX IF NOT EXISTS idx_meetings_start_time ON meetings(start_time);

-- Meeting live status indexes
CREATE INDEX IF NOT EXISTS idx_meeting_live_status_zoom_id ON meeting_live_status(zoom_meeting_id);
CREATE INDEX IF NOT EXISTS idx_meeting_live_status_agent_id ON meeting_live_status(agent_id);

-- Shortlinks table indexes
CREATE INDEX IF NOT EXISTS idx_shortlinks_zoom_meeting_id ON shortlinks(zoom_meeting_id);
CREATE INDEX IF NOT EXISTS idx_shortlinks_created_by ON shortlinks(created_by);
CREATE INDEX IF NOT EXISTS idx_shortlinks_status ON shortlinks(status);
CREATE INDEX IF NOT EXISTS idx_shortlinks_provider ON shortlinks(provider);

-- Agents table indexes
CREATE INDEX IF NOT EXISTS idx_agents_last_seen ON agents(last_seen);

-- Agent commands table indexes
CREATE INDEX IF NOT EXISTS idx_agent_commands_agent_id ON agent_commands(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_commands_status ON agent_commands(status);
CREATE INDEX IF NOT EXISTS idx_agent_commands_created_at ON agent_commands(created_at);

-- FSM states table indexes
CREATE INDEX IF NOT EXISTS idx_fsm_states_user_id ON fsm_states(user_id);

-- ================================================================
-- DATABASE STATISTICS
-- ================================================================
-- Total Tables: 7
-- Total Indexes: 14 (performance optimization)
-- Total Foreign Keys: 3 (referential integrity)
-- 
-- Key Relationships:
-- - meeting_live_status.zoom_meeting_id → meetings.zoom_meeting_id
-- - shortlinks.zoom_meeting_id → meetings.zoom_meeting_id
-- - agent_commands.agent_id → agents.id
-- ================================================================

-- ================================================================
-- MIGRATION NOTES
-- ================================================================
-- This schema represents the current state as of December 31, 2025
-- 
-- Recent Migrations:
-- 1. Added agent_id column to meeting_live_status (v2.3.0)
-- 2. Migrated recording_status from meetings to meeting_live_status (v2.3.0)
-- 3. Added recording_started_at column to meeting_live_status (v2.3.0)
-- 4. Changed created_by from INTEGER to TEXT in meetings (v2.4.0)
-- 5. Added fsm_states table for persistent sessions (v2.4.0)
-- 
-- Migration Strategy:
-- - Auto-migration on bot startup via init_db() and run_migrations()
-- - Non-destructive (uses ALTER TABLE to preserve existing data)
-- - Defined in db/db.py CREATE_SQL array and run_migrations() function
-- ================================================================

-- ================================================================
-- RESTORE INSTRUCTIONS
-- ================================================================
-- To restore this schema to a new database:
-- 
-- 1. Using SQLite CLI:
--    sqlite3 bot.db < database_schema_backup_2025-12-31.sql
-- 
-- 2. Using Python:
--    import sqlite3
--    conn = sqlite3.connect('bot.db')
--    with open('database_schema_backup_2025-12-31.sql', 'r') as f:
--        conn.executescript(f.read())
--    conn.close()
-- 
-- 3. Using bot's restore function:
--    Use /restore command in Telegram bot
-- ================================================================

-- End of schema backup
