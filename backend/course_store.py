"""Small SQLite helpers for private courses, documents, and chat history."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

STORAGE_ROOT = Path(os.getenv(
    "KNOWLEDGEPILOT_STORAGE_PATH",
    str(Path(__file__).resolve().parent / "storage_phase3"),
)).resolve()
DATABASE_PATH = STORAGE_ROOT / "courses.sqlite3"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    """Add ownership while preserving legacy rows as unassigned."""
    with connect() as database:
        course_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(courses)")
        }
        if course_columns and "user_id" not in course_columns:
            # Rebuild the old globally-unique course table so names can repeat per student.
            course_rows = database.execute("SELECT * FROM courses").fetchall()
            document_rows = database.execute("SELECT * FROM documents").fetchall()
            database.execute("PRAGMA foreign_keys = OFF")
            database.execute("BEGIN IMMEDIATE")
            database.execute("DROP TABLE documents")
            database.execute("DROP TABLE courses")
            _create_tables(database)
            database.executemany(
                "INSERT INTO courses (course_id, user_id, name, created_at) VALUES (?, NULL, ?, ?)",
                [(row["course_id"], row["name"], row["created_at"]) for row in course_rows],
            )
            database.executemany(
                "INSERT INTO documents (document_id, user_id, course_id, filename, file_hash, stored_path, page_count, chunk_count, status, created_at) "
                "VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(row["document_id"], row["course_id"], row["filename"], row["file_hash"],
                  row["stored_path"], row["page_count"], row["chunk_count"], row["status"], row["created_at"])
                 for row in document_rows],
            )
            database.execute("PRAGMA foreign_keys = ON")
        else:
            _create_tables(database)
            _add_column(database, "courses", "user_id", "TEXT")
            _add_column(database, "documents", "user_id", "TEXT")
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                course_id TEXT NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS question_reservations (
                user_id TEXT NOT NULL,
                request_key TEXT NOT NULL,
                question_hash TEXT NOT NULL,
                PRIMARY KEY (user_id, request_key)
            );
            CREATE TABLE IF NOT EXISTS daily_usage (
                user_id TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                question_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, usage_date)
            );
            CREATE TABLE IF NOT EXISTS processing_jobs (
                job_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                course_id TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_courses_user ON courses(user_id);
            CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(user_id, course_id);
            CREATE INDEX IF NOT EXISTS idx_chat_owner ON chat_messages(user_id, course_id);
            """
        )
        _add_column(database, "processing_jobs", "course_id", "TEXT")
        _add_column(database, "chat_messages", "request_id", "TEXT")
        _add_column(database, "chat_messages", "resolved_query", "TEXT")
        _add_column(database, "chat_messages", "failure_json", "TEXT NOT NULL DEFAULT '{}'")
        # Any unfinished local upload was interrupted by a previous backend stop.
        database.execute("UPDATE processing_jobs SET status = 'interrupted' WHERE status = 'processing'")


def _create_tables(database: sqlite3.Connection) -> None:
    database.execute(
        "CREATE TABLE IF NOT EXISTS courses ("
        "course_id TEXT PRIMARY KEY, user_id TEXT, name TEXT NOT NULL COLLATE NOCASE, "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, name))"
    )
    database.execute(
        "CREATE TABLE IF NOT EXISTS documents ("
        "document_id TEXT PRIMARY KEY, user_id TEXT, "
        "course_id TEXT NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE, "
        "filename TEXT NOT NULL, file_hash TEXT NOT NULL, stored_path TEXT NOT NULL, "
        "page_count INTEGER NOT NULL, chunk_count INTEGER NOT NULL, status TEXT NOT NULL, "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(course_id, file_hash))"
    )


def _add_column(database: sqlite3.Connection, table: str, name: str, kind: str) -> None:
    columns = {row["name"] for row in database.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        database.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def register_user(user_id: str) -> None:
    """Remember the provider-verified account ID without copying profile data."""
    with connect() as database:
        database.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))


def course_exists(course_id: str, user_id: str) -> bool:
    with connect() as database:
        return database.execute(
            "SELECT 1 FROM courses WHERE course_id = ? AND user_id = ?",
            (course_id, user_id),
        ).fetchone() is not None


def course_documents(course_id: str, user_id: str) -> list[dict[str, Any]]:
    with connect() as database:
        rows = database.execute(
            "SELECT document_id, course_id, filename, page_count, chunk_count, status, created_at "
            "FROM documents WHERE course_id = ? AND user_id = ? ORDER BY created_at DESC",
            (course_id, user_id),
        ).fetchall()
    return [row_to_dict(row) for row in rows]
