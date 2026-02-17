#!/usr/bin/env python3
"""
Zoom-Telebot Main Entry Point

This script serves as the main entry point for the Zoom Telegram Bot.
It imports and runs the bot from the bot package.
"""

import sys
import argparse
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def create_parser():
    """Create argument parser for the bot."""
    parser = argparse.ArgumentParser(
        description="Zoom-Telebot SOC - Telegram Bot for Zoom Meeting Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                    # Run the bot normally
  python run.py --help            # Show this help message
  python run.py --version         # Show version information
  python run.py --check-config    # Check configuration without running bot

Environment Variables Required:
  TELEGRAM_TOKEN     - Bot token from @BotFather
  INITIAL_OWNER_ID   - Your Telegram user ID
  ZOOM_ACCOUNT_ID    - Zoom account ID
  ZOOM_CLIENT_ID     - Zoom OAuth client ID
  ZOOM_CLIENT_SECRET - Zoom OAuth client secret

Optional:
  SID_ID, SID_KEY    - S.id shortener credentials
  BITLY_TOKEN        - Bitly access token
  LOG_LEVEL          - Logging level (DEBUG, INFO, WARNING, ERROR)
        """
    )

    parser.add_argument(
        '--version', '-v',
        action='version',
        version='Zoom-Telebot SOC v2026.02.17'
    )

    parser.add_argument(
        '--check-config',
        action='store_true',
        help='Check configuration and exit without running the bot'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Override log level (default: from environment or INFO)'
    )

    return parser

def check_configuration():
    """Check if required environment variables are set."""
    import os
    try:
        from config import Settings
    except ImportError:
        print("❌ Cannot import configuration module.")
        print("   Make sure you're running from the project root directory.")
        print("   Current directory:", os.getcwd())
        return False

    print("🔍 Checking configuration...")

    try:
        settings = Settings()
        print("✅ Configuration loaded successfully!")

        # Check required settings
        required = [
            ('TELEGRAM_TOKEN', settings.bot_token),
            ('INITIAL_OWNER_ID', settings.owner_id),
            ('ZOOM_ACCOUNT_ID', settings.zoom_account_id),
            ('ZOOM_CLIENT_ID', settings.zoom_client_id),
            ('ZOOM_CLIENT_SECRET', settings.zoom_client_secret),
        ]

        print("\n📋 Required Settings:")
        for name, value in required:
            status = "✅ Set" if value else "❌ Missing"
            print(f"  {name}: {status}")

        # Check optional settings
        optional = [
            ('SID_ID', getattr(settings, 'sid_id', None)),
            ('SID_KEY', getattr(settings, 'sid_key', None)),
            ('BITLY_TOKEN', getattr(settings, 'bitly_token', None)),
        ]

        print("\n📋 Optional Settings:")
        for name, value in optional:
            status = "✅ Set" if value else "⚠️  Not set"
            print(f"  {name}: {status}")

        print(f"\n📊 Database: {settings.database_url}")
        print(f"📊 Log Level: {getattr(settings, 'log_level', 'INFO')}")

        # Check if all required are set
        all_required = all(value for _, value in required)
        if all_required:
            print("\n🎉 All required configuration is set! Bot is ready to run.")
            return True
        else:
            print("\n❌ Some required configuration is missing. Please check your .env file.")
            print("   See docs/INSTALLATION.md for setup instructions.")
            return False

    except Exception as e:
        print(f"❌ Configuration error: {e}")
        print("   Please check your .env file and try again.")
        return False

def main():
    """Main entry point with argument parsing."""
    import signal
    
    parser = create_parser()
    args = parser.parse_args()

    # Handle check-config
    if args.check_config:
        success = check_configuration()
        sys.exit(0 if success else 1)

    # Handle log-level override
    if args.log_level:
        import os
        os.environ['LOG_LEVEL'] = args.log_level

    # Initialize logging
    from bot.logger import setup_logging
    setup_logging()

    # Import and run the bot
    from bot.main import main as bot_main
    import asyncio

    try:
        asyncio.run(bot_main())
    except KeyboardInterrupt:
        # Silent exit on Ctrl+C - bot/main.py already handles the message
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error sistem: {e}")
        print("🔍 Periksa log file untuk detail lebih lanjut")
        sys.exit(1)

if __name__ == '__main__':
    main()