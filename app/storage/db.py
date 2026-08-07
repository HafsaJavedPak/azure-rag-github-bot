# app/storage/db.py — updated

import json
import sqlite3
import uuid
from datetime import datetime

DB_PATH = "repos.db"


def _get_connection():
    return sqlite3.connect(DB_PATH)


def _init_db():
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS repos (
            repo_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner TEXT NOT NULL,
            status TEXT NOT NULL,
            file_count INTEGER,
            chunk_count INTEGER,
            error_message TEXT,
            indexed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            repo_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS github_auth (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            access_token TEXT NOT NULL,
            github_username TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def create_repo(repo_id: str, name: str, owner: str) -> None:
    """Called the instant POST /repos fires — before any real work starts.
    status='pending' so GET /repos/{repo_id} can find it immediately."""
    conn = _get_connection()
    conn.execute(
        "INSERT INTO repos (repo_id, name, owner, status) VALUES (?, ?, ?, ?)",
        (repo_id, name, owner, "pending"),
    )
    conn.commit()
    conn.close()


def mark_pending(repo_id: str) -> None:
    """Resets an existing repo's status back to 'pending' at the start of a
    re-sync — an UPDATE, not the INSERT create_repo does, since the row
    already exists. Clears any stale error_message from a previous failed
    sync too."""
    conn = _get_connection()
    conn.execute(
        "UPDATE repos SET status = ?, error_message = NULL WHERE repo_id = ?",
        ("pending", repo_id),
    )
    conn.commit()
    conn.close()


def mark_completed(repo_id: str, file_count: int, chunk_count: int) -> None:
    conn = _get_connection()
    conn.execute(
        "UPDATE repos SET status = ?, file_count = ?, chunk_count = ?, indexed_at = ?, error_message = NULL WHERE repo_id = ?",
        ("completed", file_count, chunk_count, datetime.utcnow().isoformat(), repo_id),
    )
    conn.commit()
    conn.close()


def mark_failed(repo_id: str, error_message: str) -> None:
    conn = _get_connection()
    conn.execute(
        "UPDATE repos SET status = ?, error_message = ? WHERE repo_id = ?",
        ("failed", error_message, repo_id),
    )
    conn.commit()
    conn.close()


def list_repos() -> list[dict]:
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM repos").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_repo(repo_id: str) -> dict | None:
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM repos WHERE repo_id = ?", (repo_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_repo(repo_id: str) -> None:
    conn = _get_connection()
    conn.execute("DELETE FROM repos WHERE repo_id = ?", (repo_id,))
    conn.commit()
    conn.close()


def create_conversation(repo_id: str) -> str:
    """One conversation belongs to exactly one repo for its whole lifetime —
    repo_id is set once here and every message inherits it, which is what
    lets the query endpoint know which repo a question is about."""
    conversation_id = str(uuid.uuid4())
    conn = _get_connection()
    conn.execute(
        "INSERT INTO conversations (conversation_id, repo_id, created_at) VALUES (?, ?, ?)",
        (conversation_id, repo_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return conversation_id


def get_conversation(conversation_id: str) -> dict | None:
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_conversations(repo_id: str | None = None) -> list[dict]:
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    if repo_id:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE repo_id = ?", (repo_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM conversations").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_conversation(conversation_id: str) -> None:
    """Deletes the conversation's messages first, then the conversation row
    itself — SQLite doesn't cascade-delete on its own here, so this has to
    be explicit (same "clean up the dependent data yourself" lesson as
    DELETE /repos/{repo_id} deleting vectors before the SQLite row)."""
    conn = _get_connection()
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
    conn.commit()
    conn.close()


def add_message(
    conversation_id: str, role: str, content: str, sources: list[dict] | None = None
) -> None:
    conn = _get_connection()
    conn.execute(
        "INSERT INTO messages (message_id, conversation_id, role, content, sources, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            conversation_id,
            role,
            content,
            json.dumps(sources) if sources else None,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_messages(conversation_id: str) -> list[dict]:
    """Full message history, oldest first — used by GET /conversations/{id}
    to show the whole conversation, as opposed to get_recent_messages below
    which is deliberately capped for prompt-building."""
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,),
    ).fetchall()
    conn.close()
    messages = [dict(row) for row in rows]
    for m in messages:
        if m["sources"]:
            m["sources"] = json.loads(m["sources"])
    return messages


def save_github_token(access_token: str, github_username: str) -> None:
    """Single-row table (id is CHECK-constrained to 1) — there's no user
    account system yet, so this is honestly scoped to "one connected GitHub
    account for this whole app". Keeping it as a real table rather than a
    config file means adding a user_id column later, if this ever needs to
    support multiple users, is a schema change rather than a rearchitecture.
    Upserts so re-connecting just overwrites the old token."""
    conn = _get_connection()
    conn.execute(
        """
        INSERT INTO github_auth (id, access_token, github_username, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            access_token = excluded.access_token,
            github_username = excluded.github_username,
            updated_at = excluded.updated_at
        """,
        (access_token, github_username, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_github_token() -> str | None:
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT access_token FROM github_auth WHERE id = 1").fetchone()
    conn.close()
    return row["access_token"] if row else None


def get_recent_messages(conversation_id: str, limit: int = 6) -> list[dict]:
    """The last `limit` messages, oldest first — feeds build_prompt()'s
    history parameter. Caps at the DB query level (LIMIT + ORDER BY DESC,
    then reversed) rather than fetching the whole conversation and slicing
    in Python, so a long-running conversation never gets pulled into memory
    just to discard most of it."""
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    conn.close()
    messages = [dict(row) for row in rows]
    messages.reverse()
    for m in messages:
        if m["sources"]:
            m["sources"] = json.loads(m["sources"])
    return messages


_init_db()
