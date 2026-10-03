"""SQLite storage for accounts and login sessions.

Rooms and games still live in memory (see room_manager.py); only data that
must survive a restart goes here. Queries are tiny, so each call simply opens
its own connection: that keeps it safe from FastAPI's threadpool without any
locking of our own.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(os.environ.get("BRIDGE_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "bridge.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    INTEGER NOT NULL,
    -- bumped on every avatar change; part of the avatar URL so browsers can
    -- cache it forever; 0 = no avatar
    avatar_version INTEGER NOT NULL DEFAULT 0
);

-- profile pictures, already square and small (the browser resizes them
-- before upload); kept apart from users so listing users stays light
CREATE TABLE IF NOT EXISTS avatars (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    image   BLOB NOT NULL,
    mime    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);

-- finished games, written once per game by stats.record_game
CREATE TABLE IF NOT EXISTS games (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   INTEGER NOT NULL,
    finished_at  INTEGER NOT NULL,
    rounds       INTEGER NOT NULL,
    player_count INTEGER NOT NULL
);

-- one row per player of a game; guests too (user_id NULL), so a profile can
-- list who the opponents were
CREATE TABLE IF NOT EXISTS game_players (
    game_id       INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    user_id       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    name          TEXT NOT NULL,
    place         INTEGER NOT NULL,
    score         INTEGER NOT NULL,
    won           INTEGER NOT NULL,
    eliminated    INTEGER NOT NULL,
    left_game     INTEGER NOT NULL,
    rounds_played INTEGER NOT NULL,
    rounds_won    INTEGER NOT NULL,
    bridges       INTEGER NOT NULL,
    resets        INTEGER NOT NULL,
    turns         INTEGER NOT NULL,
    cards_played  INTEGER NOT NULL,
    cards_drawn   INTEGER NOT NULL,
    penalty_drawn INTEGER NOT NULL,
    penalty_dealt INTEGER NOT NULL,
    skips_dealt   INTEGER NOT NULL,
    turns_skipped INTEGER NOT NULL,
    jacks_played  INTEGER NOT NULL,
    sixes_played  INTEGER NOT NULL,
    biggest_play  INTEGER NOT NULL,
    max_hand      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS game_players_user ON game_players(user_id);
CREATE INDEX IF NOT EXISTS game_players_game ON game_players(game_id);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:  # commit on success, rollback on error
            yield conn
    finally:
        conn.close()


# Columns added after a table first shipped: CREATE TABLE IF NOT EXISTS
# leaves an existing table alone, so older databases get them here.
COLUMN_MIGRATIONS = [
    ("users", "avatar_version", "INTEGER NOT NULL DEFAULT 0"),
]


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        for table, column, decl in COLUMN_MIGRATIONS:
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
