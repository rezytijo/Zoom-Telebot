#!/usr/bin/env python3
"""
Setup script for Zoom-Telebot SOC
Handles initial environment setup including:
- Database initialization
- Owner user setup
- Shortener configuration validation
- Environment validation
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

logger = logging.getLogger(__name__)


class EnvironmentSetup:
    """Handles environment setup and validation for the bot."""

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

    def validate_telegram_config(self) -> bool:
        """Validate Telegram bot configuration."""
        logger.info("Validating Telegram configuration...")

        if not settings.bot_token:
            self.log_error("TELEGRAM_TOKEN is required but not set")
            return False

        if not settings.owner_id:
            self.log_error("INITIAL_OWNER_ID is required but not set")
            return False

        # Validate token format (basic check)
        if not settings.bot_token or ':' not in settings.bot_token:
            self.log_error("TELEGRAM_TOKEN format appears invalid")
            return False

        logger.info("✅ Telegram configuration valid")
        return True

    def validate_zoom_config(self) -> bool:
        """Validate Zoom integration configuration."""
        logger.info("Validating Zoom configuration...")

        if not settings.zoom_client_id:
            self.log_error("ZOOM_CLIENT_ID is required but not set")
            return False

        if not settings.zoom_client_secret:
            self.log_error("ZOOM_CLIENT_SECRET is required but not set")
            return False

        if not settings.zoom_account_id:
            self.log_warning("ZOOM_ACCOUNT_ID not set - some features may not work")

        logger.info("✅ Zoom configuration valid")
        return True

    def validate_shortener_config(self) -> bool:
        """Validate shortener configuration."""
        logger.info("Validating shortener configuration...")

        # Check if shorteners.json exists (prefer data directory version)
        data_shorteners_path = Path(__file__).parent / "data" / "shorteners.json"
        shorteners_path = Path(__file__).parent / "shorteners.json"
        
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

    def validate_database_config(self) -> bool:
        """Validate database configuration."""
        logger.info("Validating database configuration...")

        if not settings.database_url:
            self.log_error("DATABASE_URL is required but not set")
            return False

        # Check if database file exists or can be created
        db_path = Path(settings.db_path)
        db_dir = db_path.parent

        try:
            db_dir.mkdir(parents=True, exist_ok=True)
            # Try to create/touch the database file
            db_path.touch(exist_ok=True)
            logger.info(f"✅ Database path valid: {db_path.absolute()}")
        except Exception as e:
            self.log_error(f"Cannot create database file at {db_path}: {e}")
            return False

        return True

    async def initialize_owner(self) -> bool:
        """Initialize owner user in database."""
        logger.info("Initializing owner user...")

        if not settings.owner_id:
            self.log_error("Cannot initialize owner: INITIAL_OWNER_ID not set")
            return False

        try:
            # Check if owner already exists
            existing_owner = await get_user_by_telegram_id(settings.owner_id)

            if existing_owner:
                logger.info(f"✅ Owner user already exists: {existing_owner}")
                # Ensure owner has correct role and status
                if existing_owner['role'] != 'owner' or existing_owner['status'] != 'whitelisted':
                    await update_user_status(settings.owner_id, 'whitelisted', 'owner')
                    logger.info("✅ Owner user updated with correct role and status")
            else:
                # Add owner as pending first, then approve
                await add_pending_user(settings.owner_id, settings.owner_username)
                await update_user_status(settings.owner_id, 'whitelisted', 'owner')
                logger.info(f"✅ Owner user initialized: ID={settings.owner_id}, Username={settings.owner_username}")

            return True

        except Exception as e:
            self.log_error(f"Failed to initialize owner: {e}")
            return False

    async def initialize_database(self) -> bool:
        """Initialize database schema."""
        logger.info("Initializing database schema...")

        try:
            await init_db()
            logger.info("✅ Database schema initialized")
            return True
        except Exception as e:
            self.log_error(f"Failed to initialize database: {e}")
            return False

    def validate_environment(self) -> bool:
        """Validate entire environment configuration."""
        logger.info("🔍 Starting environment validation...")

        validations = [
            self.validate_telegram_config,
            self.validate_zoom_config,
            self.validate_shortener_config,
            self.validate_database_config,
        ]

        all_passed = True
        for validation in validations:
            if not validation():
                all_passed = False

        if all_passed:
            logger.info("✅ All environment validations passed")
        else:
            logger.error("❌ Some environment validations failed")

        return all_passed

    async def setup_environment(self) -> bool:
        """Complete environment setup."""
        logger.info("🚀 Starting environment setup...")

        # Validate environment first
        if not self.validate_environment():
            logger.error("❌ Environment validation failed. Please fix the issues above.")
            return False

        # Initialize database
        if not await self.initialize_database():
            return False

        # Initialize owner
        if not await self.initialize_owner():
            return False

        # Setup shortener credentials
        if not await self.setup_shortener_credentials():
            return False

        logger.info("✅ Environment setup completed successfully!")
        return True

    def print_summary(self):
        """Print setup summary."""
        print("\n" + "="*60)
        print("📋 ENVIRONMENT SETUP SUMMARY")
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

    async def setup_shortener_credentials(self) -> bool:
        """Setup shortener credentials from environment variables."""
        logger.info("Setting up shortener credentials...")

        # Check for shorteners.json (prefer data directory version)
        data_shorteners_path = Path(__file__).parent / "data" / "shorteners.json"
        shorteners_path = Path(__file__).parent / "shorteners.json"
        
        if data_shorteners_path.exists():
            shorteners_path = data_shorteners_path
        elif not shorteners_path.exists():
            self.log_error("shorteners.json not found")
            return False

        try:
            with open(shorteners_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            updated = False

            # Update S.id credentials
            if 'sid' in config['providers']:
                sid_config = config['providers']['sid']
                if settings.sid_id and settings.sid_key:
                    if 'auth' not in sid_config:
                        sid_config['auth'] = {'type': 'header', 'headers': {}}

                    sid_config['auth']['headers']['X-Auth-Id'] = settings.sid_id
                    sid_config['auth']['headers']['X-Auth-Key'] = settings.sid_key
                    updated = True
                    logger.info("✅ S.id credentials updated from environment")
                else:
                    self.log_warning("S.id credentials not found in environment variables")

            # Update Bitly credentials if needed
            if 'bitly' in config['providers']:
                bitly_config = config['providers']['bitly']
                if settings.bitly_token:
                    # Bitly typically uses Bearer token in Authorization header
                    if 'headers' not in bitly_config:
                        bitly_config['headers'] = {}
                    bitly_config['headers']['Authorization'] = f'Bearer {settings.bitly_token}'
                    updated = True
                    logger.info("✅ Bitly credentials updated from environment")

            if updated:
                try:
                    with open(shorteners_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=2, ensure_ascii=False)
                    logger.info("✅ shorteners.json updated with credentials")
                except PermissionError:
                    # If we can't write to the original file, try to copy it to data directory
                    data_shorteners_path = Path(__file__).parent / "data" / "shorteners.json"
                    try:
                        data_shorteners_path.parent.mkdir(exist_ok=True)
                        with open(data_shorteners_path, 'w', encoding='utf-8') as f:
                            json.dump(config, f, indent=2, ensure_ascii=False)
                        logger.info("✅ shorteners.json copied to data directory with updated credentials")
                    except Exception as copy_error:
                        self.log_error(f"Failed to copy shorteners.json to data directory: {copy_error}")
                        return False

            return True

        except Exception as e:
            self.log_error(f"Failed to setup shortener credentials: {e}")
            return False
        """Print setup summary."""
        print("\n" + "="*60)
        print("📋 ENVIRONMENT SETUP SUMMARY")
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


async def main():
    """Main setup function."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🤖 Zoom-Telebot SOC Environment Setup")
    print("="*50)

    setup = EnvironmentSetup()

    try:
        success = await setup.setup_environment()
        setup.print_summary()

        if success:
            print("\n🎉 Bot is ready to run!")
            print("   Run: python main.py")
            return 0
        else:
            print("\n❌ Setup failed. Please fix the issues above.")
            return 1

    except KeyboardInterrupt:
        print("\n⚠️  Setup interrupted by user")
        return 1
    except Exception as e:
        logger.exception("Unexpected error during setup")
        print(f"\n❌ Unexpected error: {e}")
        return 1


def check_env_file():
    """Check if environment variables are configured (either from .env or OS)."""
    import os
    from pathlib import Path

    env_path = Path(".env")
    env_example_path = Path(".env.example")

    # Required environment variables
    required_vars = [
        'TELEGRAM_TOKEN',
        'INITIAL_OWNER_ID',
        'ZOOM_CLIENT_ID',
        'ZOOM_CLIENT_SECRET',
        'DATABASE_URL'
    ]

    # Check if all required variables are set
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if not missing_vars:
        print("✅ All required environment variables are set")
        return True

    # If some variables are missing, check if .env file exists
    if env_path.exists():
        print("⚠️  Some required environment variables are missing")
        print("   Please check your .env file and ensure all required variables are set:")
        for var in missing_vars:
            print(f"   - {var}")
        print()
        return False

    # If no .env file and variables missing, guide user
    print("⚠️  .env file not found and some required environment variables are missing!")
    print("   You can either:")
    print("   1. Create .env file: cp .env.example .env (then edit it)")
    print("   2. Set environment variables directly in your OS/shell")
    print()
    print("   Required variables that are missing:")
    for var in missing_vars:
        print(f"   - {var}")
    print()
    return False


if __name__ == "__main__":
    # Check if .env exists
    if not check_env_file():
        sys.exit(1)

    # Run setup
    exit_code = asyncio.run(main())
    sys.exit(exit_code)