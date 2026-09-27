"""Tests for ZoomClient.delete_meeting's idempotence.

The bug this file exists for, in production, on a real account:

    📊 Hasil Batch Deletion
    ❌ Berhasil: 0
    ❌ Gagal: 6
    ❌ Meeting 1 (82541217658): Gagal - Zoom API error 404:
       {"code":3001,"message":"Meeting does not exist: 82541217658."}

Those six meetings were already gone from Zoom - the cleanup had deleted them.
The rows were still in the local DB as 'done', because sync_meetings_from_zoom
only reconciles the 'active' status, so nothing ever retired them. Deleting
them then returned 404, and a 404 was reported as a failure, so the row never
left the meeting list and /zoom_del could never clean it up. A 404 is the
desired end state, not a problem.

No network. aiohttp is faked at the response level; only the status codes Zoom
actually returns are modelled.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zoom.zoom import ZoomClient  # noqa: E402


class FakeResponse:
    def __init__(self, status: int, body: str = "") -> None:
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response
        self.requests: list[tuple[str, str]] = []

    def delete(self, url, headers=None):
        self.requests.append(("DELETE", url))
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def client(monkeypatch):
    c = ZoomClient()

    async def fake_token():
        return "token"

    monkeypatch.setattr(c, "ensure_token", fake_token)
    return c


def _patch_session(monkeypatch, response: FakeResponse) -> FakeSession:
    """Swap aiohttp.ClientSession for a fake. zoom.py does
    `async with aiohttp.ClientSession() as session:` so the constructor itself
    has to return the fake, not just __aenter__."""
    session = FakeSession(response)
    monkeypatch.setattr("zoom.zoom.aiohttp.ClientSession", lambda *a, **k: session)
    return session


async def test_204_is_success(client, monkeypatch):
    _patch_session(monkeypatch, FakeResponse(204))
    assert await client.delete_meeting("123") is True


async def test_404_already_gone_counts_as_success(client, monkeypatch):
    """The regression. Zoom code 3001 means the meeting is not there - which is
    what the caller asked for. Raising here made /zoom_del report six failures
    for six meetings it had in fact already cleaned up, and the stale rows
    stayed in the list forever because the DB status was only written on
    success."""
    _patch_session(monkeypatch, FakeResponse(
        404, '{"code":3001,"message":"Meeting does not exist: 82541217658."}'))
    assert await client.delete_meeting("82541217658") is True


async def test_delete_is_repeatable(client, monkeypatch):
    """Calling twice must not fail the second time. The bot and the test
    cleanup both call this, and a user will retry a delete that looked like it
    failed."""
    _patch_session(monkeypatch, FakeResponse(404))
    assert await client.delete_meeting("123") is True
    assert await client.delete_meeting("123") is True


async def test_real_errors_still_raise(client, monkeypatch):
    """Idempotence must not swallow genuine failures. 403 and 500 mean the
    meeting is still there and the caller should know about it."""
    for status, body in ((403, '{"code":3003}'), (500, "boom")):
        _patch_session(monkeypatch, FakeResponse(status, body))
        with pytest.raises(RuntimeError, match=f"Zoom API error {status}"):
            await client.delete_meeting("123")


async def test_unexpected_success_status_is_not_claimed_as_deleted(client, monkeypatch):
    """Zoom has returned 200 for this endpoint in the past. A body it never
    documented is not proof of deletion, so it stays False rather than being
    folded into the 404 branch."""
    _patch_session(monkeypatch, FakeResponse(200, "{}"))
    assert await client.delete_meeting("123") is False
