import os
import sys
import json
import time
import asyncio
import sqlite3
import subprocess
from pathlib import Path
import pytest

# Add project root to python path to enable config imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Safe print helper to prevent UnicodeEncodeError in Windows command line terminals (CP1252)
_original_print = print
def print(*args, **kwargs):
    new_args = []
    for arg in args:
        if isinstance(arg, str):
            try:
                encoding = sys.stdout.encoding or 'utf-8'
                arg.encode(encoding)
                new_args.append(arg)
            except UnicodeEncodeError:
                encoding = sys.stdout.encoding or 'utf-8'
                new_args.append(arg.encode(encoding, errors='replace').decode(encoding))
        else:
            new_args.append(arg)
    _original_print(*new_args, **kwargs)

from config import settings
from db import init_db
from tests.zoom_test_cleanup import purge_all_meetings, mark_deleted_in_db

# Try to import telethon
try:
    from telethon import TelegramClient
except ImportError:
    # ponytail: skip, not sys.exit — sys.exit during collection aborts the whole
    # pytest run (INTERNALERROR), taking the other suites down with it.
    pytest.skip(
        "Telethon not installed. Run: pip install -r requirements-dev.txt",
        allow_module_level=True,
    )

CREDENTIALS_FILE = PROJECT_ROOT / "tests" / "tg_credentials.json"


def load_credentials():
    """Load Telegram client credentials from tests/tg_credentials.json."""
    if not CREDENTIALS_FILE.exists():
        print("\n" + "=" * 80)
        print("❌ INTEGRATION TEST ERROR: Telegram Credentials Not Found!")
        print(f"Please create the file: {CREDENTIALS_FILE}")
        print("You can copy the example template:")
        print("  cp tests/tg_credentials.json.example tests/tg_credentials.json")
        print("And fill it with your own API ID, Hash, Phone, and Bot username.")
        print("=" * 80 + "\n")
        pytest.skip("Telegram credentials not configured. Skipping integration tests.")

    with open(CREDENTIALS_FILE, "r") as f:
        return json.load(f)


def whitelist_user(telegram_id: int, username: str):
    """Directly whitelist the test Telegram user in the SQLite database as Owner."""
    db_path = Path(settings.db_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    print(f"Connecting to database at {db_path} to whitelist test user {telegram_id}...")
    
    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        
        # Verify table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        if not cursor.fetchone():
            print("Database tables not initialized. Running init_db...")
            asyncio.run(init_db())
            
        cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE users SET username = ?, status = 'whitelisted', role = 'owner' WHERE telegram_id = ?",
                (username, telegram_id)
            )
            print(f"Updated user {telegram_id} ({username}) to whitelisted owner.")
        else:
            cursor.execute(
                "INSERT INTO users (telegram_id, username, status, role) VALUES (?, ?, 'whitelisted', 'owner')",
                (telegram_id, username)
            )
            print(f"Inserted new user {telegram_id} ({username}) as whitelisted owner.")
        conn.commit()
    except Exception as e:
        print(f"Error whitelisting user: {e}")
        raise
    finally:
        conn.close()


def get_latest_meeting(telegram_id: int):
    """Fetch the latest meeting created by the user from SQLite database."""
    db_path = Path(settings.db_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
        
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT zoom_meeting_id, topic, status FROM meetings WHERE created_by = ? ORDER BY created_at DESC LIMIT 1",
            (str(telegram_id),)
        )
        row = cursor.fetchone()
        if row:
            return {
                "meeting_id": row[0],
                "topic": row[1],
                "status": row[2]
            }
        return None
    finally:
        conn.close()


def get_meeting_status(meeting_id: str):
    """Retrieve meeting status from SQLite database."""
    db_path = Path(settings.db_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
        
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status FROM meetings WHERE zoom_meeting_id = ?", (meeting_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def start_bot_process():
    """Start the bot in a background subprocess."""
    # Ensure stale lock file is removed
    lock_file = PROJECT_ROOT / "bot.lock"
    if lock_file.exists():
        try:
            lock_file.unlink()
            print("Removed stale bot.lock")
        except Exception as e:
            print(f"Warning: Failed to remove bot.lock: {e}")
            
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "test_bot_runner.log"
    log_file = open(log_path, "w", encoding="utf-8")
    
    print(f"Launching bot subprocess (logs at {log_path})...")
    bot_env = os.environ.copy()
    bot_env["LOG_LEVEL"] = "DEBUG"
    bot_env["ENABLE_DEPENDENCY_AUDIT"] = "false"
    
    process = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=str(PROJECT_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=bot_env,
        text=True
    )
    return process, log_file


def stop_bot_process(process, log_file):
    """Stop the bot subprocess cleanly."""
    print("Stopping bot subprocess...")
    if process:
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
                print("Bot process terminated cleanly.")
            except subprocess.TimeoutExpired:
                print("Bot process did not exit in 5s. Force killing...")
                process.kill()
                process.wait()
        except Exception as e:
            print(f"Error stopping bot process: {e}")
            
    if log_file:
        log_file.close()


def _buttons_are_different(btn_list1, btn_list2):
    if btn_list1 is None or btn_list2 is None:
        return btn_list1 != btn_list2
    
    # Flatten button lists and extract text and data content for stable comparison
    flat1 = []
    if isinstance(btn_list1, list):
        for row in btn_list1:
            for b in row:
                flat1.append((b.text, getattr(b, 'data', None)))
                
    flat2 = []
    if isinstance(btn_list2, list):
        for row in btn_list2:
            for b in row:
                flat2.append((b.text, getattr(b, 'data', None)))
                
    return flat1 != flat2


async def wait_for_bot_response(client, bot_username, last_msg=None, timeout=15):
    """Waits for either a new message or for the text/buttons of last_msg to change."""
    start_time = time.time()
    last_text = last_msg.text if last_msg else ""
    last_id = last_msg.id if last_msg else None
    last_buttons = last_msg.buttons if last_msg else None
    
    print(f"[DEBUG] wait_for_bot_response: last_id={last_id}, last_text_len={len(last_text)}")
    
    while time.time() - start_time < timeout:
        await asyncio.sleep(0.5)
        # Fetch latest messages
        messages = await client.get_messages(bot_username, limit=1)
        if not messages:
            continue
        new_msg = messages[0]
        
        # If the latest message has the same ID as last_msg, force-fetch by ID to bypass Telethon's cache
        if last_id is not None and new_msg.id == last_id:
            new_msg = await client.get_messages(bot_username, ids=last_id)
            if new_msg is None:
                continue
        
        # Scenario A: A new message was sent
        if last_id is None or new_msg.id != last_id:
            print(f"[DEBUG] Scenario A: new message ID {new_msg.id} != last_id {last_id}")
            return new_msg
            
        # Scenario B: The message was edited in place (text changed)
        if new_msg.text != last_text:
            print(f"[DEBUG] Scenario B: text changed from len {len(last_text)} to {len(new_msg.text)}")
            return new_msg
            
        # Scenario C: The buttons changed
        if _buttons_are_different(new_msg.buttons, last_buttons):
            print(f"[DEBUG] Scenario C: buttons changed")
            return new_msg
            
    print(f"[DEBUG] Timeout reached. Current new_msg.id={new_msg.id}, text_len={len(new_msg.text)}")
    raise TimeoutError(f"Timeout waiting for bot response. Last message text: '{last_text}'")


async def run_meeting_details_controls_test():
    """Runs the integration test suite for Zoom Controls and Meeting Details."""
    # 1. Load credentials
    creds = load_credentials()
    api_id = creds["api_id"]
    api_hash = creds["api_hash"]
    phone = creds["phone"]
    bot_username = creds["bot_username"]
    
    print("\n--- Connecting Telegram Client ---")
    session_path = PROJECT_ROOT / "tests" / "test_session"
    client = TelegramClient(str(session_path), api_id, api_hash)
    
    # Start client (uses cached session file, completely headless)
    await client.start(phone=phone)
    print("Telegram client connected.")
    
    # 2. Get client info and whitelist in database
    me = await client.get_me()
    telegram_id = me.id
    username = me.username or f"test_user_{me.id}"
    print(f"Test account: ID={telegram_id}, Username={username}")
    
    # Run DB init to ensure tables exist
    print("Initializing database schema...")
    await init_db()
    
    # Whitelist the test user
    whitelist_user(telegram_id, username)
    
    # 3. Start bot process
    bot_proc, log_file = start_bot_process()
    
    try:
        # Give bot 5 seconds to start up and connect
        print("Waiting 5 seconds for bot to initialize...")
        await asyncio.sleep(5)
        
        # Check if process is still running
        if bot_proc.poll() is not None:
            log_content = ""
            try:
                log_path = PROJECT_ROOT / "logs" / "test_bot_runner.log"
                if log_path.exists():
                    with open(log_path, "r", encoding="utf-8") as lf:
                        log_content = lf.read()
            except Exception:
                pass
                
            if "conflict" in log_content.lower() or "terminated by other" in log_content.lower():
                raise RuntimeError(
                    "❌ Bot failed to start due to Telegram Token Conflict. "
                    "Please stop any other running instances of the bot before running this test."
                )
            else:
                raise RuntimeError(
                    f"❌ Bot process exited unexpectedly with code {bot_proc.returncode}.\n"
                    f"Logs tail:\n{log_content[-1000:] if log_content else 'No logs'}"
                )
        
        # 4. Interact with Bot: Send /start
        print("\n--- Sending /start command ---")
        msg = await client.send_message(bot_username, "/start")
        
        # Wait for bot response (greeting and main menu keyboard)
        response = await wait_for_bot_response(client, bot_username, msg)
        print("Received bot start response:")
        print(response.text)
        
        assert "zoom telebot" in response.text.lower() or "role" in response.text.lower(), \
            "Bot did not respond with expected startup greeting or menu"
        assert response.buttons, "Main menu response does not contain buttons"
        
        # Find "➕ Create Meeting!" button
        create_btn = None
        for row in response.buttons:
            for btn in row:
                if "Create Meeting" in btn.text:
                    create_btn = btn
                    break
        assert create_btn, "Could not find 'Create Meeting' button in main menu"
        print(f"Found button: {create_btn.text}. Clicking it...")
        await create_btn.click()
        
        # Fill in FSM Steps (Topic -> Date -> Time -> Confirm)
        prompt_topic = await wait_for_bot_response(client, bot_username, response)
        topic_text = f"Controls and Details Test {int(time.time())}"
        print(f"Sending Topic: '{topic_text}'")
        msg_topic = await client.send_message(bot_username, topic_text)
        
        prompt_date = await wait_for_bot_response(client, bot_username, msg_topic)
        from datetime import datetime, timedelta
        tomorrow = datetime.now() + timedelta(days=1)
        date_str = tomorrow.strftime("%d-%m-%Y")
        print(f"Sending Date: '{date_str}'")
        msg_date = await client.send_message(bot_username, date_str)
        
        prompt_time = await wait_for_bot_response(client, bot_username, msg_date)
        print(f"Sending Time: '14:30'")
        msg_time = await client.send_message(bot_username, "14:30")
        
        prompt_confirm = await wait_for_bot_response(client, bot_username, msg_time)
        confirm_btn = next(btn for row in prompt_confirm.buttons for btn in row if "Konfirmasi" in btn.text)
        print("Clicking 'Konfirmasi'...")
        await confirm_btn.click()
        
        # Wait for success message
        success_msg = await wait_for_bot_response(client, bot_username, prompt_confirm, timeout=25)
        print("Received bot success message.")
        
        # Get meeting details from DB
        latest_meet = get_latest_meeting(telegram_id)
        assert latest_meet, "Meeting record not found in database"
        meeting_id = latest_meet["meeting_id"]
        print(f"Created meeting ID: {meeting_id}")
        
        # 5. Open Meeting List
        print("\n--- Opening Meeting List ---")
        msg_list_start = await client.send_message(bot_username, "/start")
        resp_list_start = await wait_for_bot_response(client, bot_username, msg_list_start)
        list_btn = next(btn for row in resp_list_start.buttons for btn in row if "List Meeting" in btn.text)
        print("Clicking 'List Meeting'...")
        await list_btn.click()
        
        list_view = await wait_for_bot_response(client, bot_username, resp_list_start)
        print("Received meeting list view.")
        
        # 6. Click "🎥 {topic_short}" to open Zoom Control screen
        print(f"\n--- Clicking '🎥 {topic_text[:20]}' to open Zoom Control screen ---")
        control_btn = None
        for row in list_view.buttons:
            for btn in row:
                if btn.data and btn.data.decode().startswith(f"control_zoom:{meeting_id}"):
                    control_btn = btn
                    break
        assert control_btn, f"Could not find Zoom Control button for meeting {meeting_id}"
        print("Clicking Zoom Control button...")
        await control_btn.click()
        
        control_screen = await wait_for_bot_response(client, bot_username, list_view)
        print("Received Zoom Control screen:")
        print(control_screen.text)
        
        # Assert Zoom Control screen contents
        assert "kontrol zoom meeting" in control_screen.text.lower(), "Screen header mismatch"
        assert meeting_id in control_screen.text, "Meeting ID not found in screen text"
        assert "status:" in control_screen.text.lower(), "Status label not found in screen text"
        assert "participants:" in control_screen.text.lower(), "Participants label not found in screen text"
        assert "recording:" in control_screen.text.lower(), "Recording label not found in screen text"
        assert control_screen.buttons, "Zoom Control screen has no buttons"
        
        # 7. Click "📊 Meeting Details" button
        print("\n--- Clicking '📊 Meeting Details' ---")
        details_btn = None
        for row in control_screen.buttons:
            for btn in row:
                if btn.data and btn.data.decode().startswith(f"zoom_meeting_details:{meeting_id}"):
                    details_btn = btn
                    break
        assert details_btn, "Could not find 'Meeting Details' button"
        print("Clicking Meeting Details button...")
        await details_btn.click()
        
        details_screen = await wait_for_bot_response(client, bot_username, control_screen)
        print("Received Meeting Details screen:")
        print(details_screen.text)
        
        # Assert Meeting Details screen contents
        assert "meeting details" in details_screen.text.lower(), "Details screen header mismatch"
        assert f"id:" in details_screen.text.lower() and meeting_id in details_screen.text, "Meeting ID mismatch"
        assert "passcode:" in details_screen.text.lower(), "Passcode label not found in details screen"
        assert "topic:" in details_screen.text.lower(), "Topic label not found in details screen"
        assert "host:" in details_screen.text.lower(), "Host email label not found in details screen"
        assert "join url:" in details_screen.text.lower(), "Join URL label not found in details screen"
        assert details_screen.buttons, "Details screen has no buttons"
        
        # 8. Click "🎥 Kembali ke Kontrol" to navigate back
        print("\n--- Clicking '🎥 Kembali ke Kontrol' ---")
        back_btn = None
        for row in details_screen.buttons:
            for btn in row:
                if btn.data and btn.data.decode().startswith(f"control_zoom:{meeting_id}"):
                    back_btn = btn
                    break
        assert back_btn, "Could not find 'Kembali ke Kontrol' button"
        print("Clicking back button...")
        await back_btn.click()
        
        returned_control_screen = await wait_for_bot_response(client, bot_username, details_screen)
        print("Returned to Zoom Control screen:")
        print(returned_control_screen.text)
        
        # Assert we are back on the Zoom Control page
        assert "kontrol zoom meeting" in returned_control_screen.text.lower(), "Failed to navigate back to Control screen"
        
        # 9. Clean up: Delete the meeting via command /zoom_del <id>
        print(f"\n--- Cleaning up: Deleting meeting {meeting_id} ---")
        msg_del = await client.send_message(bot_username, f"/zoom_del {meeting_id}")
        del_proc_msg = await wait_for_bot_response(client, bot_username, msg_del)
        del_result_msg = await wait_for_bot_response(client, bot_username, del_proc_msg, timeout=25)
        
        # Verify in DB with retry loop
        db_status = None
        for _ in range(10):
            db_status = get_meeting_status(meeting_id)
            if db_status == "deleted":
                break
            await asyncio.sleep(0.5)
        assert db_status == "deleted", "Failed to delete meeting during cleanup"
        print("✅ Cleanup complete. Meeting deleted.")
        
        print("\n🎉 ZOOM CONTROLS & MEETING DETAILS TESTS PASSED SUCCESSFULLY! 🎉\n")
        
    finally:
        stop_bot_process(bot_proc, log_file)
        await client.disconnect()
        # See test_bot_integration for why this is in finally rather than at
        # the end of the happy path.
        await cleanup_zoom_meetings("test_meeting_details_controls")


@pytest.mark.asyncio
async def test_meeting_details_controls_integration():
    """Pytest entrypoint for Zoom Controls and Meeting Details integration tests."""
    await run_meeting_details_controls_test()


if __name__ == "__main__":
    asyncio.run(run_meeting_details_controls_test())
