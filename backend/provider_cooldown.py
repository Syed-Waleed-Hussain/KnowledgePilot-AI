"""One shared Groq cooldown, independent of credential selection and student IDs."""
import math
import time
from backend import course_store


def cooldown(seconds=None):
    with course_store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS ai_provider_cooldown(provider TEXT PRIMARY KEY, retry_at REAL NOT NULL)')
        if seconds is not None:
            db.execute("INSERT INTO ai_provider_cooldown VALUES ('groq',?) ON CONFLICT(provider) DO UPDATE SET retry_at=MAX(retry_at,excluded.retry_at)",
                       (time.time()+seconds,))
        row = db.execute("SELECT retry_at FROM ai_provider_cooldown WHERE provider='groq'").fetchone()
    return max(0, math.ceil(row[0]-time.time())) if row else 0
