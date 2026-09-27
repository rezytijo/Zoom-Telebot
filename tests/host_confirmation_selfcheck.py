"""Self-check for remote host-confirmation logic.

Covers the two places where a silent bug makes the feature useless:
  1. list_meetings_pending_launch must return launch_requested rows ONLY, and
     launch_requested_at must arrive as a datetime (the timeout math needs it).
  2. _render_launch_detail must distinguish the states that live_status alone
     collapses, and must escape last_remote_error.

Run: python tests/host_confirmation_selfcheck.py
Exits non-zero on failure.
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiosqlite

from config import settings

_pending = None
render = None


async def _setup():
    """Import db + handlers against a throwaway DB and return the callables.

    Tables come from init_db() rather than db/schema.sql: db.py carries its own
    inline CREATE TABLE, and schema.sql is reference documentation only.
    """
    global _pending, render
    import db as db_pkg
    from bot import handlers as handlers_mod

    tmp = tempfile.mkdtemp()
    settings.db_path = os.path.join(tmp, "selfcheck.db")

    await db_pkg.init_db()
    _pending = db_pkg.list_meetings_pending_launch
    render = handlers_mod._render_launch_detail
    return db_pkg


async def main():
    db_pkg = await _setup()
    from db import (
        set_remote_launch_state,
        mark_remote_launch_failed,
        get_remote_launch_state,
    )

    # Seed the three states that matter plus one never-touched meeting.
    await set_remote_launch_state("111", "req-1", 555)  # launch_requested
    await set_remote_launch_state("222", "req-2", 555, "failed", "TokenError: missing token")
    await set_remote_launch_state("333", "req-3", 555, "started")

    # 1. Only launch_requested rows come back.
    rows = await _pending()
    assert [r["zoom_meeting_id"] for r in rows] == ["111"], (
        f"expected only meeting 111 pending, got {[r['zoom_meeting_id'] for r in rows]}"
    )

    # 2. launch_requested_at must be a datetime, not a string. If it is a str,
    #    _as_naive() raises AttributeError and the timeout never fires.
    ts = rows[0]["launch_requested_at"]
    assert isinstance(ts, datetime), f"launch_requested_at must be datetime, got {type(ts)}"

    # 3. A fresh request is not yet past the confirm timeout.
    age = (datetime.now() - ts.replace(tzinfo=None)).total_seconds()
    assert age < 60, f"freshly seeded request should be young, got {age}s"

    # 4. A stale request IS past the timeout -> the caller marks it failed.
    stale = (datetime.now() - timedelta(seconds=settings.zoom_remote_host_confirm_timeout + 60))
    async with aiosqlite.connect(settings.db_path) as conn:
        await conn.execute(
            "UPDATE meeting_live_status SET launch_requested_at = ? WHERE zoom_meeting_id = '111'",
            (stale.isoformat(sep=" "),),
        )
        await conn.commit()
    rows = await _pending()
    stale_ts = rows[0]["launch_requested_at"].replace(tzinfo=None)
    age = (datetime.now() - stale_ts).total_seconds()
    assert age > settings.zoom_remote_host_confirm_timeout, (
        f"stale request should exceed {settings.zoom_remote_host_confirm_timeout}s, got {age}s"
    )

    # 5. mark_remote_launch_failed only touches launch_requested rows. A late
    #    failure arriving after the webhook already set 'started' must not win.
    await mark_remote_launch_failed("333", "host_confirm_timeout")
    state = await get_remote_launch_state("333")
    assert state["live_status"] == "started", (
        f"late failure overwrote a started meeting: {state}"
    )

    # 6. A real pending row does transition to failed.
    await mark_remote_launch_failed("111", "host_confirm_timeout")
    state = await get_remote_launch_state("111")
    assert state["live_status"] == "failed", f"expected failed, got {state}"
    assert state["last_remote_error"] == "host_confirm_timeout"

    # 7. Rendering: the states live_status alone would collapse must differ.
    pending_html = render(
        {"live_status": "launch_requested", "launch_requested_at": datetime.now(),
         "requested_by": 555, "last_remote_error": None},
        requested_by_id=555,
    )
    failed_html = render(
        {"live_status": "failed", "launch_requested_at": None,
         "requested_by": 555, "last_remote_error": "<b>TokenError</b>"},
        requested_by_id=555,
    )
    started_html = render({"live_status": "started", "actual_started_at": datetime.now()},
                          requested_by_id=555)
    none_html = render({"live_status": "not_started"}, requested_by_id=555)

    assert "Menunggu host masuk" in pending_html, pending_html
    assert "Remote launch gagal" in failed_html, failed_html
    # 8. Raw exception text is escaped, not injected as HTML.
    assert "<b>TokenError</b>" not in failed_html, f"unescaped error HTML: {failed_html}"
    assert "&lt;b&gt;TokenError" in failed_html, f"error not escaped: {failed_html}"
    assert "Host masuk" in started_html, started_html
    assert none_html == "", f"not_started should render nothing, got {none_html!r}"

    # 9. An aware timestamp must not crash the formatter (naive/aware mix).
    aware = datetime.now(timezone.utc)
    aware_html = render({"live_status": "started", "actual_started_at": aware},
                        requested_by_id=555)
    assert "Host masuk" in aware_html, aware_html

    # 10. _fmt_ts must render in the bot timezone, not raw UTC. A naive DB value
    #     is UTC (SQLite CURRENT_TIMESTAMP), so raw strftime would read 7 hours
    #     early for the Asia/Jakarta default.
    from bot.handlers import _fmt_ts
    from config import settings as cfg
    from zoneinfo import ZoneInfo

    naive_utc = datetime(2026, 9, 26, 12, 0, 0)          # 19:00 in WIB
    expected = naive_utc.replace(tzinfo=timezone.utc).astimezone(
        ZoneInfo(cfg.timezone)).strftime("%H:%M:%S")
    got = _fmt_ts(naive_utc)
    assert got == expected, f"tz mismatch: got {got}, expected {expected}"

    # An already-aware value in the same zone must render identically.
    assert _fmt_ts(naive_utc.replace(tzinfo=timezone.utc)) == expected, \
        "aware and naive-equivalent timestamps must render the same"

    # 11. String timestamps from the DB must be parsed, not passed through raw.
    assert _fmt_ts("2026-09-26 12:00:00") == expected, \
        f"string timestamp not parsed: {_fmt_ts('2026-09-26 12:00:00')}"

    # 12. Regression: SQLite CURRENT_TIMESTAMP is UTC but datetime.now() is local.
    #     A fresh launch_requested must NOT look like it timed out. The Docker
    #     image sets TZ=Asia/Jakarta, so a naive-UTC value subtracted from a
    #     naive-local now is off by +7h and every launch looked instantly expired.
    from bot.background_tasks import _as_utc_naive

    # What SQLite actually hands back: naive UTC.
    fresh_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    age_fixed = (datetime.now(timezone.utc).replace(tzinfo=None)
                 - _as_utc_naive(fresh_utc_naive)).total_seconds()
    assert age_fixed < 60, f"fresh launch must look young, got {age_fixed:.0f}s"

    # Reproduce the container clock explicitly rather than depending on the
    # machine running this check (which may itself be UTC).
    wib = timezone(timedelta(hours=7))
    local_wib_now = datetime.now(wib).replace(tzinfo=None)
    old_age = (local_wib_now - fresh_utc_naive).total_seconds()
    assert old_age > settings.zoom_remote_host_confirm_timeout, (
        f"test is vacuous: the old naive-local math should have produced a false "
        f"timeout under TZ=Asia/Jakarta, but got {old_age:.0f}s"
    )

    # The fix must collapse both spellings to the same instant.
    assert _as_utc_naive(fresh_utc_naive) == fresh_utc_naive
    aware_in_wib = datetime.now(wib)
    age_from_aware = (datetime.now(timezone.utc).replace(tzinfo=None)
                      - _as_utc_naive(aware_in_wib)).total_seconds()
    assert abs(age_from_aware) < 60, f"aware non-UTC timestamp mishandled: {age_from_aware:.0f}s"

    print("host_confirmation_selfcheck: all assertions passed")


if __name__ == "__main__":
    asyncio.run(main())
