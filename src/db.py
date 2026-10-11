"""SQLite state store for the queue worker.

WAL mode is used so readers (e.g. a status CLI or the maintenance check)
never block on a writer, and so a crash mid-write leaves the previous
committed state intact (the WAL file replays or is discarded on next open,
it never corrupts the main db file in place).
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS commands (
    id            TEXT PRIMARY KEY,
    payload       TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('in_progress', 'done', 'failed')),
    started_at    REAL NOT NULL,
    finished_at   REAL,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE;")
    try:
        yield conn
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise


def start_command(conn: sqlite3.Connection, cmd_id: str, payload: str) -> None:
    with transaction(conn):
        conn.execute(
            "INSERT INTO commands (id, payload, status, started_at) VALUES (?, ?, 'in_progress', ?)",
            (cmd_id, payload, time.time()),
        )


def finish_command(conn: sqlite3.Connection, cmd_id: str, ok: bool, error: str | None = None) -> None:
    with transaction(conn):
        conn.execute(
            "UPDATE commands SET status = ?, finished_at = ?, error = ? WHERE id = ?",
            ("done" if ok else "failed", time.time(), error, cmd_id),
        )


def stuck_commands(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Commands left in_progress — almost always a crash mid-dispatch."""
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM commands WHERE status = 'in_progress'")
    return cur.fetchall()


def integrity_check(conn: sqlite3.Connection) -> str:
    return conn.execute("PRAGMA integrity_check;").fetchone()[0]


def checkpoint(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
