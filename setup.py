#!/usr/bin/env python3
"""
Zoom-Telebot SOC Initial Setup Script
Handles complete bot initialization including:
- Environment variable validation
- Database initialization
- Owner user setup
- Shortener configuration
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from db import init_db, add_pending_user, update_user_status, get_user_by_telegram_id
import shortener

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BotSetup:
    """Handles complete bot setup and initialization."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def log_error(self, message: str):
        """Log an error message."""
        self.errors.append(message)
        logger.error(message)

    def log_warning(self, message: str):
        """Log a warning message."""
        self.warnings.append(message)
        logger.warning(message)

    def validate_environment_variables(self) -> bool:
        """Validate all required environment variables."""
        logger.info("🔍 Validating environment variables...")

        # Required environment variables with descriptions
        required_vars = {
            'TELEGRAM_TOKEN': 'Telegram bot token from @BotFather',
            'INITIAL_OWNER_ID': 'Telegram user ID of the bot owner',
            'ZOOM_CLIENT_ID': 'Zoom OAuth client ID',
            'ZOOM_CLIENT_SECRET': 'Zoom OAuth client secret',
            'DATABASE_URL': 'Database connection URL'
        }

        missing_vars = []
        for var, description in required_vars.items():
            if not os.getenv(var):
                missing_vars.append(f"{var} ({description})")

        if missing_vars:
            self.log_error("Missing required environment variables:")
            for var in missing_vars:
                logger.error(f"  - {var}")
            return False

        # Validate Telegram token format
        token = os.getenv('TELEGRAM_TOKEN')
        if token and ':' not in token:
            self.log_error("TELEGRAM_TOKEN format appears invalid (should contain ':')")
            return False

        # Optional warnings for recommended variables
        optional_vars = {
            'ZOOM_ACCOUNT_ID': 'Zoom account ID for better integration',
            'INITIAL_OWNER_USERNAME': 'Owner username for better UX',
            'SID_ID': 'S.id service credentials',
            'SID_KEY': 'S.id service credentials',
            'BITLY_TOKEN': 'Bitly service credentials'
        }

        for var, description in optional_vars.items():
            if not os.getenv(var):
                self.log_warning(f"Optional variable {var} not set: {description}")

        logger.info("✅ Environment variables validation passed")
        return True

    def validate_shortener_config(self) -> bool:
        """Validate shortener configuration file."""
        logger.info("🔍 Validating shortener configuration...")

        # Check if shorteners.json exists
        shorteners_path = Path(__file__).parent / "shorteners.json"
        data_shorteners_path = Path(__file__).parent / "data" / "shorteners.json"

        if data_shorteners_path.exists():
            shorteners_path = data_shorteners_path
            logger.info("Using shorteners.json from data directory")
        elif not shorteners_path.exists():
            self.log_error("shorteners.json file not found")
            return False

        try:
            with open(shorteners_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if 'providers' not in config:
                self.log_error("shorteners.json missing 'providers' key")
                return False

            providers = config['providers']
            enabled_providers = [k for k, v in providers.items() if v.get('enabled', False)]

            if not enabled_providers:
                self.log_warning("No shortener providers are enabled in shorteners.json")
            else:
                logger.info(f"✅ Found {len(enabled_providers)} enabled shortener provider(s): {', '.join(enabled_providers)}")

        except json.JSONDecodeError as e:
            self.log_error(f"Invalid JSON in shorteners.json: {e}")
            return False
        except Exception as e:
            self.log_error(f"Error reading shorteners.json: {e}")
            return False

        return True

    async def initialize_database(self) -> bool:
        """Initialize database schema."""
        logger.info("🗄️  Initializing database...")

        try:
            await init_db()
            logger.info("✅ Database schema initialized successfully")
            return True
        except Exception as e:
            self.log_error(f"Failed to initialize database: {e}")
            return False

    async def setup_owner_user(self) -> bool:
        """Setup the bot owner user."""
        logger.info("👤 Setting up owner user...")

        owner_id = os.getenv('INITIAL_OWNER_ID')
        owner_username = os.getenv('INITIAL_OWNER_USERNAME', f"user_{owner_id}")

        if not owner_id:
            self.log_error("INITIAL_OWNER_ID not set")
            return False

        try:
            # Check if owner already exists
            existing_owner = await get_user_by_telegram_id(int(owner_id))

            if existing_owner:
                logger.info(f"✅ Owner user already exists: {existing_owner}")
                # Ensure owner has correct role and status
                if existing_owner['role'] != 'owner' or existing_owner['status'] != 'whitelisted':
                    await update_user_status(int(owner_id), 'whitelisted', 'owner')
                    logger.info("✅ Owner user updated with correct role and status")
            else:
                # Add owner as pending first, then approve
                await add_pending_user(int(owner_id), owner_username)
                await update_user_status(int(owner_id), 'whitelisted', 'owner')
                logger.info(f"✅ Owner user initialized: ID={owner_id}, Username={owner_username}")

            return True

        except Exception as e:
            self.log_error(f"Failed to setup owner user: {e}")
            return False

    async def configure_shorteners(self) -> bool:
        """Configure shortener services with credentials from environment."""
        logger.info("🔗 Configuring shortener services...")

        # Check for shorteners.json
        shorteners_path = Path(__file__).parent / "shorteners.json"
        data_shorteners_path = Path(__file__).parent / "data" / "shorteners.json"

        if data_shorteners_path.exists():
            shorteners_path = data_shorteners_path
        elif not shorteners_path.exists():
            self.log_error("shorteners.json not found")
            return False

        try:
            with open(shorteners_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            updated = False

            # Configure S.id credentials
            if 'sid' in config['providers']:
                sid_config = config['providers']['sid']
                sid_id = os.getenv('SID_ID')
                sid_key = os.getenv('SID_KEY')

                if sid_id and sid_key:
                    if 'auth' not in sid_config:
                        sid_config['auth'] = {'type': 'header', 'headers': {}}

                    sid_config['auth']['headers']['X-Auth-Id'] = sid_id
                    sid_config['auth']['headers']['X-Auth-Key'] = sid_key
                    updated = True
                    logger.info("✅ S.id credentials configured from environment")
                else:
                    self.log_warning("S.id credentials (SID_ID, SID_KEY) not found in environment")

            # Configure Bitly credentials
            if 'bitly' in config['providers']:
                bitly_config = config['providers']['bitly']
                bitly_token = os.getenv('BITLY_TOKEN')

                if bitly_token:
                    if 'headers' not in bitly_config:
                        bitly_config['headers'] = {}
                    bitly_config['headers']['Authorization'] = f'Bearer {bitly_token}'
                    updated = True
                    logger.info("✅ Bitly credentials configured from environment")
                else:
                    self.log_warning("Bitly token (BITLY_TOKEN) not found in environment")

            # Save updated configuration
            if updated:
                try:
                    with open(shorteners_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=2, ensure_ascii=False)
                    logger.info("✅ Shortener configuration updated and saved")
                except PermissionError:
                    # If we can't write to the original file, try to copy it to data directory
                    data_shorteners_path = Path(__file__).parent / "data" / "shorteners.json"
                    try:
                        data_shorteners_path.parent.mkdir(exist_ok=True)
                        with open(data_shorteners_path, 'w', encoding='utf-8') as f:
                            json.dump(config, f, indent=2, ensure_ascii=False)
                        logger.info("✅ Shortener configuration copied to data directory")
                    except Exception as copy_error:
                        self.log_error(f"Failed to save shortener configuration: {copy_error}")
                        return False
            else:
                logger.info("ℹ️  No shortener credentials to update")

            return True

        except Exception as e:
            self.log_error(f"Failed to configure shorteners: {e}")
            return False

    def print_configuration_summary(self):
        """Print current configuration summary."""
        print("\n" + "="*70)
        print("📋 BOT CONFIGURATION SUMMARY")
        print("="*70)

        # Environment variables
        print("\n🔧 Environment Variables:")
        env_vars = [
            ('TELEGRAM_TOKEN', 'Telegram Bot Token'),
            ('INITIAL_OWNER_ID', 'Owner User ID'),
            ('INITIAL_OWNER_USERNAME', 'Owner Username'),
            ('ZOOM_CLIENT_ID', 'Zoom Client ID'),
            ('ZOOM_CLIENT_SECRET', 'Zoom Client Secret'),
            ('ZOOM_ACCOUNT_ID', 'Zoom Account ID'),
            ('DATABASE_URL', 'Database URL'),
            ('DEFAULT_MODE', 'Bot Mode'),
            ('LOG_LEVEL', 'Log Level'),
        ]

        for var, desc in env_vars:
            value = os.getenv(var, 'Not set')
            if var in ['TELEGRAM_TOKEN', 'ZOOM_CLIENT_SECRET', 'SID_KEY', 'BITLY_TOKEN']:
                # Mask sensitive values
                if value != 'Not set' and len(value) > 10:
                    value = value[:6] + '...' + value[-4:]
            status = "✅" if value != 'Not set' else "❌"
            print(f"  {status} {var}: {value} ({desc})")

        # Database info
        db_url = os.getenv('DATABASE_URL', '')
        if 'sqlite' in db_url:
            db_path = db_url.replace('sqlite+aiosqlite:///', '')
            print(f"\n🗄️  Database: SQLite at {db_path}")
        else:
            print(f"\n🗄️  Database: {db_url}")

        print("\n" + "="*70)

    async def run_initial_setup(self) -> bool:
        """Run complete initial setup process."""
        print("🤖 Zoom-Telebot SOC Initial Setup")
        print("="*50)
        print("This script will initialize your bot with the following steps:")
        print("1. Validate environment variables")
        print("2. Validate shortener configuration")
        print("3. Initialize database")
        print("4. Setup owner user")
        print("5. Configure shortener services")
        print()

        # Step 1: Validate environment variables
        logger.info("Step 1: Validating environment variables...")
        if not self.validate_environment_variables():
            return False

        # Step 2: Validate shortener config
        logger.info("Step 2: Validating shortener configuration...")
        if not self.validate_shortener_config():
            return False

        # Step 3: Initialize database
        logger.info("Step 3: Initializing database...")
        if not await self.initialize_database():
            return False

        # Step 4: Setup owner user
        logger.info("Step 4: Setting up owner user...")
        if not await self.setup_owner_user():
            return False

        # Step 5: Configure shorteners
        logger.info("Step 5: Configuring shortener services...")
        if not await self.configure_shorteners():
            return False

        logger.info("✅ Initial setup completed successfully!")
        return True

    def print_setup_summary(self):
        """Print setup completion summary."""
        print("\n" + "="*60)
        print("🎉 SETUP COMPLETION SUMMARY")
        print("="*60)

        if not self.errors and not self.warnings:
            print("✅ Setup completed successfully with no errors or warnings!")
        else:
            if self.errors:
                print(f"❌ {len(self.errors)} error(s) found:")
                for error in self.errors:
                    print(f"   • {error}")

            if self.warnings:
                print(f"⚠️  {len(self.warnings)} warning(s):")
                for warning in self.warnings:
                    print(f"   • {warning}")

        print("\n" + "="*60)


def print_environment_template():
    """Print environment variables template."""
    print("� Environment Variables Template:")
    print("="*50)
    print("""
# ================================
# Database & Default Mode Configuration
DATABASE_URL=sqlite+aiosqlite:///./zoom_telebot.db
DEFAULT_MODE=polling

# ========================================
# Combined SOC Telegram Bot Configuration
# ========================================

# Telegram Bot Configuration
TELEGRAM_TOKEN=your-telegram-bot-token-here
INITIAL_OWNER_ID=your-telegram-user-id-here
INITIAL_OWNER_USERNAME=@your-telegram-username

# Zoom Integration Configuration (Server-to-Server OAuth)
ZOOM_ACCOUNT_ID=your-zoom-account-id
ZOOM_CLIENT_ID=your-zoom-client-id
ZOOM_CLIENT_SECRET=your-zoom-client-secret

# Short URL Service Configuration
# S.id Configuration (recommended for Indonesian users)
SID_ID=your-sid-id-here
SID_KEY=your-sid-key-here

# Bitly Configuration (optional)
BITLY_TOKEN=your-bitly-token-here

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s

# ========================================
# Shortener Configuration
# ========================================
# Shortener providers are configured in shorteners.json file
# To add new providers, edit shorteners.json (no code changes needed!)
#
# Example new provider format in shorteners.json:
# "newprovider": {
#   "name": "New Provider",
#   "description": "Description of the provider",
#   "enabled": true,
#   "api_url": "https://api.example.com/shorten",
#   "method": "post",
#   "headers": {"Content-Type": "application/json"},
#   "body": {"url": "{url}"},
#   "response_type": "json",
#   "success_check": "status==200",
#   "url_extract": "response.get('short_url')"
# }
""")


async def main():
    """Main setup function."""
    if len(sys.argv) > 1 and sys.argv[1] == '--template':
        print_environment_template()
        return 0

    setup = BotSetup()

    try:
        # Print configuration summary first
        setup.print_configuration_summary()

        # Run initial setup
        success = await setup.run_initial_setup()
        setup.print_setup_summary()

        if success:
            print("\n🎉 Bot setup completed successfully!")
            print("\n🚀 You can now run the bot with:")
            print("   python main.py                    # Production mode")
            print("   python dev.py run                # Development mode")
            print("   docker compose up               # Docker mode")
            print("\n📖 For more information, see README.md")
            return 0
        else:
            print("\n❌ Setup failed. Please fix the issues above and run again.")
            print("💡 Tip: Run 'python setup.py --template' to see environment variables template")
            return 1

    except KeyboardInterrupt:
        print("\n⚠️  Setup interrupted by user")
        return 1
    except Exception as e:
        logger.exception("Unexpected error during setup")
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


