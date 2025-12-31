"""Background Tasks for Zoom Bot
Handles periodic updates like cloud recording fetching, expired meeting cleanup, etc.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from zoom import zoom_client
from db import list_meetings, update_meeting_cloud_recording_data, get_meeting_cloud_recording_data, update_meeting_status

logger = logging.getLogger(__name__)


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


# Global instance
bg_task_manager = BackgroundTaskManager()


async def start_background_tasks():
    """Start background tasks (call this on bot startup)."""
    await bg_task_manager.start()


async def stop_background_tasks():
    """Stop background tasks (call this on bot shutdown)."""
    await bg_task_manager.stop()
