"""Migration helper: convert legacy status 'approve' to 'whitelisted'.

Usage:
  python migrate_statuses.py

This script updates the database configured in `config.settings.db_path`.
It prints how many rows were updated.
"""
import sqlite3
from config import settings


def main():
    db = settings.db_path
    print("Using DB:", db)
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE status = 'approve'")
    before = cur.fetchone()[0]
    print(f"Found {before} users with status 'approve'")
    if before == 0:
        print("Nothing to do.")
        conn.close()
        return
    cur.execute("UPDATE users SET status = 'whitelisted' WHERE status = 'approve'")
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM users WHERE status = 'whitelisted'")
    after_whitelisted = cur.fetchone()[0]
    print(f"Now total whitelisted users: {after_whitelisted}")
    conn.close()

if __name__ == '__main__':
    main()
