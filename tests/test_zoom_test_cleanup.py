"""Tests for the test-meeting cleanup, focused on the one thing that can do
real damage: deleting a meeting a human actually scheduled.

Nothing here touches the network. Zoom is called through ``zoom_client`` and
every test that would reach it is faked.
"""

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tests.zoom_test_cleanup as zc


def test_every_prefix_comes_from_a_real_test():
    """A prefix with no matching topic in any test file is dead weight that
    will never match, and a test that renames its topic without updating this
    list leaves a meeting behind. Fail loudly instead of silently drifting."""
    test_dir = PROJECT_ROOT / "tests"
    sources = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in test_dir.glob("*.py")
        if p.name != "zoom_test_cleanup.py"
    )
    for prefix in zc.TEST_TOPIC_PREFIXES:
        assert prefix in sources, (
            f"{prefix!r} is listed in TEST_TOPIC_PREFIXES but no test file uses it. "
            "Either the tests were renamed and this list was not, or the prefix is dead."
        )


def test_is_test_meeting_matches_real_test_topics():
    for prefix in zc.TEST_TOPIC_PREFIXES:
        assert zc.is_test_meeting(prefix + "1790502426")


def test_is_test_meeting_refuses_human_topics():
    """The guard that matters. Everything here must be False, because a True
    means cleanup deletes a meeting a person booked."""
    human = [
        "Rapat Koordinasi",
        "Integration Test Meeting Planning",       # prefix, no timestamp
        "Integration Test Meeting Planning Weekly",  # prefix AND extra words
        "Integration Test Meeting 2026",           # 4 digits, not a unix stamp
        "Integration Test Meeting",                # prefix, nothing after
        "Standup Harian",
        "integration test meeting 123",            # case differs
        "Rapat - Integration Test Meeting",         # prefix not at the start
        "HostJoinProbe Planning Sync",              # prefix, no timestamp
        "",
        None,
    ]
    for topic in human:
        assert not zc.is_test_meeting(topic), f"would delete a human meeting: {topic!r}"


def test_a_prefix_with_a_timestamp_looks_exactly_like_a_real_one():
    """If this ever stops being true the two cases above pass for the wrong
    reason and the matcher is silently useless. Pin the two together."""
    real = "Integration Test Meeting 1790502426"
    decoy = "Integration Test Meeting Planning 1790502426"
    assert zc.is_test_meeting(real)
    assert not zc.is_test_meeting(decoy), (
        "a human topic ending in a timestamp is indistinguishable from a test "
        "topic; tighten the matcher before running this against the account"
    )


def test_find_test_meetings_filters_without_touching_zoom():
    meetings = [
        {"id": 1, "topic": "Integration Test Meeting 1790502426"},
        {"id": 2, "topic": "Rapat Internal"},
        {"id": 3, "topic": "HostJoinProbe 1790410614"},
        {"id": 4},
    ]
    kept = asyncio.run(zc.find_test_meetings(meetings))
    assert [m["id"] for m in kept] == [1, 3]


def test_purge_meeting_trashes_recording_before_deleting_meeting(monkeypatch):
    """Order is the whole point. Trash the recording first: a crash between
    the two calls then leaves a live meeting with trashed recordings, which is
    recoverable. The reverse leaves a deleted meeting with recordings nobody
    can see, in an account's Recordings tab, for months."""
    calls = []

    async def fake_recording(meeting_id):
        calls.append(("recording", meeting_id))
        return True

    async def fake_delete(meeting_id):
        calls.append(("meeting", meeting_id))
        return True

    monkeypatch.setattr(zc.zoom_client, "delete_cloud_recording", fake_recording)
    monkeypatch.setattr(zc.zoom_client, "delete_meeting", fake_delete)

    result = asyncio.run(zc.purge_meeting("123"))

    assert calls == [("recording", "123"), ("meeting", "123")], calls
    assert result == {"meeting_id": "123", "recording": True, "meeting": "deleted"}


def test_purge_meeting_still_deletes_the_meeting_when_recording_fails(monkeypatch):
    """A recording failure is common and usually permanent - the S2S token has
    no recording:write:admin scope. The meeting must go anyway, or the
    permanently-failing recording call blocks cleanup forever."""
    calls = []

    async def fake_recording(meeting_id):
        calls.append("recording")
        raise RuntimeError("no scope")

    async def fake_delete(meeting_id):
        calls.append("meeting")
        return True

    monkeypatch.setattr(zc.zoom_client, "delete_cloud_recording", fake_recording)
    monkeypatch.setattr(zc.zoom_client, "delete_meeting", fake_delete)

    result = asyncio.run(zc.purge_meeting("123"))

    assert calls == ["recording", "meeting"]
    assert result["meeting"] == "deleted"
    assert "no scope" in str(result["recording"])


def test_purge_meeting_never_raises(monkeypatch):
    """It runs in a finally block. A raise here replaces the real test failure
    with a cleanup failure and the original traceback is lost."""

    async def boom(_):
        raise RuntimeError("Zoom is down")

    monkeypatch.setattr(zc.zoom_client, "delete_cloud_recording", boom)
    monkeypatch.setattr(zc.zoom_client, "delete_meeting", boom)

    result = asyncio.run(zc.purge_meeting("123"))
    assert str(result["meeting"]).startswith("error")


def test_cleanup_helper_swallows_zoom_outages(monkeypatch):
    """A cleanup failure must not turn a passing test red. It warns instead."""
    async def boom():
        raise RuntimeError("Zoom unreachable")

    monkeypatch.setattr(zc, "purge_all_meetings", boom)
    asyncio.run(zc.cleanup_zoom_meetings("t"))  # must not raise


def test_cleanup_helper_never_calls_the_db_when_nothing_matched(monkeypatch):
    called = []

    async def empty():
        return []

    async def tracker(ids, extra_db=None):
        called.append(list(ids))

    monkeypatch.setattr(zc, "purge_all_meetings", empty)
    monkeypatch.setattr(zc, "mark_deleted_in_db", tracker)
    asyncio.run(zc.cleanup_zoom_meetings("t"))
    assert called == []
