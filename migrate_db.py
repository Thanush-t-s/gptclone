"""
Database migration script to add email, google_id, and security fields to users table.
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "instance", "chat.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get existing columns
cols = [c[1] for c in cursor.execute("PRAGMA table_info(users)").fetchall()]

new_cols = [
    ("email", "TEXT"),
    ("full_name", "TEXT"),
    ("avatar_url", "TEXT"),
    ("auth_provider", "TEXT DEFAULT 'local'"),
    ("google_id", "TEXT"),
    ("failed_login_attempts", "INTEGER DEFAULT 0"),
    ("locked_until", "DATETIME")
]

for col_name, col_type in new_cols:
    if col_name not in cols:
        cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        print(f"Added column: {col_name}")

# Backfill emails for existing users
rows = cursor.execute("SELECT id, username, email FROM users").fetchall()
for user_id, username, email in rows:
    if not email:
        safe_email = f"{username.lower()}@example.com"
        cursor.execute("UPDATE users SET email = ? WHERE id = ?", (safe_email, user_id))
        print(f"Set email for user {username} -> {safe_email}")

conn.commit()
print("Migration completed successfully!")
conn.close()
