#!/usr/bin/env python3
"""
Simple development runner for Zoom-Telebot SOC
Provides easy commands for development and testing
"""

import os
import sys
import subprocess
import argparse
import time
from pathlib import Path
from threading import Event

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

PROJECT_ROOT = Path(__file__).resolve().parent

# File watching configuration
WATCH_EXTENSIONS = {'.py', '.json'}
EXCLUDE_FILES = {'zoom_telebot.db'}
EXCLUDE_DIRS = {'.venv', '__pycache__', '.git', '.obsidian', '.idea'}
DEBOUNCE_SECONDS = 0.5

class AutoRestartHandler(FileSystemEventHandler):
    """File system event handler for auto-restart functionality."""

    def __init__(self, restart_event: Event):
        super().__init__()
        self.restart_event = restart_event
        self._last_restart = 0.0

    def _should_trigger_restart(self, src_path: str) -> bool:
        """Check if the file change should trigger a restart."""
        path = Path(src_path)

        # Check file extension
        if path.suffix not in WATCH_EXTENSIONS:
            return False

        # Check if file should be excluded
        if path.name in EXCLUDE_FILES:
            return False

        # Check if path contains excluded directories
        for part in path.parts:
            if part in EXCLUDE_DIRS:
                return False

        return True

    def on_any_event(self, event):
        """Handle file system events."""
        try:
            src_path = str(event.src_path)
            if not self._should_trigger_restart(src_path):
                return
        except Exception:
            return

        # Debounce to avoid multiple restarts for the same change
        now = time.time()
        if now - self._last_restart < DEBOUNCE_SECONDS:
            return

        self._last_restart = now
        print(f"🔄 Detected change in {Path(src_path).relative_to(PROJECT_ROOT)} -> scheduling restart")
        self.restart_event.set()

def run_command(cmd, desc=""):
    """Run a command and return success status."""
    print(f"🔧 {desc}")
    print(f"   Command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        return result.returncode == 0
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def setup_environment():
    """Setup environment before running."""
    print("🚀 Setting up environment...")
    return run_command([sys.executable, "setup.py"], "Running setup script")

def run_bot():
    """Run the bot."""
    print("🤖 Starting bot...")
    os.environ.setdefault('LOG_LEVEL', 'INFO')
    return run_command([sys.executable, "main.py"], "Running bot")

def run_bot_debug():
    """Run the bot with debug logging."""
    print("🐛 Starting bot in debug mode...")
    os.environ['LOG_LEVEL'] = 'DEBUG'
    return run_command([sys.executable, "main.py"], "Running bot with debug logging")

def run_bot_with_auto_restart(debug=False):
    """Run the bot with auto-restart on file changes."""
    if not WATCHDOG_AVAILABLE:
        print("❌ watchdog library is required for auto-restart functionality.")
        print("   Install with: pip install watchdog")
        return False

    if debug:
        print("🐛 Starting bot in debug mode with auto-restart...")
        os.environ['LOG_LEVEL'] = 'DEBUG'
    else:
        print("🤖 Starting bot with auto-restart...")
        os.environ.setdefault('LOG_LEVEL', 'INFO')

    # Import watchdog components (already checked availability above)
    from watchdog.observers import Observer

    # Setup file watching
    restart_event = Event()
    event_handler = AutoRestartHandler(restart_event)
    observer = Observer()
    observer.schedule(event_handler, str(PROJECT_ROOT), recursive=True)
    observer.start()

    def start_bot_process():
        """Start the bot process."""
        cmd = [sys.executable, str(PROJECT_ROOT / 'main.py')]
        env = os.environ.copy()
        print(f"🚀 Starting bot process: {' '.join(cmd)}")
        return subprocess.Popen(cmd, stdout=None, stderr=None, cwd=str(PROJECT_ROOT), env=env)

    # Start initial bot process
    bot_process = start_bot_process()

    try:
        while True:
            # Wait for file change event
            if restart_event.wait(timeout=1.0):  # Check every second
                restart_event.clear()
                print("🔄 Restarting bot due to file changes...")

                # Terminate current process
                try:
                    bot_process.terminate()
                    bot_process.wait(timeout=5)
                    print("✅ Previous bot process terminated")
                except subprocess.TimeoutExpired:
                    print("⚠️  Force killing previous bot process...")
                    bot_process.kill()
                except Exception as e:
                    print(f"⚠️  Error terminating process: {e}")

                # Small pause to let file operations complete
                time.sleep(0.5)

                # Start new bot process
                bot_process = start_bot_process()

    except KeyboardInterrupt:
        print("\n⚠️  Stopping auto-restart and terminating bot...")
    except Exception as e:
        print(f"\n❌ Error in auto-restart: {e}")
    finally:
        observer.stop()
        observer.join()
        try:
            bot_process.terminate()
            bot_process.wait(timeout=3)
        except Exception:
            try:
                bot_process.kill()
            except Exception:
                pass
        print("✅ Auto-restart stopped")

    return True

def test_imports():
    """Test Python imports."""
    print("🧪 Testing imports...")
    test_files = ['config', 'handlers', 'db', 'zoom', 'shortener']
    success = True

    for module in test_files:
        if not run_command([sys.executable, "-c", f"import {module}; print('{module}: OK')"],
                          f"Testing {module} import"):
            success = False

    return success

def show_help():
    """Show help information."""
    print("🤖 Zoom-Telebot SOC Development Commands")
    print("=" * 50)
    print()
    print("USAGE:")
    print("  python dev.py <command> [options]")
    print()
    print("COMMANDS:")
    print("  setup    - Setup environment (validation + initialization)")
    print("  run      - Run bot with normal logging")
    print("  debug    - Run bot with debug logging")
    print("  test     - Test Python imports")
    print("  help     - Show this help")
    print()
    print("OPTIONS:")
    print("  --watch  - Enable auto-restart on file changes (.py and .json files)")
    print("             Excludes: database files, .venv, __pycache__, .git")
    print()
    print("EXAMPLES:")
    print("  python dev.py setup           # Setup environment first")
    print("  python dev.py run             # Run bot (auto-setup)")
    print("  python dev.py run --watch     # Run bot with auto-restart")
    print("  python dev.py debug --watch   # Run with debug logs + auto-restart")
    print("  python dev.py test            # Test imports only")
    print()

def main():
    parser = argparse.ArgumentParser(
        description="Zoom-Telebot SOC Development Runner",
        prog="python dev.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  python dev.py setup           # Setup environment first
  python dev.py run             # Run bot (auto-setup)
  python dev.py run --watch     # Run bot with auto-restart
  python dev.py debug --watch   # Run with debug logs + auto-restart
  python dev.py test            # Test imports only
        """
    )

    parser.add_argument(
        'command',
        choices=['setup', 'run', 'debug', 'test', 'help'],
        help='Command to execute'
    )

    parser.add_argument(
        '--watch',
        action='store_true',
        help='Enable auto-restart on file changes (.py and .json files)'
    )

    args = parser.parse_args()

    if args.command == 'help':
        show_help()
        return 0

    print("🤖 Zoom-Telebot SOC Development Runner")
    print("=" * 50)

    if args.command == 'setup':
        return 0 if setup_environment() else 1

    elif args.command == 'run':
        if not setup_environment():
            print("❌ Setup failed.")
            return 1
        if args.watch:
            if not WATCHDOG_AVAILABLE:
                print("❌ Watchdog library not available. Install with: pip install watchdog")
                return 1
            return 0 if run_bot_with_auto_restart() else 1
        else:
            return 0 if run_bot() else 1

    elif args.command == 'debug':
        if not setup_environment():
            print("❌ Setup failed.")
            return 1
        if args.watch:
            if not WATCHDOG_AVAILABLE:
                print("❌ Watchdog library not available. Install with: pip install watchdog")
                return 1
            return 0 if run_bot_with_auto_restart(debug=True) else 1
        else:
            return 0 if run_bot_debug() else 1

    elif args.command == 'test':
        return 0 if test_imports() else 1

    return 0

if __name__ == "__main__":
    sys.exit(main())