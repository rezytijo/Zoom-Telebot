#!/usr/bin/env python3
"""
Simple development runner for Zoom-Telebot SOC
Provides easy commands for development and testing
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

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

def check_env():
    """Check environment configuration."""
    print("🔍 Checking environment...")

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        print("✅ .env file found - loading environment variables from file")
    else:
        print("⚠️  .env file not found - using OS environment variables")
        print("   Note: Make sure required environment variables are set")

    # Import settings to trigger dotenv loading
    try:
        from config import settings

        # Basic validation of critical environment variables
        missing_vars = []
        if not settings.bot_token:
            missing_vars.append("TELEGRAM_TOKEN")
        if not settings.owner_id:
            missing_vars.append("INITIAL_OWNER_ID")

        if missing_vars:
            print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
            print("   Set these in .env file or as OS environment variables")
            return False

        print("✅ Environment configuration valid")
        return True

    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return False

def show_help():
    """Show help information."""
    print("🤖 Zoom-Telebot SOC Development Commands")
    print("=" * 50)
    print()
    print("USAGE:")
    print("  python dev.py <command>")
    print()
    print("COMMANDS:")
    print("  setup    - Setup environment (validation + initialization)")
    print("  run      - Run bot with normal logging")
    print("  debug    - Run bot with debug logging")
    print("  test     - Test Python imports")
    print("  check    - Check environment configuration")
    print("  help     - Show this help")
    print()
    print("EXAMPLES:")
    print("  python dev.py setup    # Setup environment first")
    print("  python dev.py run      # Run bot (auto-setup)")
    print("  python dev.py debug    # Run with debug logs")
    print("  python dev.py test     # Test imports only")
    print()
    print("For auto-restart on file changes, use:")
    print("  python dev_run.py")

def main():
    if len(sys.argv) < 2:
        show_help()
        return 1

    action = sys.argv[1]

    print("🤖 Zoom-Telebot SOC Development Runner")
    print("=" * 50)

    # Check environment first
    if not check_env():
        return 1

    if action == 'help' or action == '--help' or action == '-h':
        show_help()
        return 0

    if action == 'setup':
        return 0 if setup_environment() else 1

    elif action == 'run':
        if not setup_environment():
            print("❌ Setup failed.")
            return 1
        return 0 if run_bot() else 1

    elif action == 'debug':
        if not setup_environment():
            print("❌ Setup failed.")
            return 1
        return 0 if run_bot_debug() else 1

    elif action == 'test':
        return 0 if test_imports() else 1

    elif action == 'check':
        return 0 if check_env() else 1

    else:
        print(f"❌ Unknown command: {action}")
        print("Run 'python dev.py help' for available commands")
        return 1

if __name__ == "__main__":
    sys.exit(main())