"""Client for the internal Kasm-based Zoom host controller."""

from __future__ import annotations

from typing import Any, Dict

import aiohttp

from config import settings


class RemoteZoomError(RuntimeError):
    """Raised when the remote Zoom host rejects or cannot process a command."""


class RemoteZoomClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or settings.zoom_remote_base_url).rstrip("/")
        self.token = token if token is not None else settings.zoom_remote_api_token

    def _headers(self) -> Dict[str, str]:
        if not self.token:
            raise RemoteZoomError("ZOOM_REMOTE_API_TOKEN belum dikonfigurasi")
        return {"Authorization": f"Bearer {self.token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=settings.zoom_remote_launch_timeout)
        # Callers may add their own headers (import_session sets Content-Type),
        # so merge instead of passing a second `headers` keyword.
        headers = {**self._headers(), **(kwargs.pop("headers", None) or {})}
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                **kwargs,
            ) as response:
                try:
                    payload = await response.json()
                except Exception:
                    payload = {}
                if response.status >= 400:
                    # The host answers a rejected cookie export with web's plain
                    # text body, not JSON. Falling back to a generic "HTTP 400"
                    # would throw away the one line naming the missing cookie.
                    reason = payload.get("error") or (await response.text()).strip()
                    raise RemoteZoomError(reason or f"Remote Zoom HTTP {response.status}")
                return payload

    async def health(self) -> Dict[str, Any]:
        return await self._request("GET", "/health")

    async def status(self) -> Dict[str, Any]:
        return await self._request("GET", "/status")

    async def launch_meeting(
        self,
        meeting_id: str,
        start_url: str,
        requested_by: int,
        passcode: str | None = None,
        join_url: str | None = None,
    ) -> Dict[str, Any]:
        """Ask the remote host to open the meeting.

        start_url carries the zak host key, which only the Zoom desktop client
        understands. join_url is the public https://zoom.us/j/<id>?pwd= link,
        which a browser host can actually use. Both are sent so the same call
        works against either host: the Kasm controller reads start_url, the
        browser host reads join_url and rejects start_url outright.

        Both new parameters are optional, so existing callers keep working.
        """
        payload: Dict[str, Any] = {"start_url": start_url, "requested_by": requested_by}
        if passcode:
            payload["passcode"] = passcode
        if join_url:
            payload["join_url"] = join_url
        return await self._request(
            "POST",
            f"/meetings/{meeting_id}/launch",
            json=payload,
        )

    async def stop_meeting(self, meeting_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/meetings/{meeting_id}/stop")

    async def restart_zoom(self) -> Dict[str, Any]:
        return await self._request("POST", "/zoom/restart")

    async def import_session(self, cookie_json: bytes) -> Dict[str, Any]:
        """Upload a Cookie Editor export to the host, replacing the session.

        The body is the raw JSON bytes, not a multipart form: the bot receives a
        Telegram file_id and streams those bytes through unchanged, so wrapping
        them in multipart would be a second encoding of the same thing.
        """
        return await self._request(
            "POST",
            "/zoom/session",
            data=cookie_json,
            headers={**self._headers(), "Content-Type": "application/json"},
        )

    async def check_session(self) -> Dict[str, Any]:
        """Ask the host to verify the session against Zoom, not just the disk.

        Distinct from status()['session_ready'] in kind, not degree: status
        reports what the file's existence implies, this reports what Zoom says
        after loading it. Only this one can catch a session that is on disk and
        expired - the failure the operator cannot diagnose on their own.

        Slower than status(). It starts Chromium and waits on zoom.us.
        """
        return await self._request("POST", "/zoom/session/check")


remote_zoom_client = RemoteZoomClient()
