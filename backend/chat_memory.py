"""Small, bounded conversation helpers. Documents remain the factual evidence."""

import json
import re
from fastapi import HTTPException
from backend import course_store


def load_history(session_id, course_id, user_id, limit=12):
    if not session_id:
        return []
    with course_store.connect() as database:
        session = database.execute(
            "SELECT 1 FROM chat_sessions WHERE session_id=? AND course_id=? AND user_id=?",
            (session_id, course_id, user_id),
        ).fetchone()
        if not session:
            raise HTTPException(404, "Chat session not found.")
        rows = database.execute(
            "SELECT role, content, sources_json, created_at FROM chat_messages "
            "WHERE session_id=? AND course_id=? AND user_id=? ORDER BY rowid DESC LIMIT ?",
            (session_id, course_id, user_id, limit),
        ).fetchall()
    return [{"role": row["role"], "text": row["content"],
             "sources": json.loads(row["sources_json"]), "created_at": row["created_at"]}
            for row in reversed(rows)]


def retrieval_question(question, history):
    # Resolve short references using recent user topics; never invent a document fact.
    follow_up = re.search(r"\b(it|its|they|their|this|that|those|these)\b|^(and|also|why|how about)\b",
                          question, re.IGNORECASE)
    topics = [item["text"][:400] for item in history if item["role"] == "student"][-3:]
    if follow_up and topics:
        return "Previous topics: " + " | ".join(topics) + "\nFollow-up: " + question
    return question
