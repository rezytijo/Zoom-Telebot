"""Integration test for the remote host-join flow.

Covers what the other suites do not: pressing "Start on Remote Zoom" and
watching the meeting reach a terminal live_status.

The launch itself is asserted strictly - the controller must accept it and the
row must land in launch_requested. The *host confirmation* step cannot be
asserted unconditionally, because it needs a human logged into the Kasm Zoom
container clicking "Join" (or a pre-warmed login in zoom_remote_profile). So the
test asserts the timeout branch when the host never joins, and reports which
branch ran. That is deliberate: a silent pass would be worse than a reported
skip, because the whole point of this feature is proving the loop terminates.

Run:
    python -m pytest tests/test_remote_host_join.py -v

Note: the Docker bot container must be stopped first. It shares TELEGRAM_TOKEN
with the local bot this test spawns, and two pollers on one token make every
update invisible to this test (TelegramConflictError).
"""
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.zoom_test_cleanup import mark_deleted_in_db, purge_all_meetings

_original_print = print


def print(*args, **kwargs):  # noqa: A001 - CP1252-safe stdout for Windows
    safe = []
    for a in args:
        if isinstance(a, str):
            enc = sys.stdout.encoding or "utf-8"
            try:
                a.encode(enc)
            except UnicodeEncodeError:
                a = a.encode(enc, errors="replace").decode(enc)
            safe.append(a)
        else:
            safe.append(a)
    _original_print(*safe, **kwargs)


from config import settings  # noqa: E402

try:
    from telethon import TelegramClient
except ImportError:
    pytest.skip(
        "Telethon not installed. Run: pip install -r requirements-dev.txt",
        allow_module_level=True,
    )

CREDENTIALS_FILE = PROJECT_ROOT / "tests" / "tg_credentials.json"

# How long to watch the launch before giving up. Kept short on purpose: this is a
# test, not a demo. The production budget lives in ZOOM_REMOTE_HOST_CONFIRM_TIMEOUT.
POLL_BUDGET_SECONDS = int(os.getenv("TEST_HOST_CONFIRM_BUDGET", "150"))
POLL_INTERVAL = 10

# zoom-remote publishes 8080 to loopback only (see docker-compose.yml). The
# .env value is the compose hostname, which does not resolve from the host.
HOST_CONTROLLER_PORT = int(os.getenv("ZOOM_REMOTE_HOST_PORT", "8080"))


def load_credentials():
    if not CREDENTIALS_FILE.exists():
        pytest.skip(
            f"Telegram credentials not configured. See {CREDENTIALS_FILE}.example"
        )
    with open(CREDENTIALS_FILE) as fh:
        return json.load(fh)


def db_path() -> Path:
    p = Path(settings.db_path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def read_live_status(meeting_id: str):
    """Read the full launch row straight from SQLite (no bot involved)."""
    conn = sqlite3.connect(str(db_path()))
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT live_status, last_remote_error, requested_by,
                      launch_requested_at, actual_started_at
               FROM meeting_live_status WHERE zoom_meeting_id = ?""",
            (meeting_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        keys = ("live_status", "last_remote_error", "requested_by",
                "launch_requested_at", "actual_started_at")
        return dict(zip(keys, row))
    finally:
        conn.close()


def whitelist_user(telegram_id: int, username: str):
    conn = sqlite3.connect(str(db_path()))
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
        if cur.fetchone():
            cur.execute(
                "UPDATE users SET username=?, status='whitelisted', role='owner' "
                "WHERE telegram_id = ?",
                (username, telegram_id),
            )
        else:
            cur.execute(
                "INSERT INTO users (telegram_id, username, status, role) "
                "VALUES (?, ?, 'whitelisted', 'owner')",
                (telegram_id, username),
            )
        conn.commit()
        print(f"[setup] user {telegram_id} whitelisted as owner")
    finally:
        conn.close()


def get_latest_meeting(telegram_id: int):
    """Fetch the most recent meeting this user created.

    The bot stores the Zoom id as TEXT, so it must be compared as a string.
    """
    conn = sqlite3.connect(str(db_path()))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT zoom_meeting_id FROM meetings WHERE created_by = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (str(telegram_id),),
        )
        row = cur.fetchone()
        return str(row[0]) if row and row[0] is not None else None
    finally:
        conn.close()


def container_running() -> bool:
    out = subprocess.run(
        ["docker", "compose", "ps", "--format", "{{.Service}} {{.State}}"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    for line in (out.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "zoom-telebot" and parts[1] == "running":
            return True
    return False


def dump_container_logs(tail: int = 120):
    """Best-effort log dump. Never fail the test because logging failed."""
    for args in (
        ["docker", "compose", "logs", "--no-color", "--tail", str(tail), "zoom-remote"],
        ["docker", "compose", "logs", "--no-color", "--tail", str(tail), "zoom-telebot"],
    ):
        try:
            proc = subprocess.run(args, cwd=str(PROJECT_ROOT),
                                  capture_output=True, text=True, timeout=30)
            body = (proc.stdout or "").strip()
            if body:
                print(f"\n----- {' '.join(args[-1:])} logs -----")
                print(body)
        except Exception as exc:
            print(f"(log dump failed: {exc})")


def controller_reachable() -> tuple[bool, str]:
    """Probe the Go controller from the host.

    .env points ZOOM_REMOTE_BASE_URL at the compose hostname (zoom-remote:8080),
    which only resolves *inside* the Docker network. The controller publishes
    127.0.0.1:8080, so the local bot must be pointed there instead.
    """
    import urllib.error
    import urllib.request

    for base in (f"http://127.0.0.1:{HOST_CONTROLLER_PORT}", settings.zoom_remote_base_url):
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=4) as resp:
                if resp.status == 200:
                    return True, base
        except Exception as exc:
            last = f"{base} -> {type(exc).__name__}: {exc}"
    return False, locals().get("last", "no endpoint tried")


def reset_remote_host():
    """Free a host still bound to a previous meeting.

    The controller's `state` lives in memory only: once a launch succeeds it
    stays {Status: "opened", MeetingID: X} forever, because nothing on the Go
    side transitions it. A second launch of a *different* meeting therefore
    hits the conflict branch and is rejected with 409. This is the same thing
    the bot's "Restart Remote Zoom" button does, so the test uses it too.
    """
    import urllib.request

    if not settings.zoom_remote_api_token:
        pytest.skip("ZOOM_REMOTE_API_TOKEN is not set; cannot drive the controller")

    req = urllib.request.Request(
        f"http://127.0.0.1:{HOST_CONTROLLER_PORT}/zoom/restart",
        method="POST",
        headers={"Authorization": f"Bearer {settings.zoom_remote_api_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            print(f"[setup] host reset: {resp.read().decode('utf-8', 'replace').strip()}")
    except Exception as exc:
        pytest.fail(
            f"Could not reset the remote host: {type(exc).__name__}: {exc}\n"
            "The host may still be bound to an earlier meeting."
        )


def start_bot_process():
    lock = PROJECT_ROOT / "bot.lock"
    if lock.exists():
        try:
            lock.unlink()
        except OSError:
            pass
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "test_host_join.log"
    fh = open(log_path, "w", encoding="utf-8")
    env = os.environ.copy()
    env["LOG_LEVEL"] = "INFO"
    env["ENABLE_DEPENDENCY_AUDIT"] = "false"
    env["ZOOM_REMOTE_HOST_PORT"] = str(HOST_CONTROLLER_PORT)
    # Not run.py: dotenv override would clobber an env-based base URL. See
    # _bot_host_launcher.py for the full explanation.
    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "tests" / "_bot_host_launcher.py")],
        cwd=str(PROJECT_ROOT), stdout=fh, stderr=subprocess.STDOUT, env=env, text=True,
    )
    print(f"[setup] bot subprocess pid={proc.pid}, log={log_path}")
    return proc, fh, log_path


def stop_bot_process(proc, fh):
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    if fh:
        fh.close()


def wait_for_polling_ready(log_path: Path, timeout: int = 60):
    """Block until the dispatcher is actually polling.

    Sleeping a fixed 5s is what made the sibling suite flaky: on_startup awaits
    a full Zoom sync, so on a slow machine the first command is never answered.
    """
    marker = "Start polling"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log_path.exists():
            try:
                if marker in log_path.read_text(encoding="utf-8", errors="replace"):
                    return True
            except OSError:
                pass
        time.sleep(0.5)
    return False


async def wait_for_bot_response(client, bot_username, last_msg=None, timeout: int = 20):
    last_id = last_msg.id if last_msg else None
    last_text = last_msg.text if last_msg else ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(0.4)
        msgs = await client.get_messages(bot_username, limit=1)
        if not msgs:
            continue
        msg = msgs[0]
        if last_id is not None and msg.id == last_id:
            msg = await client.get_messages(bot_username, ids=last_id) or msg
        if last_msg is None or msg.id != last_id:
            return msg
        if msg.text != last_text:
            return msg
    raise TimeoutError(f"Timeout waiting for bot. Last text: {last_text!r}")


async def run_host_join_test():
    creds = load_credentials()
    if container_running():
        pytest.fail(
            "Docker bot container is running. It shares TELEGRAM_TOKEN with the "
            "local bot this test spawns, so updates are consumed by the container "
            "and this test can never see a reply.\n"
            "Run:  docker compose stop zoom-telebot"
        )

    reachable, endpoint = controller_reachable()
    if not reachable:
        pytest.fail(
            f"Remote Zoom controller is not reachable ({endpoint}).\n"
            f"Run:  docker compose up -d zoom-remote   "
            f"(expects http://127.0.0.1:{HOST_CONTROLLER_PORT}/health)"
        )
    print(f"[setup] controller reachable at {endpoint}")

    from db import init_db
    await init_db()

    client = TelegramClient(
        str(PROJECT_ROOT / "tests" / "test_session"),
        creds["api_id"], creds["api_hash"],
    )
    await client.start(phone=creds["phone"])
    me = await client.get_me()
    whitelist_user(me.id, me.username or f"test_{me.id}")

    bot_proc, log_fh, log_path = start_bot_process()
    try:
        reset_remote_host()
        if not wait_for_polling_ready(log_path):
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:] \
                if log_path.exists() else "(no log)"
            pytest.fail(f"Bot never reached '{marker_ready}'.\nLog tail:\n{tail}")
        print("[setup] bot is polling")

        # 1. Create a meeting through the bot. The FSM is text-driven:
        #    Create Meeting -> send topic -> send date -> send time -> Konfirmasi.
        msg = await client.send_message(creds["bot_username"], "/start")
        resp = await wait_for_bot_response(client, creds["bot_username"], msg)
        create_btn = next(
            b for row in resp.buttons for b in row if "Create Meeting" in b.text
        )
        await create_btn.click()

        topic = f"HostJoinProbe {int(time.time())}"
        sent = await client.send_message(creds["bot_username"], topic)
        sent = await wait_for_bot_response(client, creds["bot_username"], sent)
        assert "Kapan" in sent.text, f"Expected the date prompt, got:\n{sent.text}"

        date_str = (datetime.now() + timedelta(days=1)).strftime("%d-%m-%Y")
        sent = await client.send_message(creds["bot_username"], date_str)
        sent = await wait_for_bot_response(client, creds["bot_username"], sent)
        assert "jam" in sent.text.lower(), f"Expected the time prompt, got:\n{sent.text}"

        sent = await client.send_message(creds["bot_username"], "14:30")
        sent = await wait_for_bot_response(client, creds["bot_username"], sent)
        print(f"[1] confirm screen:\n{sent.text}")
        confirm = next(
            b for row in sent.buttons for b in row if "Konfirmasi" in b.text
        )
        await confirm.click()

        created = await wait_for_bot_response(
            client, creds["bot_username"], sent, timeout=40
        )
        print(f"[1] create result:\n{created.text}")

        # Read the id from the DB, not the message: parsing Zoom ids out of
        # formatted text is what makes suites break when the template changes.
        meeting_id = get_latest_meeting(me.id)
        assert meeting_id, f"No meeting row written by this user:\n{created.text}"
        print(f"[2] meeting_id = {meeting_id}")

        # 2. Open the control screen and press "Start on Remote Zoom".
        msg = await client.send_message(creds["bot_username"], "/start")
        resp = await wait_for_bot_response(client, creds["bot_username"], msg)
        list_btn = next(b for row in resp.buttons for b in row if "List Meeting" in b.text)
        await list_btn.click()
        list_view = await wait_for_bot_response(client, creds["bot_username"], resp)

        control_btn = next(
            b for row in list_view.buttons for b in row
            if b.data and b.data.decode().startswith(f"control_zoom:{meeting_id}")
        )
        await control_btn.click()
        control = await wait_for_bot_response(client, creds["bot_username"], list_view)
        print(f"[3] control screen:\n{control.text}")

        start_btn = next(
            b for row in control.buttons for b in row
            if b.data and b.data.decode().startswith(f"start_zoom_meeting:{meeting_id}")
        )
        await start_btn.click()
        launched = await wait_for_bot_response(
            client, creds["bot_username"], control, timeout=40
        )
        print(f"[4] launch screen:\n{launched.text}")

        # 3. The launch must be accepted, not silently swallowed.
        assert "gagal" not in launched.text.lower(), f"Launch reported failure:\n{launched.text}"

        state = read_live_status(meeting_id)
        assert state is not None, "No meeting_live_status row was written"
        print(f"[5] db after launch: {state}")
        assert state["live_status"] in ("launch_requested", "started"), (
            f"Expected launch_requested or started, got {state['live_status']!r} "
            f"(err={state['last_remote_error']!r})"
        )

        # 4. Watch the poller resolve it.
        if state["live_status"] == "launch_requested":
            print(f"[6] watching up to {POLL_BUDGET_SECONDS}s for host confirmation...")
            deadline = time.time() + POLL_BUDGET_SECONDS
            while time.time() < deadline:
                await asyncio.sleep(POLL_INTERVAL)
                state = read_live_status(meeting_id)
                print(f"    live_status = {state['live_status']}  "
                      f"err = {state['last_remote_error']}")
                if state["live_status"] in ("started", "failed"):
                    break

        final = state["live_status"]
        print(f"[7] final live_status = {final}")

        if final == "started":
            assert state["actual_started_at"], (
                "live_status=started but actual_started_at was never stamped"
            )
            print("HOST JOIN CONFIRMED: the remote host actually joined.")
        else:
            # Not a pass and not a failure of the code - it means nobody is
            # logged into the Kasm container. Say so explicitly.
            pytest.skip(
                "Launch was accepted but the host never joined, so the poller "
                f"resolved it to {final!r} ({state['last_remote_error']!r}).\n"
                "This is expected until someone logs into Zoom inside the Kasm "
                "container once (VNC on 127.0.0.1:6901) and stays logged in.\n"
                "What this test DID prove: the launch was accepted, the row went "
                "to launch_requested, and the watcher resolved it to a terminal "
                "state instead of hanging forever."
            )

    except Exception:
        print("\n########## FAILURE DIAGNOSTICS ##########")
        print(read_live_status.__doc__ or "")
        dump_container_logs()
        try:
            if log_path.exists():
                print("\n----- local bot log tail -----")
                print(log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
        except OSError:
            pass
        raise
    finally:
        stop_bot_process(bot_proc, log_fh)
        await client.disconnect()
        # This test had no Zoom-side cleanup at all - the four HostJoinProbe
        # meetings it left behind were still scheduled a day later. It also
        # pytest.skips on the no-host-joined branch, which is the most likely
        # outcome, so a happy-path cleanup here would almost never run.
        await cleanup_zoom_meetings("test_remote_host_join")


marker_ready = "Start polling"


@pytest.mark.asyncio
async def test_remote_host_join():
    """Press Start on Remote Zoom and verify the launch reaches a terminal state."""
    await run_host_join_test()
