import sqlite3
from gmail_cleaner.config import DB_FILE


def init_db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    conn.execute("""
    CREATE TABLE IF NOT EXISTS gmail_messages (
        id TEXT PRIMARY KEY,
        thread_id TEXT,
        history_id INTEGER,
        internal_date INTEGER,
        label_ids TEXT,
        subject TEXT,
        sender TEXT,
        recipients TEXT,
        snippet TEXT,
        body_text TEXT,
        raw_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS sync_state (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_internal_date
    ON gmail_messages(internal_date)
    """)

    # From analyze.py
    try:
        conn.execute("""
        ALTER TABLE gmail_messages
        ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0
        """)
    except sqlite3.OperationalError:
        pass

    conn.commit()
    return conn


def get_state(conn, key):
    row = conn.execute(
        "SELECT value FROM sync_state WHERE key=?",
        (key,)
    ).fetchone()
    return row[0] if row else None


def set_state(conn, key, value):
    conn.execute(
        """
        INSERT OR REPLACE INTO sync_state(key,value)
        VALUES (?,?)
        """,
        (key, str(value))
    )
