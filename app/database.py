import sqlite3

DB_NAME = "/data/assistant.db"


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


    cursor.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, key)
    )
    """)

    conn.commit()
    conn.close()
    print("✅ DB initialized, tabel memories siap")


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

def upsert_memory(user_id, key, value):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO memories (user_id, key, value)
    VALUES (?, ?, ?)
    ON CONFLICT(user_id, key)
    DO UPDATE SET value = excluded.value,
                  updated_at = CURRENT_TIMESTAMP
    """, (str(user_id), key, value))

    conn.commit()
    conn.close()


# BARU: ambil semua memory milik user
def get_all_memories(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT key, value
    FROM memories
    WHERE user_id = ?
    ORDER BY updated_at DESC
    """, (str(user_id),))

    rows = cursor.fetchall()
    conn.close()

    return rows
