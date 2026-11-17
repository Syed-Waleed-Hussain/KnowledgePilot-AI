"""Small, bounded conversation helpers. Documents remain the factual evidence."""

import json
import re
from fastapi import HTTPException
from backend import course_store


def parse_saved_infographic(content):
    """Only restore a structured object; malformed legacy text stays inert."""
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    if not isinstance(parsed.get('title'), str) or not isinstance(parsed.get('layout'), str):
        return None
    return parsed


def load_history(session_id, course_id, user_id, limit=12, before_message_id=None):
    if not session_id:
        return []
    with course_store.connect() as database:
        session = database.execute(
            "SELECT 1 FROM chat_sessions WHERE session_id=? AND course_id=? AND user_id=?",
            (session_id, course_id, user_id),
        ).fetchone()
        if not session:
            raise HTTPException(404, "Chat session not found.")
        boundary = None
        if before_message_id:
            boundary = database.execute('SELECT rowid FROM chat_messages WHERE message_id=? AND session_id=? AND course_id=? AND user_id=?',
                (before_message_id, session_id, course_id, user_id)).fetchone()
            if not boundary:
                raise HTTPException(404, 'Chat turn not found.')
        rows = database.execute(
            "SELECT role, content, sources_json, created_at, request_id, failure_json, resolved_query FROM chat_messages AS m "
            "WHERE session_id=? AND course_id=? AND user_id=? AND m.rowid < ? "
            "ORDER BY COALESCE((SELECT parent.rowid FROM chat_messages AS parent "
            "WHERE parent.message_id='student:' || m.message_id AND parent.user_id=m.user_id "
            "AND parent.session_id=m.session_id),m.rowid) DESC, "
            "CASE WHEN m.role='student' THEN 0 ELSE 1 END DESC LIMIT ?",
            (session_id, course_id, user_id, boundary[0] if boundary else 9223372036854775807, limit),
        ).fetchall()
    messages = []
    for row in reversed(rows):
        item = {"role": row["role"], "text": row["content"],
                "sources": json.loads(row["sources_json"]), "created_at": row["created_at"],
                "request_id": row["request_id"], "resolved_query": row['resolved_query'],
                **json.loads(row["failure_json"] or '{}')}
        if row["role"] == "infographic":
            item["infographic"] = parse_saved_infographic(row["content"])
        messages.append(item)
    return messages


def is_follow_up(question):
    text = question.strip().lower().rstrip('?!.,')
    if re.search(r"\b(it|its|they|their|this|that|those|these)\b", text):
        return True
    return bool(re.fullmatch(
        r"(?:please\s+)?(?:why|how about|in detail|more details|(?:explain|tell me|elaborate)(?:\s+more|\s+in detail)?|"
        r"(?:give|show)(?: me)? an? example|(?:make|create|generate)(?: me)? (?:a )?quiz|"
        r"explain the (?:first|second|third|fourth|fifth|\d+) point)(?:\s+please)?", text))


def retrieval_question(question, history):
    """Resolve intent, never document facts. History must be owner/course scoped."""
    if not is_follow_up(question):
        return question
    topic = None
    for item in reversed(history):
        if item['role'] != 'student':
            continue
        if not is_follow_up(item['text']):
            topic = item['text'][:400]
            break
        resolved = item.get('resolved_query')
        if resolved and resolved != item['text']:
            topic = resolved.split('\nFollow-up:',1)[0].removeprefix('Previous topic: ')[:400]
            break
    if not topic:
        return question
    ordinal = ''
    if re.search(r'\b(?:first|second|third|fourth|fifth|\d+) point\b', question, re.I):
        ordinal = next((item['text'][:1600] for item in reversed(history)
                        if item['role'] == 'generated'), '')
    return f"Previous topic: {topic}\nFollow-up: {question}" + (f"\nPoint labels (context only): {ordinal}" if ordinal else '')
