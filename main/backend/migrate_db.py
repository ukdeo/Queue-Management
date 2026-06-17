import sqlite3
import os

db_path = 'palo.db'

def migrate():
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check for priority_level in tokens
    cursor.execute("PRAGMA table_info(tokens)")
    columns = [c[1] for c in cursor.fetchall()]
    
    if 'priority_level' not in columns:
        print("Adding priority_level column to tokens table...")
        cursor.execute("ALTER TABLE tokens ADD COLUMN priority_level INTEGER DEFAULT 0")
    else:
        print("priority_level column already exists.")

    conn.commit()
    conn.close()
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
