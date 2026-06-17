"""
Migration script: adds missing columns to the 'queues' table if they don't exist.
Safe to re-run — checks before adding.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "palo.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get existing columns
    c.execute("PRAGMA table_info(queues)")
    existing_cols = {row[1] for row in c.fetchall()}
    print(f"Existing queues columns: {existing_cols}")

    migrations = [
        ("active", "INTEGER NOT NULL DEFAULT 1"),
        ("is_accepting_tokens", "INTEGER NOT NULL DEFAULT 1"),
    ]

    for col_name, col_def in migrations:
        if col_name not in existing_cols:
            print(f"  Adding column: {col_name}")
            c.execute(f"ALTER TABLE queues ADD COLUMN {col_name} {col_def}")
        else:
            print(f"  Column already exists: {col_name}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
