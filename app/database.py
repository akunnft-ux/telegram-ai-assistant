import sqlite3

DB_NAME = "assistant.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


def save_message(user_id, role, message):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO conversations (user_id, role, message)
    VALUES (?, ?, ?)
    """, (str(user_id), role, message))

    conn.commit()
    conn.close()

def get_recent_messages(user_id, limit=10):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT role, message
    FROM conversations
    WHERE user_id = ?
    ORDER BY id DESC
    LIMIT ?
    """, (str(user_id), limit))

    rows = cursor.fetchall()
    conn.close()

    rows.reverse()  # biar urutan lama -> baru
    return rows
