"""
Database-backed FSM storage for aiogram.
Persists user session state across bot restarts.

v2026-01-08: Add TTL expiry (default 5 minutes) so stale
FSM states are cleared automatically and won't disturb other
bot interactions when users leave a flow mid-way.
"""
import json
import logging
from typing import Any, Dict, Optional
import aiosqlite
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.state import State
from datetime import datetime, timezone
from config import settings

logger = logging.getLogger(__name__)


class DatabaseFSMStorage(BaseStorage):
    """FSM storage backed by SQLite database."""

    def __init__(self, db_path: str):
        """Initialize database FSM storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        # TTL in seconds; default 300s (5 minutes)
        # Configurable via settings.fsm_ttl_seconds if present
        self.ttl_seconds: int = getattr(settings, 'fsm_ttl_seconds', 300) or 300

    async def set_state(self, key: StorageKey, state: Optional[State]) -> None:
        """Set FSM state for a user."""
        try:
            state_name = state.state if state else None
            user_id = key.user_id
            
            async with aiosqlite.connect(self.db_path) as db:
                # Get current data to preserve it
                current_data = await self._get_data(db, user_id)
                
                await db.execute(
                    """
                    INSERT OR REPLACE INTO fsm_states (user_id, state, data, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (user_id, state_name, json.dumps(current_data))
                )
                await db.commit()
            
            logger.debug("FSM state set for user %s: %s", user_id, state_name)
        except Exception as e:
            logger.error("Failed to set FSM state for user %s: %s", key.user_id, e)
            raise

    async def get_state(self, key: StorageKey) -> Optional[str]:
        """Get FSM state for a user."""
        try:
            user_id = key.user_id
            async with aiosqlite.connect(self.db_path) as db:
                # Fetch state along with updated_at to enforce TTL
                cur = await db.execute(
                    "SELECT state, updated_at FROM fsm_states WHERE user_id = ?",
                    (user_id,)
                )
                row = await cur.fetchone()
                state = None
                if row:
                    state_val, updated_at = row[0], row[1]
                    if not self._is_expired(updated_at):
                        state = state_val
                    else:
                        await db.execute("DELETE FROM fsm_states WHERE user_id = ?", (user_id,))
                        await db.commit()
                logger.debug("FSM state retrieved for user %s: %s", user_id, state)
                return state
        except Exception as e:
            logger.error("Failed to get FSM state for user %s: %s", key.user_id, e)
            return None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        """Set FSM data for a user."""
        try:
            user_id = key.user_id
            data_json = json.dumps(data)
            
            async with aiosqlite.connect(self.db_path) as db:
                # Get current state to preserve it
                current_state = await self._get_state_name(db, user_id)
                
                await db.execute(
                    """
                    INSERT OR REPLACE INTO fsm_states (user_id, state, data, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (user_id, current_state, data_json)
                )
                await db.commit()
            
            logger.debug("FSM data set for user %s: %d keys", user_id, len(data))
        except Exception as e:
            logger.error("Failed to set FSM data for user %s: %s", key.user_id, e)
            raise

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        """Get FSM data for a user."""
        try:
            user_id = key.user_id
            async with aiosqlite.connect(self.db_path) as db:
                data = await self._get_data(db, user_id)
                logger.debug("FSM data retrieved for user %s: %d keys", user_id, len(data))
                return data
        except Exception as e:
            logger.error("Failed to get FSM data for user %s: %s", key.user_id, e)
            return {}

    async def del_state(self, key: StorageKey) -> None:
        """Delete FSM state for a user."""
        try:
            user_id = key.user_id
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM fsm_states WHERE user_id = ?", (user_id,))
                await db.commit()
            logger.debug("FSM state deleted for user %s", user_id)
        except Exception as e:
            logger.error("Failed to delete FSM state for user %s: %s", key.user_id, e)
            raise

    async def del_data(self, key: StorageKey) -> None:
        """Delete FSM data for a user."""
        # In our implementation, deleting data means setting it to empty dict
        await self.set_data(key, {})

    async def close(self) -> None:
        """Close storage connection."""
        # SQLite doesn't require explicit close in aiosqlite
        logger.info("Database FSM storage closed")

    # Helper methods
    async def _get_data(self, db: aiosqlite.Connection, user_id: int) -> Dict[str, Any]:
        """Get data for a user from database."""
        try:
            cur = await db.execute(
                "SELECT data, updated_at FROM fsm_states WHERE user_id = ?",
                (user_id,)
            )
            row = await cur.fetchone()
            if row:
                data_json, updated_at = row[0], row[1]
                if self._is_expired(updated_at):
                    await db.execute("DELETE FROM fsm_states WHERE user_id = ?", (user_id,))
                    await db.commit()
                    return {}
                if data_json:
                    return json.loads(data_json)
            return {}
        except Exception as e:
            logger.error("Failed to retrieve FSM data from DB for user %s: %s", user_id, e)
            return {}

    async def _get_state_name(self, db: aiosqlite.Connection, user_id: int) -> Optional[str]:
        """Get state name for a user from database."""
        try:
            cur = await db.execute(
                "SELECT state, updated_at FROM fsm_states WHERE user_id = ?",
                (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            state_val, updated_at = row[0], row[1]
            if self._is_expired(updated_at):
                await db.execute("DELETE FROM fsm_states WHERE user_id = ?", (user_id,))
                await db.commit()
                return None
            return state_val
        except Exception as e:
            logger.error("Failed to retrieve FSM state from DB for user %s: %s", user_id, e)
            return None

    def _is_expired(self, updated_at_value: Optional[str]) -> bool:
        """Return True if the row timestamp is older than TTL seconds.

        updated_at is stored as TEXT like 'YYYY-MM-DD HH:MM:SS' (UTC).
        """
        if not updated_at_value:
            return False
        try:
            # SQLite CURRENT_TIMESTAMP yields UTC in 'YYYY-MM-DD HH:MM:SS'
            ts = datetime.strptime(str(updated_at_value), "%Y-%m-%d %H:%M:%S")
            # Treat as UTC
            ts = ts.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = (now - ts).total_seconds()
            return diff > float(self.ttl_seconds)
        except Exception:
            # On parse error, do not expire to avoid accidental data loss
            return False
