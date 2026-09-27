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


def _read_log_tail(log_path, limit=2000):
    """Return the last `limit` chars of the bot log, or '' if unreadable."""
    try:
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                return lf.read()[-limit:]
    except OSError:
        pass
    return ""

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
            return new_msg
            
        # Scenario B: The message was edited in place (text changed)
        if new_msg.text != last_text:
            return new_msg
            
        # Scenario C: The buttons changed
        if _buttons_are_different(new_msg.buttons, last_buttons):
            return new_msg
            
    raise TimeoutError(f"Timeout waiting for bot response. Last message text: '{last_text}'")


async def run_integration_test():
    """Runs the full Telegram bot integration test suite."""
    # 1. Load credentials
    creds = load_credentials()
    api_id = creds["api_id"]
    api_hash = creds["api_hash"]
    phone = creds["phone"]
    bot_username = creds["bot_username"]
    
    print("\n--- Connecting Telegram Client ---")
    session_path = PROJECT_ROOT / "tests" / "test_session"
    client = TelegramClient(str(session_path), api_id, api_hash)
    
    # Start client (will prompt for OTP code on terminal if first-time run)
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
        # Wait until the bot is actually polling. A fixed sleep races with
        # on_startup(), which blocks on the initial Zoom sync before the
        # dispatcher starts consuming updates; on a slow machine the first
        # /start can arrive before polling begins and is never answered.
        # ponytail: log-line polling instead of a health endpoint. Upgrade to
        # /health if the bot ever grows one.
        print("Waiting for bot to begin polling...")
        log_path = PROJECT_ROOT / "logs" / "test_bot_runner.log"
        ready_marker = "Run polling for bot"
        deadline = time.time() + 45
        while time.time() < deadline:
            if bot_proc.poll() is not None:
                break
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                    if ready_marker in lf.read():
                        print("Bot is polling.")
                        break
            except FileNotFoundError:
                pass
            await asyncio.sleep(0.5)
        else:
            raise RuntimeError(
                f"Bot did not start polling within 45s.\n"
                f"Logs tail:\n{_read_log_tail(log_path)}"
            )
        
        # Check if process is still running
        if bot_proc.poll() is not None:
            # Process terminated early! Let's read the logs to see why
            log_content = _read_log_tail(log_path, limit=4000)
                
            if "conflict" in log_content.lower() or "terminated by other" in log_content.lower():
                raise RuntimeError(
                    "❌ Bot failed to start due to Telegram Token Conflict. "
                    "Please stop any other running instances of the bot (e.g. docker containers or dev.py) before running this test."
                )
            else:
                raise RuntimeError(
                    f"❌ Bot process exited unexpectedly with code {bot_proc.returncode}.\n"
                    f"Logs tail:\n{log_content if log_content else 'No logs'}"
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
        
        # 5. Click "➕ Create Meeting!"
        await create_btn.click()
        
        # Wait for the bot to edit the message to ask for Topic (Step 1/3)
        prompt_topic = await wait_for_bot_response(client, bot_username, response)
        print("Received bot prompt:")
        print(prompt_topic.text)
        assert "Step 1" in prompt_topic.text or "Topic" in prompt_topic.text, "Bot did not prompt for step 1 (Topic)"
        
        # 6. Send Topic
        topic_text = f"Integration Test Meeting {int(time.time())}"
        print(f"Sending Topic: '{topic_text}'")
        msg_topic = await client.send_message(bot_username, topic_text)
        
        # Wait for bot prompt for Date (Step 2/3)
        prompt_date = await wait_for_bot_response(client, bot_username, msg_topic)
        print("Received bot prompt:")
        print(prompt_date.text)
        assert "Step 2" in prompt_date.text or "Kapan" in prompt_date.text, "Bot did not prompt for step 2 (Date)"
        
        # 7. Send Date (dynamically tomorrow)
        from datetime import datetime, timedelta
        tomorrow = datetime.now() + timedelta(days=1)
        # Format DD-MM-YYYY
        date_str = tomorrow.strftime("%d-%m-%Y")
        print(f"Sending Date: '{date_str}'")
        msg_date = await client.send_message(bot_username, date_str)
        
        # Wait for bot prompt for Time (Step 3/3)
        prompt_time = await wait_for_bot_response(client, bot_username, msg_date)
        print("Received bot prompt:")
        print(prompt_time.text)
        assert "Step 3" in prompt_time.text or "waktu" in prompt_time.text, "Bot did not prompt for step 3 (Time)"
        
        # 8. Send Time
        time_str = "14:30"
        print(f"Sending Time: '{time_str}'")
        msg_time = await client.send_message(bot_username, time_str)
        
        # Wait for confirmation prompt
        prompt_confirm = await wait_for_bot_response(client, bot_username, msg_time)
        print("Received bot prompt:")
        print(prompt_confirm.text)
        assert "Konfirmasi" in prompt_confirm.text, "Bot did not prompt for Confirmation"
        assert prompt_confirm.buttons, "Confirmation message does not have buttons"
        
        # Find "✅ Konfirmasi" button
        confirm_btn = None
        for row in prompt_confirm.buttons:
            for btn in row:
                if "Konfirmasi" in btn.text:
                    confirm_btn = btn
                    break
                    
        assert confirm_btn, "Could not find 'Konfirmasi' button"
        print("Clicking 'Konfirmasi'...")
        
        # 9. Click Confirm
        await confirm_btn.click()
        
        # Wait for success message (creating meeting might take a few seconds)
        success_msg = await wait_for_bot_response(client, bot_username, prompt_confirm, timeout=25)
        print("Received bot success message:")
        print(success_msg.text)
        assert "Berikut disampaikan" in success_msg.text or "join" in success_msg.text.lower(), \
            "Meeting creation failed"
        
        # 10. Verify in SQLite Database
        print("Checking meeting creation in SQLite Database...")
        latest_meet = get_latest_meeting(telegram_id)
        assert latest_meet, "Meeting record not found in database"
        assert latest_meet["topic"] == topic_text, f"Database topic mismatch: {latest_meet['topic']} vs {topic_text}"
        assert latest_meet["status"] == "active", f"Database meeting status is not active: {latest_meet['status']}"
        meeting_id = latest_meet["meeting_id"]
        print(f"✅ Success: Meeting {meeting_id} is ACTIVE in database.")
        
        # 11. Test Deletion via Command: /zoom_del <id>
        print(f"\n--- Testing Deletion via Command: /zoom_del {meeting_id} ---")
        msg_del = await client.send_message(bot_username, f"/zoom_del {meeting_id}")
        
        # Wait for processing message
        del_proc_msg = await wait_for_bot_response(client, bot_username, msg_del)
        print("Received bot delete status:")
        print(del_proc_msg.text)
        
        # Wait for final result message
        del_result_msg = await wait_for_bot_response(client, bot_username, del_proc_msg, timeout=25)
        print("Received bot delete result:")
        print(del_result_msg.text)
        assert "Berhasil" in del_result_msg.text or "deleted" in del_result_msg.text.lower(), \
            f"Bot delete command response indicates failure: {del_result_msg.text}"
        
        # Verify in DB that it is marked deleted (with retry loop to avoid race conditions)
        db_status = None
        for _ in range(10):
            db_status = get_meeting_status(meeting_id)
            if db_status == "deleted":
                break
            await asyncio.sleep(0.5)
        assert db_status == "deleted", f"Meeting {meeting_id} status in DB is '{db_status}', expected 'deleted'"
        print(f"✅ Success: Meeting {meeting_id} status updated to DELETED in database.")
        
        # 12. Create another meeting to test inline button deletion
        print("\n--- Creating a second meeting to test inline button deletion ---")
        msg_start_2 = await client.send_message(bot_username, "/start")
        resp_2 = await wait_for_bot_response(client, bot_username, msg_start_2)
        
        create_btn_2 = None
        for row in resp_2.buttons:
            for btn in row:
                if "Create Meeting" in btn.text:
                    create_btn_2 = btn
                    break
        assert create_btn_2
        await create_btn_2.click()
        
        prompt_topic_2 = await wait_for_bot_response(client, bot_username, resp_2)
        topic_text_2 = f"Inline Deletion Test {int(time.time())}"
        msg_topic_2 = await client.send_message(bot_username, topic_text_2)
        
        prompt_date_2 = await wait_for_bot_response(client, bot_username, msg_topic_2)
        msg_date_2 = await client.send_message(bot_username, date_str)
        
        prompt_time_2 = await wait_for_bot_response(client, bot_username, msg_date_2)
        msg_time_2 = await client.send_message(bot_username, time_str)
        
        prompt_confirm_2 = await wait_for_bot_response(client, bot_username, msg_time_2)
        confirm_btn_2 = None
        for row in prompt_confirm_2.buttons:
            for btn in row:
                if "Konfirmasi" in btn.text:
                    confirm_btn_2 = btn
                    break
        assert confirm_btn_2
        await confirm_btn_2.click()
        
        success_msg_2 = await wait_for_bot_response(client, bot_username, prompt_confirm_2, timeout=25)
        print("Second meeting created successfully.")
        
        latest_meet_2 = get_latest_meeting(telegram_id)
        meeting_id_2 = latest_meet_2["meeting_id"]
        assert latest_meet_2["status"] == "active"
        
        # 13. Test Deletion via Inline Buttons
        print("\n--- Testing Deletion via Inline Buttons ---")
        msg_list = await client.send_message(bot_username, "/start")
        resp_list = await wait_for_bot_response(client, bot_username, msg_list)
        
        list_btn = None
        for row in resp_list.buttons:
            for btn in row:
                if "List Meeting" in btn.text:
                    list_btn = btn
                    break
        assert list_btn, "Could not find 'List Meeting' button"
        print("Clicking 'List Meeting'...")
        await list_btn.click()
        
        list_view = await wait_for_bot_response(client, bot_username, resp_list)
        print("Received list view:")
        print(list_view.text)
        assert list_view.buttons, "List view has no buttons"
        
        # Find the delete button for meeting_id_2
        delete_btn = None
        for row in list_view.buttons:
            for btn in row:
                if btn.data and btn.data.decode().startswith(f"confirm_delete:{meeting_id_2}"):
                    delete_btn = btn
                    break
        assert delete_btn, f"Could not find delete button for meeting {meeting_id_2}"
        print(f"Found delete button for {meeting_id_2}. Clicking it...")
        await delete_btn.click()
        
        # Wait for delete confirmation prompt
        delete_prompt = await wait_for_bot_response(client, bot_username, list_view)
        print("Received delete prompt:")
        print(delete_prompt.text)
        assert delete_prompt.buttons, "Did not load delete confirmation menu"
            
        # Find "✅ Ya, Hapus Meeting" button
        yes_delete_btn = None
        for row in delete_prompt.buttons:
            for btn in row:
                if "Ya" in btn.text:
                    yes_delete_btn = btn
                    break
        assert yes_delete_btn, "Could not find 'Ya, Hapus Meeting' button"
        print("Clicking 'Ya, Hapus Meeting'...")
        await yes_delete_btn.click()
        
        # Wait for it to return to meeting list or send success
        final_list_view = await wait_for_bot_response(client, bot_username, delete_prompt, timeout=25)
        print("Deleted meeting. Current view text:")
        print(final_list_view.text)
        
        # Verify in DB that it is marked deleted (with retry loop to avoid race conditions)
        db_status_2 = None
        for _ in range(10):
            db_status_2 = get_meeting_status(meeting_id_2)
            if db_status_2 == "deleted":
                break
            await asyncio.sleep(0.5)
        assert db_status_2 == "deleted", f"Meeting {meeting_id_2} status in DB is '{db_status_2}', expected 'deleted'"
        print(f"✅ Success: Second meeting {meeting_id_2} status updated to DELETED in database.")
        
        print("\n🎉 ALL INTEGRATION TESTS PASSED SUCCESSFULLY! 🎉\n")
        
    finally:
        # Cleanup
        stop_bot_process(bot_proc, log_file)
        await client.disconnect()
        # Zoom-side cleanup goes in finally, not at the end of the happy path.
        # Every failure above left a real meeting on the real Zoom account; four
        # of them piled up in one afternoon. Runs before disconnect would be
        # wasted - this talks to Zoom, not Telegram.
        await cleanup_zoom_meetings("test_bot_integration")


@pytest.mark.asyncio
async def test_telegram_bot_integration():
    """Pytest entrypoint for Telegram bot integration tests."""
    await run_integration_test()


if __name__ == "__main__":
    # Standard script run execution
    asyncio.run(run_integration_test())
