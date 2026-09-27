"""Delete Zoom meetings that the integration tests created, plus their cloud
recordings.

Every test in this directory creates a real meeting on the real Zoom account.
Until now cleanup lived at the end of the happy path, so any assertion failure
left the meeting behind. The next run created another. Four of them leaked in
one afternoon.

Two things make this harder than it looks:

1. ``created_by`` is NOT a usable discriminator. The tests drive the bot
   through a real Telegram account, so the rows are stamped with the operator's
   own user id. Filtering on it would also match meetings a human created by
   hand. The topic prefix is the only marker the tests control end to end.

2. Deleting the meeting does NOT delete its recordings. Zoom keeps
   cloud recordings in the account's Recordings tab until they are explicitly
   trashed, and they survive the meeting they belong to. A "clean" Zoom account
   that still has every test recording in it is not clean.

   Recordings are trashed first, so a failure halfway through leaves the more
   visible artifact gone first.

   KNOWN LIMITATION: the server-to-server OAuth token this project uses does
   not carry the ``recording:write:admin`` scope, so Zoom answers the trash
   call with ``400 code 4711`` and the recording survives. The code path is
   correct and stays in place; granting that scope in the Zoom app is what
   makes it work. Until then the meetings are cleaned and the recordings are
   not, and the report says so rather than claiming success.

Run it standalone to sweep up old ones::

    python tests/zoom_test_cleanup.py           # delete matching meetings
    python tests/zoom_test_cleanup.py --dry-run  # list them, change nothing
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from zoom.zoom import zoom_client

# Exact prefixes, each with its trailing space. Deliberately not a substring
# match: "Integration Test Meeting " must not catch a "Integration Test Meeting
# Planning" that a human scheduled.
#
# The trailing space alone is NOT enough, which the unit test proves. A human
# naming a meeting "Integration Test Meeting Planning Weekly" would still be
# caught. So each prefix is combined with TIMESTAMP_SUFFIX below: every test
# topic ends in f" {int(time.time())}", and nothing a human writes ends in a
# bare 10-digit unix timestamp. Both parts must match.
#
# Every entry is a literal that appears in a test file, so a test renaming its
# topic has to come here too - which is the point. A silent rename should
# surface as leftover meetings, not as meetings we quietly refuse to clean.
TEST_TOPIC_PREFIXES: Sequence[str] = (
    "Integration Test Meeting ",
    "Inline Deletion Test ",
    "Controls and Details Test ",
    "HostJoinProbe ",
)

# The tests all build their topic as f"{prefix}{int(time.time())}". A human
# topic can share the prefix ("Integration Test Meeting Planning") but is very
# unlikely to be the prefix plus nothing but a bare unix timestamp, so that is
# what is required - see is_test_meeting.


def is_test_meeting(topic: str | None) -> bool:
    """True only for a topic a test in this repo could have produced.

    The prefix must be followed by *only* a unix timestamp, not merely contain
    one somewhere. "Integration Test Meeting Planning 1790502426" starts with
    the prefix and ends with a timestamp, and a prefix-plus-suffix check that
    ignores the middle would delete it. Requiring the whole topic to be
    prefix+timestamp is what makes this safe to point at a real account.
    """
    if not topic:
        return False
    for prefix in TEST_TOPIC_PREFIXES:
        remainder = topic[len(prefix):] if topic.startswith(prefix) else None
        if remainder is not None and remainder.isdigit() and 9 <= len(remainder) <= 11:
            return True
    return False


async def find_test_meetings(meetings: Iterable[dict]) -> List[dict]:
    return [m for m in meetings if is_test_meeting(m.get("topic"))]


async def purge_meeting(meeting_id: str) -> dict:
    """Trash the cloud recordings, then delete the meeting.

    Order is deliberate. If the process dies between the two calls, what is
    left is an undeleted meeting whose recordings are already in the trash -
    the recoverable half. The reverse order leaves a deleted meeting with live
    recordings, which is the artifact nobody notices for months.

    Never raises. A cleanup path that can raise is a cleanup path that gets
    skipped exactly when it is most needed, which is inside a ``finally`` block
    where a raise would mask the original test failure.
    """
    result = {"meeting_id": meeting_id, "recording": None, "meeting": None}
    try:
        result["recording"] = await zoom_client.delete_cloud_recording(meeting_id)
    except Exception as exc:  # noqa: BLE001 - see docstring
        result["recording"] = f"error: {type(exc).__name__}: {exc}"
    try:
        await zoom_client.delete_meeting(meeting_id)
        result["meeting"] = "deleted"
    except Exception as exc:  # noqa: BLE001
        result["meeting"] = f"error: {type(exc).__name__}: {exc}"
    return result


async def purge_all_meetings(dry_run: bool = False) -> List[dict]:
    """Delete every test-created meeting on the account. Returns one report per
    meeting so the caller can log it without a second round trip."""
    data = await zoom_client.list_upcoming_meetings("me")
    targets = await find_test_meetings(data.get("meetings", []))
    if dry_run:
        return [{"meeting_id": str(m.get("id")), "topic": m.get("topic"),
                 "recording": "skipped", "meeting": "skipped"} for m in targets]
    return [await purge_meeting(str(m.get("id"))) for m in targets]


def _db_paths() -> List[Path]:
    """Every database that could hold rows for these meetings.

    The tests run against the local file while the bot normally runs in a
    container against its own copy, so cleaning one and not the other just
    moves the problem. Both are returned; missing ones are dropped.
    """
    candidates = [Path(settings.db_path), PROJECT_ROOT / "zoom_telebot.db"]
    out = []
    for path in candidates:
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if path.exists():
            out.append(path)
    return out


async def mark_deleted_in_db(meeting_ids: Iterable[str], extra_db: Path | None = None) -> None:
    """Mirror the Zoom-side deletion into the local DBs.

    Only ever writes the ``deleted`` status; it never removes rows. Row
    removal would break the audit trail that the meeting list is built on, and
    ``sync_meetings_from_zoom`` reaches the same end state on its own for
    anything Zoom no longer returns.

    ``extra_db`` exists because the bot normally runs in a container with its
    own database file, separate from the one the tests write to. Cleaning only
    the host copy leaves the container showing meetings that no longer exist in
    Zoom until the next sync happens to run.
    """
    ids = list(meeting_ids)
    if not ids:
        return
    import sqlite3
    placeholders = ",".join("?" * len(ids))
    paths = _db_paths()
    if extra_db:
        paths.append(extra_db)
    for path in paths:
        if not path.exists():
            continue
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                f"UPDATE meetings SET status='deleted', updated_at=CURRENT_TIMESTAMP "
                f"WHERE zoom_meeting_id IN ({placeholders})",
                ids,
            )
            conn.commit()
        finally:
            conn.close()


async def cleanup_zoom_meetings(label: str) -> None:
    """Call from a test's ``finally``. Never raises, never fails the test.

    Two rules, both learned the hard way:

    * It must not raise. This runs in ``finally``, so an exception here would
      replace the real test failure with a cleanup failure and the original
      traceback would be lost.
    * It must not be fatal. If Zoom is unreachable the test's own result is
      still the one that matters; a failure to tidy up is worth a loud warning,
      not a red test that sends someone hunting a bug in code that passed.
    """
    try:
        results = await purge_all_meetings()
    except Exception as exc:  # noqa: BLE001
        print(f"\n[{label}] Zoom cleanup skipped: {type(exc).__name__}: {exc}")
        print(f"[{label}] Test meetings may still be on the account. "
              f"Run: python tests/zoom_test_cleanup.py")
        return

    if not results:
        return

    try:
        await mark_deleted_in_db(r["meeting_id"] for r in results)
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] Could not update the local DB: {type(exc).__name__}: {exc}")

    failed = [r for r in results if str(r["meeting"]).startswith("error")]
    for row in results:
        print(f"[{label}] purged meeting {row['meeting_id']} "
              f"(recording={row['recording']}, meeting={row['meeting']})")
    if failed:
        print(f"[{label}] {len(failed)} meeting(s) survived cleanup - delete them by hand: "
              f"{', '.join(r['meeting_id'] for r in failed)}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be deleted and change nothing")
    parser.add_argument("--db", type=Path, default=None,
                        help="also mark these meetings deleted in this database file "
                             "(use inside the container: --db /app/zoom_telebot.db)")
    args = parser.parse_args()

    results = await purge_all_meetings(dry_run=args.dry_run)
    if not results:
        print("No test-generated meetings found. Nothing to do.")
        return 0

    for row in results:
        print(f"  {row['meeting_id']}  recording={row['recording']}  meeting={row['meeting']}")

    if args.dry_run:
        print(f"\n{len(results)} meeting(s) would be deleted. Re-run without --dry-run.")
        return 0

    await mark_deleted_in_db((r["meeting_id"] for r in results), extra_db=args.db)
    failed = [r for r in results if str(r["meeting"]).startswith("error")]
    print(f"\nDeleted {len(results) - len(failed)}/{len(results)} test meetings.")
    if failed:
        print(f"{len(failed)} failed - they need deleting by hand:")
        for row in failed:
            print(f"  {row['meeting_id']}: {row['meeting']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
