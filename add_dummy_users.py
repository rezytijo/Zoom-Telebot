#!/usr/bin/env python3
"""
Script to add 30 dummy Telegram users to the database.
- 15 users with status 'pending' and role 'user'
- 15 users with status 'whitelisted' and role 'user'
"""

import asyncio
import random
import string
from db import add_pending_user, update_user_status, init_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_random_username(length=8):
    """Generate a random username."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_telegram_id():
    """Generate a random Telegram ID (between 100000000 and 999999999)."""
    return random.randint(100000000, 999999999)


async def add_dummy_users():
    """Add 30 dummy users to the database."""
    logger.info("Initializing database...")
    await init_db()

    logger.info("Adding 30 dummy users...")

    # Add 15 pending users
    pending_users = []
    for i in range(15):
        telegram_id = generate_telegram_id()
        username = f"pending_user_{i+1}"
        await add_pending_user(telegram_id, username)
        # Update role to 'user' (default is 'guest')
        await update_user_status(telegram_id, 'pending', 'user')
        pending_users.append((telegram_id, username))
        logger.info(f"Added pending user: {username} (ID: {telegram_id})")

    # Add 15 whitelisted users
    whitelisted_users = []
    for i in range(15):
        telegram_id = generate_telegram_id()
        username = f"user_{i+1}"
        # First add as pending
        await add_pending_user(telegram_id, username)
        # Then update to whitelisted and role 'user'
        await update_user_status(telegram_id, 'whitelisted', 'user')
        whitelisted_users.append((telegram_id, username))
        logger.info(f"Added whitelisted user: {username} (ID: {telegram_id})")

    logger.info("Successfully added 30 dummy users!")
    logger.info(f"Pending users: {len(pending_users)}")
    logger.info(f"Whitelisted users: {len(whitelisted_users)}")

    # Print summary
    print("\n=== DUMMY USERS ADDED SUCCESSFULLY ===")
    print(f"Total users added: {len(pending_users) + len(whitelisted_users)}")
    print(f"Pending users: {len(pending_users)}")
    print(f"Whitelisted users: {len(whitelisted_users)}")

    print("\n--- Pending Users ---")
    for tid, uname in pending_users:
        print(f"@{uname} (ID: {tid}) - Status: pending, Role: user")

    print("\n--- Whitelisted Users ---")
    for tid, uname in whitelisted_users:
        print(f"@{uname} (ID: {tid}) - Status: whitelisted, Role: user")


if __name__ == "__main__":
    asyncio.run(add_dummy_users())