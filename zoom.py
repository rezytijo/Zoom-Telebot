import time
import base64
import asyncio
import aiohttp
from typing import Optional, Dict, Any
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
        payload["settings"] = {
            "host_video": True,
            "participant_video": True,
            "join_before_host": False,
            "mute_upon_entry": True,
            "waiting_room": False,
            "auto_start_ai_companion_questions": True,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    self.logger.error("Zoom create_meeting returned %s: %s", resp.status, text)
                    raise RuntimeError(f"Zoom API error {resp.status}: {text}")
                return await resp.json()

    async def list_upcoming_meetings(self, user_id: Optional[str] = "me") -> Dict[str, Any]:
        from datetime import datetime, timedelta
        self.logger.debug("Listing upcoming meetings for user %s", user_id)
        token = await self.ensure_token()
        today = datetime.now().date()
        from_date = today.isoformat()
        to_date = (today + timedelta(days=30)).isoformat()
        params = {
            'type': 'scheduled',
            'page_size': 30,
            'from': from_date,
            'to': to_date,
            'timezone': 'Asia/Jakarta'
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


zoom_client = ZoomClient()
