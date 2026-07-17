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
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                **kwargs,
            ) as response:
                try:
                    payload = await response.json()
                except Exception:
                    payload = {"error": await response.text()}
                if response.status >= 400:
                    raise RemoteZoomError(payload.get("error") or f"Remote Zoom HTTP {response.status}")
                return payload

    async def health(self) -> Dict[str, Any]:
        return await self._request("GET", "/health")

    async def status(self) -> Dict[str, Any]:
        return await self._request("GET", "/status")

    async def launch_meeting(self, meeting_id: str, start_url: str, requested_by: int) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/meetings/{meeting_id}/launch",
            json={"start_url": start_url, "requested_by": requested_by},
        )

    async def stop_meeting(self, meeting_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/meetings/{meeting_id}/stop")

    async def restart_zoom(self) -> Dict[str, Any]:
        return await self._request("POST", "/zoom/restart")


remote_zoom_client = RemoteZoomClient()
