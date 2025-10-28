#!/usr/bin/env python3
"""
Script to verify dummy users were added correctly
"""

import asyncio
from db import list_pending_users, list_all_users, init_db

async def check_users():
    await init_db()

    pending = await list_pending_users()
    all_users = await list_all_users()

    print(f'Total users in database: {len(all_users)}')
    print(f'Pending users: {len(pending)}')
    print(f'Whitelisted users: {len([u for u in all_users if u["status"] == "whitelisted"])}')

    print('\nFirst 5 pending users:')
    for user in pending[:5]:
        print(f'  @{user["username"]} (ID: {user["telegram_id"]}) - {user["status"]}, {user["role"]}')

    print('\nFirst 5 whitelisted users:')
    whitelisted = [u for u in all_users if u['status'] == 'whitelisted'][:5]
    for user in whitelisted:
        print(f'  @{user["username"]} (ID: {user["telegram_id"]}) - {user["status"]}, {user["role"]}')

if __name__ == "__main__":
    asyncio.run(check_users())