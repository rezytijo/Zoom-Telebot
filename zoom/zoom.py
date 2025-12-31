import time
import base64
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from config import settings
import logging


class ZoomClient:
    def __init__(self):
        self._token: Optional[str] = None
        self._token_exp: float = 0
        self._token_lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)

    async def _get_jwt_token(self) -> str:
        # Acquire lock to avoid concurrent token fetches
        async with self._token_lock:
            # Return cached token if still valid (buffer 30s)
            if self._token and time.time() < self._token_exp - 30:
                self.logger.debug("Using cached Zoom token, expires in %s seconds", int(self._token_exp - time.time()))
                return self._token

            # Build Basic auth header by base64 encoding client_id:client_secret
            client_id = settings.zoom_client_id
            client_secret = settings.zoom_client_secret
            if not client_id or not client_secret:
                self.logger.error("Zoom client credentials missing")
                raise RuntimeError("Zoom client credentials not configured (ZOOM_CLIENT_ID / ZOOM_CLIENT_SECRET)")

            basic_raw = f"{client_id}:{client_secret}".encode('utf-8')
            basic_b64 = base64.b64encode(basic_raw).decode('ascii')

            token_url = "https://zoom.us/oauth/token"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic_b64}",
            }

            # Prefer server-to-server (S2S) OAuth using the account_credentials grant
            # when an account id is configured (this matches Zoom internal apps / S2S flow).
            # Fallback to client_credentials only when no account id is provided.
            if settings.zoom_account_id:
                data = {"grant_type": "account_credentials", "account_id": str(settings.zoom_account_id)}
                self.logger.debug("Requesting Zoom S2S token using account_credentials for account_id=%s", settings.zoom_account_id)
            else:
                data = {"grant_type": "client_credentials"}
                self.logger.debug("Requesting Zoom token using client_credentials (no account_id configured)")

            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=data, headers=headers) as resp:
                    text = await resp.text()
                    # attempt to decode JSON body if possible
                    try:
                        j = await resp.json()
                    except Exception:
                        j = {}

                    # log full response at debug level for diagnostics
                    self.logger.debug("Zoom token endpoint response status=%s body=%s json=%s", resp.status, text, j)

                    if resp.status >= 400:
                        self.logger.error("Zoom token endpoint returned %s: %s", resp.status, text)
                        raise RuntimeError(f"Zoom token error {resp.status}: {text}")
                    access_token = j.get("access_token")
                    expires_in = j.get("expires_in", 3600)
                    if not access_token:
                        self.logger.error("Zoom token response missing access_token: %s", j)
                        raise RuntimeError(f"Zoom token response missing access_token: {j}")
                    self._token = access_token
                    self._token_exp = time.time() + int(expires_in)
                    self.logger.info("Obtained new Zoom token, expires in %s seconds", int(expires_in))
                    return access_token

    async def fetch_token_info(self) -> Dict[str, Any]:
        """Fetch the token endpoint and return the raw response for diagnostics.

        This does not alter the cached token state; it's intended for debugging.
        Returns a dict containing: status, text, json (if decodable), requested_data
        """
        client_id = settings.zoom_client_id
        client_secret = settings.zoom_client_secret
        if not client_id or not client_secret:
            raise RuntimeError("Zoom client credentials missing")

        basic_raw = f"{client_id}:{client_secret}".encode('utf-8')
        basic_b64 = base64.b64encode(basic_raw).decode('ascii')

        token_url = "https://zoom.us/oauth/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic_b64}",
        }

        if settings.zoom_account_id:
            data = {"grant_type": "account_credentials", "account_id": str(settings.zoom_account_id)}
        else:
            data = {"grant_type": "client_credentials"}

        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=data, headers=headers) as resp:
                text = await resp.text()
                try:
                    j = await resp.json()
                except Exception:
                    j = None

                return {
                    "status": resp.status,
                    "text": text,
                    "json": j,
                    "requested_data": data,
                }

    def is_token_valid(self) -> bool:
        """Return True if cached token exists and not expired (with 30s buffer)."""
        return bool(self._token and time.time() < self._token_exp - 30)

    async def ensure_token(self) -> str:
        """Ensure a valid token is available and return it; refresh if needed."""
        if self.is_token_valid():
            assert self._token is not None
            return self._token
        return await self._get_jwt_token()

    async def get_meeting(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Get meeting details from Zoom API.
        
        Returns meeting info including status, or None if not found.
        """
        self.logger.debug("Getting meeting details for %s", meeting_id)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/meetings/{meeting_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.logger.debug("Meeting %s details retrieved", meeting_id)
                    return data
                elif resp.status == 404:
                    self.logger.warning("Meeting %s not found", meeting_id)
                    return None
                else:
                    text = await resp.text()
                    self.logger.error("Failed to get meeting %s: %s - %s", meeting_id, resp.status, text)
                    return None

    async def get_meeting_recording_status(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Get recording status for a meeting from Zoom API.
        
        Returns recording information if available, or None.
        Note: This gets completed recordings, not real-time recording status.
        """
        self.logger.debug("Getting recording status for meeting %s", meeting_id)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/meetings/{meeting_id}/recordings"
        headers = {"Authorization": f"Bearer {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.logger.debug("Recording status for meeting %s retrieved", meeting_id)
                    return data
                elif resp.status == 404:
                    self.logger.debug("No recordings found for meeting %s", meeting_id)
                    return None
                else:
                    text = await resp.text()
                    self.logger.warning("Failed to get recording status for meeting %s: %s - %s", meeting_id, resp.status, text)
                    return None


    async def create_meeting(self, user_id: Optional[str] = "me", topic: str = "Meeting from Bot", start_time: Optional[str] = None, duration: int = 120) -> Dict[str, Any]:
        self.logger.info("Creating meeting for user_id=%s topic=%s start_time=%s", user_id, topic, start_time)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/users/{user_id}/meetings"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        # build payload following user-provided structure
        payload: Dict[str, Any] = {
            "topic": topic,
            "default_password": True,
            "duration": duration,
        }
        if start_time:
            # Zoom expects start_time in ISO8601 (UTC or with offset)
            payload["start_time"] = start_time
        payload["timezone"] = "Asia/Jakarta"
        # sensible settings per user's request
        auto_recording_mode = "cloud"
        if getattr(settings, "zoom_control_mode", "cloud").lower() == "agent":
            auto_recording_mode = "local"

        payload["settings"] = {
            "host_video": True,
            "participant_video": True,
            "join_before_host": False,
            "mute_upon_entry": True,
            "waiting_room": False,
            "auto_start_ai_companion_questions": True,
            "auto_recording": auto_recording_mode,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    self.logger.error("Zoom create_meeting returned %s: %s", resp.status, text)
                    raise RuntimeError(f"Zoom API error {resp.status}: {text}")
                return await resp.json()

    async def list_upcoming_meetings(self, user_id: Optional[str] = "me") -> Dict[str, Any]:
        from datetime import datetime, timedelta, timezone
        self.logger.debug("Listing upcoming meetings for user %s", user_id)
        token = await self.ensure_token()
        
        # Get current time in UTC, then convert to Asia/Jakarta timezone
        now_utc = datetime.now(timezone.utc)
        jakarta_tz = timezone(timedelta(hours=7))  # UTC+7
        now_jakarta = now_utc.astimezone(jakarta_tz)
        
        # Start from 00:00:00 of current day (in Jakarta time) to show all meetings from midnight
        today_start = now_jakarta.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Convert back to UTC for API (Zoom API expects UTC)
        from_date = today_start.astimezone(timezone.utc).isoformat()
        to_date = (today_start + timedelta(days=30)).astimezone(timezone.utc).isoformat()
        
        self.logger.debug("Meeting range: from %s to %s (Jakarta time: %s to %s)", 
                         from_date, to_date, today_start.isoformat(), 
                         (today_start + timedelta(days=30)).isoformat())
        
        params = {
            'type': 'scheduled',
            'page_size': 30,
            'from': from_date,
            'to': to_date
        }
        url = f"{settings.zoom_audience}/v2/users/{user_id}/meetings"
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    self.logger.error("Zoom list_meetings returned %s: %s", resp.status, text)
                    raise RuntimeError(f"Zoom API error {resp.status}: {text}")
                data = await resp.json()
                self.logger.debug("Received meetings: %s", data)
                return data

    async def get_short_url(self, meeting: Dict[str, Any]) -> str:
        # Zoom doesn't provide a 'short url' directly in API; we return join_url
        return meeting.get("join_url") or meeting.get("start_url") or ""

    async def delete_meeting(self, meeting_id: str) -> bool:
        self.logger.info("Deleting meeting meeting_id=%s", meeting_id)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/meetings/{meeting_id}"
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers) as resp:
                if resp.status == 204:
                    self.logger.info("Meeting %s deleted successfully", meeting_id)
                    return True
                elif resp.status >= 400:
                    text = await resp.text()
                    self.logger.error("Zoom delete_meeting returned %s: %s", resp.status, text)
                    raise RuntimeError(f"Zoom API error {resp.status}: {text}")
                else:
                    self.logger.warning("Unexpected status %s for delete_meeting %s", resp.status, meeting_id)
                    return False

    async def update_meeting(self, meeting_id: str, topic: str | None = None, start_time: str | None = None) -> Dict[str, Any]:
        """Patch/update a meeting's topic and/or start_time via Zoom API.

        This uses the PATCH /meetings/{meetingId} endpoint.
        """
        self.logger.info("Updating meeting %s topic=%s start_time=%s", meeting_id, topic, start_time)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/meetings/{meeting_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        payload: Dict[str, Any] = {}
        if topic is not None:
            payload["topic"] = topic
        if start_time is not None:
            payload["start_time"] = start_time
            payload["timezone"] = "Asia/Jakarta"

        if not payload:
            raise RuntimeError("No fields provided to update")

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    self.logger.error("Zoom update_meeting returned %s: %s", resp.status, text)
                    raise RuntimeError(f"Zoom API error {resp.status}: {text}")
                # Zoom returns 204 No Content on success for patch; return minimal info
                if resp.status in (200, 204):
                    return {"ok": True, "status": resp.status}
                return {"ok": False, "status": resp.status, "body": text}

    async def end_meeting(self, meeting_id: str) -> bool:
        """Request Zoom to end an ongoing meeting (meeting status endpoint).

        Uses the meeting status endpoint: PUT /meetings/{meetingId}/status with {"action":"end"}.
        If not supported by account/token, falls back to deleting the meeting.
        """
        self.logger.info("Ending meeting %s via status endpoint", meeting_id)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/meetings/{meeting_id}/status"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"action": "end"}

        async with aiohttp.ClientSession() as session:
            async with session.put(url, json=payload, headers=headers) as resp:
                if resp.status in (204, 200):
                    self.logger.info("Meeting %s ended successfully via status endpoint", meeting_id)
                    return True
                # Some accounts may not support this endpoint; try delete as a fallback
                text = await resp.text()
                self.logger.warning("End meeting returned %s: %s - attempting delete as fallback", resp.status, text)
        # fallback: attempt delete
        try:
            return await self.delete_meeting(meeting_id)
        except Exception as e:
            self.logger.exception("Fallback delete failed for meeting %s: %s", meeting_id, e)
            return False


    async def start_meeting(self, meeting_id: str) -> Dict[str, Any]:
        """Start a scheduled Zoom meeting.

        Returns meeting details with start_url and join_url.
        """
        self.logger.info("Starting meeting %s", meeting_id)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/meetings/{meeting_id}/status"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"action": "start"}

        async with aiohttp.ClientSession() as session:
            async with session.put(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.logger.info("Meeting %s started successfully", meeting_id)
                    return data
                else:
                    text = await resp.text()
                    self.logger.error("Failed to start meeting %s: %s - %s", meeting_id, resp.status, text)
                    raise Exception(f"Failed to start meeting: {resp.status} - {text}")


    async def get_meeting_participants(self, meeting_id: str) -> List[Dict[str, Any]]:
        """Get list of participants in an active meeting.
        
        Uses the /live_meetings endpoint which works for live/active meetings.
        For past meetings analytics, use /metrics/meetings/{meetingId}/participants instead.
        """
        self.logger.info("Getting participants for meeting %s", meeting_id)
        token = await self.ensure_token()
        # Use /meetings endpoint with live meeting parameter for LIVE participants
        url = f"{settings.zoom_audience}/v2/meetings/{meeting_id}?type=live"
        headers = {"Authorization": f"Bearer {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # For live meetings, participants are in the 'participants' field
                    participants = data.get('participants', [])
                    self.logger.info("Retrieved %d participants for meeting %s", len(participants), meeting_id)
                    return participants
                else:
                    text = await resp.text()
                    self.logger.error("Failed to get participants for meeting %s: %s - %s", meeting_id, resp.status, text)
                    return []


    async def mute_all_participants(self, meeting_id: str) -> bool:
        """Mute all participants in an active meeting."""
        self.logger.info("Muting all participants in meeting %s", meeting_id)
        token = await self.ensure_token()
        # Use participants/status endpoint for muting all participants
        url = f"{settings.zoom_audience}/v2/meetings/{meeting_id}/participants/status"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"action": "mute"}

        async with aiohttp.ClientSession() as session:
            async with session.put(url, json=payload, headers=headers) as resp:
                if resp.status in (204, 200):
                    self.logger.info("All participants muted in meeting %s", meeting_id)
                    return True
                else:
                    text = await resp.text()
                    self.logger.error("Failed to mute all participants in meeting %s: %s - %s", meeting_id, resp.status, text)
                    return False


    async def control_live_meeting_recording(self, meeting_id: str, action: str) -> bool:
        """Control recording for a live meeting using live_meetings events API.
        
        Args:
            meeting_id: The meeting ID
            action: One of 'start', 'stop', 'pause', 'resume'
        
        Returns:
            True if successful, False otherwise
        
        API Endpoint: PATCH /live_meetings/{meetingId}/events
        """
        self.logger.info("Controlling recording for meeting %s with action %s", meeting_id, action)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/live_meetings/{meeting_id}/events"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Map action names to Zoom API format
        action_map = {
            'start': 'recording.start',
            'stop': 'recording.stop',
            'pause': 'recording.pause',
            'resume': 'recording.resume'
        }
        
        zoom_method = action_map.get(action, action)
        payload = {"method": zoom_method}

        # Log detailed API call information for debugging
        self.logger.debug("=" * 80)
        self.logger.debug("ZOOM API CALL - Recording Control")
        self.logger.debug("=" * 80)
        self.logger.debug("METHOD: PATCH")
        self.logger.debug("URL: %s", url)
        self.logger.debug("HEADERS:")
        self.logger.debug("  Authorization: Bearer %s...%s (token length: %d)", token[:10], token[-10:], len(token))
        self.logger.debug("  Content-Type: application/json")
        self.logger.debug("PAYLOAD: %s", payload)
        self.logger.debug("=" * 80)

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, json=payload, headers=headers) as resp:
                response_text = await resp.text()
                
                # Log response details
                self.logger.debug("=" * 80)
                self.logger.debug("ZOOM API RESPONSE")
                self.logger.debug("=" * 80)
                self.logger.debug("STATUS: %d", resp.status)
                self.logger.debug("HEADERS: %s", dict(resp.headers))
                self.logger.debug("BODY: %s", response_text)
                self.logger.debug("=" * 80)
                
                if resp.status in (204, 200, 202):
                    self.logger.info("Recording control %s successful for meeting %s", action, meeting_id)
                    return True
                else:
                    self.logger.error("Failed to control recording for meeting %s: %s - %s", meeting_id, resp.status, response_text)
                    return False


    async def get_live_meeting_details(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Get live meeting details including recording status.
        
        Returns meeting info with recording_status field, or None if not found.
        Uses /live_meetings/{meetingId} endpoint for real-time status.
        """
        self.logger.debug("Getting live meeting details for %s", meeting_id)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/live_meetings/{meeting_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.logger.debug("Live meeting %s details retrieved", meeting_id)
                    return data
                elif resp.status == 404:
                    self.logger.debug("Live meeting %s not found (may not be live)", meeting_id)
                    return None
                else:
                    text = await resp.text()
                    self.logger.warning("Failed to get live meeting %s: %s - %s", meeting_id, resp.status, text)
                    return None


    async def get_cloud_recording_urls(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Get cloud recording download URLs for a completed meeting.
        
        Returns dict with recording information including download_url, play_url for each file.
        Returns None if no recordings found or meeting not recorded.
        
        Zoom API Endpoint: GET /v2/meetings/{meetingId}/recordings
        
        Response includes:
        - recording_files[]: Array of recording files
          - download_url: Direct download link (expires in 24hrs)
          - play_url: Web player link
          - file_type: MP4, M4A, TIMELINE, TRANSCRIPT, CHAT, CC
          - file_size: Size in bytes
          - recording_start: Start timestamp
          - recording_end: End timestamp
        - share_url: Zoom's web page to view/download recordings
        """
        self.logger.debug("Getting cloud recording URLs for meeting %s", meeting_id)
        token = await self.ensure_token()
        url = f"{settings.zoom_audience}/v2/meetings/{meeting_id}/recordings"
        headers = {"Authorization": f"Bearer {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.logger.debug("Cloud recordings for meeting %s retrieved: %d files", 
                                     meeting_id, len(data.get('recording_files', [])))
                    return data
                elif resp.status == 404:
                    self.logger.debug("No cloud recordings found for meeting %s", meeting_id)
                    return None
                else:
                    text = await resp.text()
                    self.logger.warning("Failed to get cloud recordings for meeting %s: %s - %s", 
                                       meeting_id, resp.status, text)
                    return None


zoom_client = ZoomClient()
