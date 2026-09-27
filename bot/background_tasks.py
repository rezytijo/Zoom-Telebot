"""Background Tasks for Zoom Bot
Handles periodic updates like cloud recording fetching, expired meeting cleanup, etc.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from zoom import zoom_client
from db import list_meetings, update_meeting_cloud_recording_data, get_meeting_cloud_recording_data, update_meeting_status, list_meetings_pending_launch, mark_remote_launch_failed, update_meeting_live_status
from config import settings

logger = logging.getLogger(__name__)

def _as_utc_naive(dt) -> datetime:
    """Normalise a DB timestamp to a naive UTC datetime.

    SQLite CURRENT_TIMESTAMP is UTC, but the host clock is local (Asia/Jakarta by
    default). Subtracting a naive local `datetime.now()` from a naive UTC value
    inflates the age by the UTC offset - 7 hours here - so every pending launch
    looked instantly timed out. Normalising both sides to UTC is what makes the
    comparison mean the same thing regardless of the host timezone.
    """
    if dt.tzinfo is None:
        return dt  # already naive UTC from SQLite
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class BackgroundTaskManager:
    """Manages background tasks for the bot."""
    
    def __init__(self):
        self.is_running = False
        self.tasks = []
        
    async def start(self):
        """Start all background tasks."""
        if self.is_running:
            logger.warning("Background tasks already running")
            return
        
        self.is_running = True
        logger.info("Starting background tasks")
        
        # Create tasks
        self.tasks = [
            asyncio.create_task(self._periodic_cloud_recording_sync()),
            asyncio.create_task(self._periodic_cleanup()),
            asyncio.create_task(self._host_confirmation_watch()),
        ]
        
        logger.info("Background tasks started: %d tasks", len(self.tasks))
    
    async def stop(self):
        """Stop all background tasks."""
        if not self.is_running:
            logger.warning("Background tasks not running")
            return
        
        self.is_running = False
        logger.info("Stopping background tasks")
        
        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self.tasks = []
        logger.info("Background tasks stopped")
    
    async def _periodic_cloud_recording_sync(self):
        """Periodically check for cloud recordings and update database.
        
        Runs every 30 minutes.
        Skips recordings that were checked less than 1 hour ago (to avoid excessive API calls).
        """
        logger.info("Cloud Recording Sync task started (interval: 30 minutes)")
        
        while self.is_running:
            try:
                await asyncio.sleep(1800)  # 30 minutes
                
                logger.debug("Running periodic cloud recording sync")
                
                meetings = await list_meetings()
                logger.debug("Found %d meetings for cloud recording check", len(meetings))
                
                for meeting in meetings:
                    if not self.is_running:
                        break
                    
                    zoom_meeting_id = meeting.get('zoom_meeting_id')
                    status = meeting.get('status')
                    
                    # Only check completed or expired meetings (not active)
                    if status not in ['expired', 'deleted', 'completed']:
                        logger.debug("Skipping meeting %s: status=%s", zoom_meeting_id, status)
                        continue
                    
                    try:
                        # Get cached recording data
                        cached_data = await get_meeting_cloud_recording_data(zoom_meeting_id)
                        
                        # Check if we should refresh (if last checked was > 1 hour ago)
                        if cached_data and cached_data.get('last_checked'):
                            try:
                                last_checked = datetime.fromisoformat(cached_data['last_checked'])
                                if datetime.now() - last_checked < timedelta(hours=1):
                                    logger.debug("Meeting %s: cached recording data still fresh", zoom_meeting_id)
                                    continue
                            except Exception as e:
                                logger.debug("Error parsing last_checked: %s", e)
                        
                        # Fetch cloud recording data from Zoom API
                        logger.debug("Fetching cloud recordings for meeting %s", zoom_meeting_id)
                        recording_data = await zoom_client.get_cloud_recording_urls(zoom_meeting_id)
                        
                        if recording_data:
                            # Add last_checked timestamp
                            recording_data['last_checked'] = datetime.now().isoformat()
                            
                            # Save to database
                            await update_meeting_cloud_recording_data(zoom_meeting_id, recording_data)
                            
                            recording_count = recording_data.get('recording_count', 0)
                            logger.info("Meeting %s: cloud recordings found (%d files)", 
                                       zoom_meeting_id, recording_count)
                        else:
                            # No recordings yet, but still update timestamp to avoid excessive API calls
                            if cached_data:
                                cached_data['last_checked'] = datetime.now().isoformat()
                                await update_meeting_cloud_recording_data(zoom_meeting_id, cached_data)
                            
                            logger.debug("Meeting %s: no cloud recordings available yet", zoom_meeting_id)
                    
                    except Exception as e:
                        logger.error("Error fetching cloud recordings for meeting %s: %s", zoom_meeting_id, e)
                
                logger.debug("Periodic cloud recording sync completed")
            
            except asyncio.CancelledError:
                logger.info("Cloud Recording Sync task cancelled")
                break
            except Exception as e:
                logger.exception("Error in cloud recording sync task: %s", e)
                # Continue running despite errors
    
    async def _periodic_cleanup(self):
        """Periodically clean up old/expired meetings.
        
        Runs every 6 hours.
        Deletes cloud recording data for meetings older than 30 days.
        """
        logger.info("Cleanup task started (interval: 6 hours)")
        
        while self.is_running:
            try:
                await asyncio.sleep(21600)  # 6 hours
                
                logger.debug("Running periodic cleanup")
                
                meetings = await list_meetings()
                logger.debug("Found %d meetings for cleanup check", len(meetings))
                
                cutoff_date = datetime.now() - timedelta(days=30)
                cleanup_count = 0
                
                for meeting in meetings:
                    if not self.is_running:
                        break
                    
                    zoom_meeting_id = meeting.get('zoom_meeting_id')
                    created_at_str = meeting.get('created_at')
                    
                    if not created_at_str:
                        continue
                    
                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                        
                        if created_at < cutoff_date:
                            # Clear cloud recording data for old meetings
                            cached_data = await get_meeting_cloud_recording_data(zoom_meeting_id)
                            if cached_data:
                                await update_meeting_cloud_recording_data(zoom_meeting_id, None)
                                cleanup_count += 1
                                logger.debug("Cleared cloud recording data for old meeting %s", zoom_meeting_id)
                    
                    except Exception as e:
                        logger.warning("Error processing meeting %s for cleanup: %s", zoom_meeting_id, e)
                
                logger.info("Periodic cleanup completed: cleared %d old meeting records", cleanup_count)
            
            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled")
                break
            except Exception as e:
                logger.exception("Error in cleanup task: %s", e)
                # Continue running despite errors

    async def _host_confirmation_watch(self):
        """Advance launch_requested -> started without depending on the Zoom webhook.

        The remote controller reports "opened" the moment xdg-open spawns, which
        proves nothing about whether the host actually joined. Until a Zoom
        webhook is configured the bot has no other way to learn that, so this
        polls the Zoom API directly and stamps the transition itself.

        Without this, launch_requested meetings sit forever indistinguishable
        from never-launched ones: get_meeting_live_status() returns the raw
        column, and the operator's "Cek Status" button never changes.
        """
        logger.info("Host confirmation watcher started")
        try:
            while self.is_running:
                try:
                    rows = await list_meetings_pending_launch()
                    for row in rows:
                        if not self.is_running:
                            break
                        await self._confirm_one(row)
                except asyncio.CancelledError:
                    logger.info("Host confirmation watcher cancelled")
                    break
                except Exception as e:
                    logger.exception("Error in host confirmation loop: %s", e)

                # 10s keeps the button responsive without hammering the Zoom API.
                await asyncio.sleep(10)
        finally:
            logger.info("Host confirmation watcher stopped")

    async def _confirm_one(self, row: Dict):
        """Poll one pending launch until it starts, fails, or times out."""
        meeting_id = row["zoom_meeting_id"]
        try:
            meeting_data = await zoom_client.get_meeting(meeting_id)
        except Exception as e:
            # A transient Zoom API error must not abandon the launch. The meeting
            # stays launch_requested and is retried on the next tick; the timeout
            # in the DB is what eventually gives up on it.
            logger.debug("Host confirm poll failed for %s: %s", meeting_id, type(e).__name__)
            return

        if not meeting_data:
            await mark_remote_launch_failed(meeting_id, "meeting_not_found")
            return

        status = meeting_data.get("status", "unknown")
        if status == "started":
            await update_meeting_live_status(meeting_id, "started")
            logger.info("Remote host joined meeting %s (Zoom reports started)", meeting_id)
            return

        if status in ("ended", "deleted"):
            await mark_remote_launch_failed(meeting_id, f"zoom_status_{status}")
            return

        # Still waiting: check whether the request has outlived its budget.
        requested_at = row.get("launch_requested_at")
        if not requested_at:
            return
        try:
            age = (datetime.now(timezone.utc).replace(tzinfo=None)
                   - _as_utc_naive(requested_at)).total_seconds()
        except (AttributeError, TypeError, ValueError):
            return
        if age > settings.zoom_remote_host_confirm_timeout:
            await mark_remote_launch_failed(meeting_id, "host_confirm_timeout")

# Global instance
bg_task_manager = BackgroundTaskManager()


async def start_background_tasks():
    """Start background tasks (call this on bot startup)."""
    await bg_task_manager.start()


async def stop_background_tasks():
    """Stop background tasks (call this on bot shutdown)."""
    await bg_task_manager.stop()
