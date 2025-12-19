#!/usr/bin/env python3
"""
Development runner for Zoom-Telebot SOC with auto-restart capability.

Provides easy commands for development and testing with file watching.
Auto-restarts the bot when Python or JSON files are modified.
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
    # Create dummy classes to avoid NameError
    class FileSystemEventHandler:
        """Dummy class when watchdog is not available."""
        pass
    Observer = None

PROJECT_ROOT = Path(__file__).resolve().parent

def find_python_executable():
    """Find the correct Python executable that has the required dependencies."""
    import subprocess
    
    # First, try the current sys.executable
    try:
        result = subprocess.run([sys.executable, "-c", "import config; print('OK')"], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.returncode == 0:
            return sys.executable
    except Exception:
        pass
    
    # If current doesn't work, try common system Python locations
    candidates = [
        r"C:\Users\primall\AppData\Local\Programs\Python\Python314\python.exe",
        r"C:\Users\primall\AppData\Local\Programs\Python\Python313\python.exe", 
        r"C:\Users\primall\AppData\Local\Programs\Python\Python312\python.exe",
        r"C:\Python314\python.exe",
        r"C:\Python313\python.exe",
        r"C:\Python312\python.exe",
    ]
    
    for candidate in candidates:
        try:
            if Path(candidate).exists():
                result = subprocess.run([candidate, "-c", "import config; print('OK')"], 
                                      capture_output=True, text=True, cwd=PROJECT_ROOT)
                if result.returncode == 0:
                    return candidate
        except Exception:
            continue
    
    # Fallback to sys.executable if nothing else works
    return sys.executable

# Use system Python instead of whatever is in PATH (avoids Inkscape Python issues)
PYTHON_EXE = find_python_executable()

# File watching configuration
WATCH_EXTENSIONS = {'.py', '.json'}
EXCLUDE_FILES = {'zoom_telebot.db', 'bot.db'}
EXCLUDE_DIRS = {'.venv', '__pycache__', '.git', '.obsidian', '.idea', 'logs', 'c2_server', 'docker'}
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
        try:
            rel_path = Path(src_path).relative_to(PROJECT_ROOT)
        except ValueError:
            rel_path = Path(src_path).name
        print(f"🔄 Detected change in {rel_path} -> scheduling restart")
        self.restart_event.set()


def run_command(cmd, desc=""):
    """Run a command and return success status."""
    print(f"🔧 {desc}")
    # Replace sys.executable with PYTHON_EXE if it's the first element
    if cmd and cmd[0] == sys.executable:
        cmd = [PYTHON_EXE] + cmd[1:]
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
    setup_script = PROJECT_ROOT / "scripts" / "setup.py"
    if setup_script.exists():
        return run_command([sys.executable, str(setup_script)], "Running setup script")
    else:
        print("⚠️  Setup script not found, skipping...")
        return True


def run_bot():
    """Run the bot."""
    print("🤖 Starting bot...")
    os.environ.setdefault('LOG_LEVEL', 'INFO')
    return run_command([sys.executable, "run.py"], "Running bot")


def run_bot_debug():
    """Run the bot with debug logging."""
    print("🐛 Starting bot in debug mode...")
    os.environ['LOG_LEVEL'] = 'DEBUG'
    return run_command([sys.executable, "run.py", "--log-level", "DEBUG"], "Running bot with debug logging")


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
        cmd = [PYTHON_EXE, str(PROJECT_ROOT / 'run.py')]
        if debug:
            cmd.extend(['--log-level', 'DEBUG'])
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
    test_modules = ['config', 'bot', 'db', 'zoom', 'shortener', 'c2']
    success = True

    for module in test_modules:
        try:
            result = subprocess.run(
                [PYTHON_EXE, "-c", f"import {module}; print('{module}: OK')"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"   ✅ {module}: OK")
            else:
                print(f"   ❌ {module}: FAILED")
                if result.stderr:
                    print(f"      Error: {result.stderr.strip()}")
                success = False
        except Exception as e:
            print(f"   ❌ {module}: ERROR - {e}")
            success = False

    return success


def check_config():
    """Check configuration."""
    print("🔍 Checking configuration...")
    return run_command([PYTHON_EXE, "run.py", "--check-config"], "Checking config")


def show_help():
    """Show help information."""
    print("🤖 Zoom-Telebot SOC Development Commands")
    print("=" * 50)
    print()
    print("USAGE:")
    print("  python dev.py <command> [options]")
    print()
    print("COMMANDS:")
    print("  setup       - Setup environment (validation + initialization)")
    print("  run         - Run bot with normal logging")
    print("  debug       - Run bot with debug logging")
    print("  test        - Test Python imports")
    print("  check       - Check configuration")
    print("  help        - Show this help")
    print()
    print("OPTIONS:")
    print("  --watch     - Enable auto-restart on file changes (.py and .json files)")
    print("                Excludes: database files, .venv, __pycache__, .git, logs")
    print()
    print("EXAMPLES:")
    print("  python dev.py setup              # Setup environment first")
    print("  python dev.py run                # Run bot (auto-setup)")
    print("  python dev.py run --watch        # Run bot with auto-restart")
    print("  python dev.py debug --watch      # Run with debug logs + auto-restart")
    print("  python dev.py test               # Test imports only")
    print("  python dev.py check              # Check configuration")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Zoom-Telebot SOC Development Runner",
        prog="python dev.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  python dev.py setup              # Setup environment first
  python dev.py run                # Run bot (auto-setup)
  python dev.py run --watch        # Run bot with auto-restart
  python dev.py debug --watch      # Run with debug logs + auto-restart
  python dev.py test               # Test imports only
  python dev.py check              # Check configuration
        """
    )

    parser.add_argument(
        'command',
        choices=['setup', 'run', 'debug', 'test', 'check', 'help'],
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

    elif args.command == 'check':
        return 0 if check_config() else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
