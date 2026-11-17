"""Durable turn metadata; request identity is independent of provider credentials."""
import json
import time
import math
from fastapi import HTTPException
from backend import course_store


def begin_turn(answer_id, session_id, user_id, course_id, question, request_id, resolved_query=None):
    with course_store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT content, failure_json FROM chat_messages WHERE message_id=? AND user_id=? AND course_id=? AND session_id=?',
                         ('student:' + answer_id, user_id, course_id, session_id)).fetchone()
        if row:
            if row['content'] != question:
                raise HTTPException(409, 'This request ID already belongs to a different message.')
            failure = json.loads(row['failure_json'] or '{}')
            wait = math.ceil(failure.get('retry_at', 0) - time.time())
            if wait > 0:
                raise HTTPException(429, dict(message='Please wait before retrying this saved turn.',
                    error_category=failure.get('error_category', 'in_progress'), retry_after=wait), headers={'Retry-After': str(wait)})
        pending = json.dumps(dict(error='This turn was interrupted or is still processing. Retry if no answer arrives.',
            error_category='in_progress', retryable=True, retry_at=time.time()+120))
        db.execute('INSERT OR IGNORE INTO chat_messages(message_id,session_id,user_id,course_id,role,content,request_id) VALUES (?,?,?,?,?,?,?)',
                   ('student:' + answer_id, session_id, user_id, course_id, 'student', question, request_id))
        db.execute('UPDATE chat_messages SET failure_json=? WHERE message_id=? AND user_id=?', (pending, 'student:' + answer_id, user_id))
        db.execute('UPDATE chat_messages SET resolved_query=COALESCE(resolved_query,?) WHERE message_id=? AND user_id=?',
                   (resolved_query, 'student:' + answer_id, user_id))


def fail_turn(answer_id, user_id, result):
    failure = {key: result.get(key) for key in ('error', 'error_category', 'retryable', 'retry_after')}
    failure['retry_at'] = time.time() + (result.get('retry_after') or 0)
    with course_store.connect() as db:
        db.execute('UPDATE chat_messages SET failure_json=? WHERE message_id=? AND user_id=?',
                   (json.dumps(failure), 'student:' + answer_id, user_id))


def complete_turn(answer_id, session_id, user_id, course_id, answer, sources, role='generated'):
    if role not in ('generated', 'infographic'):
        raise ValueError('Unsupported chat answer role.')
    with course_store.connect() as db:
        db.execute('INSERT OR IGNORE INTO chat_messages(message_id,session_id,user_id,course_id,role,content,sources_json) VALUES (?,?,?,?,?,?,?)',
                   (answer_id, session_id, user_id, course_id, role, answer, json.dumps(sources)))
        db.execute("UPDATE chat_messages SET failure_json='{}' WHERE message_id=? AND user_id=?", ('student:' + answer_id, user_id))
