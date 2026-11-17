"""Small contextual epsilon-greedy learner, stored in SQLite; no model training."""
import math
import random
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from backend import course_store

ACTIONS = {'fast': 3, 'detailed': 5, 'context_aware': 5}
TASKS = ('question', 'summary', 'quiz', 'comparison')

def extract_context(question, history=()):
    """Only coarse categories leave request memory; never persist the question."""
    task = 'question'
    if re.search(r'compare|comparison', question, re.I): task = 'comparison'
    elif re.search(r'\b(quiz|mcqs?|multiple.choice)\b', question, re.I): task = 'quiz'
    elif re.search(r'\b(summarize|summarise|summary)\b', question, re.I): task = 'summary'
    followup = bool(history) and bool(re.search(
        r'\b(it|its|they|their|this|that|those|these)\b|^(and|also|why|how about)\b', question, re.I))
    return dict(task_type=task, is_followup=followup,
                query_length='short' if len(question.split()) <= 12 else 'long')

def context_key(context):
    if set(context) != {'task_type', 'is_followup', 'query_length'}:
        raise ValueError('Invalid context fields')
    if context['task_type'] not in TASKS or type(context['is_followup']) is not bool or context['query_length'] not in ('short','long'):
        raise ValueError('Invalid context categories')
    return f"{context['task_type']}:{int(context['is_followup'])}:{context['query_length']}"

def available_actions(context, *, page=None):
    context_key(context)
    # Existing document-scoped comparisons and page requests must remain intact.
    if context['task_type'] == 'comparison' or page is not None: return []
    if context['task_type'] == 'summary': return ['detailed','context_aware']
    return list(ACTIONS)

def select_action(values, allowed, epsilon=0.1, rng=None):
    if not allowed or any(a not in ACTIONS for a in allowed): raise ValueError('Invalid actions')
    if not math.isfinite(epsilon) or not 0 <= epsilon <= 1: raise ValueError('Invalid epsilon')
    for action in allowed:
        q = values.get(action, {}).get('q', 0.0)
        if type(q) not in (float, int) or not math.isfinite(q) or not 0 <= q <= 1:
            raise ValueError('Malformed action estimate')
    rng = rng or random.Random()
    if rng.random() < epsilon: return rng.choice(allowed)
    # Random ties avoid a permanent bias toward the first action during training.
    best = max(values.get(a, {}).get('q',0.0) for a in allowed)
    return rng.choice([a for a in allowed if values.get(a,{}).get('q',0.0)==best])

def calculate_reward(metrics, *, authorized=True, duration_ms=0, tool_calls=0, model_calls=0):
    """Observable reliability proxy, NOT factual truth. Failed/invalid results score zero."""
    if not authorized or metrics.get('success') is not True or metrics.get('citation_validity') is not True or metrics.get('evidence_available') is not True:
        return 0.0
    if metrics.get('passed') is False or metrics.get('structured_output_validity') is False:
        return 0.0
    for value in (duration_ms,tool_calls,model_calls):
        if not isinstance(value,(float,int)) or not math.isfinite(value) or value < 0: raise ValueError('Invalid performance metric')
    efficiency = max(0.0, 1 - (min(duration_ms/30000,1)+min(tool_calls/5,1)+min(model_calls/2,1))/3)
    factors = [(0.35,float(metrics['citation_validity'])),(0.25,float(metrics.get('task_completion') is True)),
               (0.10,1.0),(0.10,efficiency)]
    structured = metrics.get('structured_output_validity')
    if structured is not None: factors.append((0.20,float(structured is True)))
    return sum(w*v for w,v in factors)/sum(w for w,v in factors)

class PolicyStore:
    """Explicit path for experiments; default uses existing application SQLite."""
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else course_store.DATABASE_PATH

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS rl_values (
              context TEXT NOT NULL, action TEXT NOT NULL,
              observations INTEGER NOT NULL CHECK(observations >= 0),
              q REAL NOT NULL CHECK(q >= 0 AND q <= 1),
              epsilon REAL NOT NULL CHECK(epsilon >= 0 AND epsilon <= 1),
              updated_at TEXT NOT NULL, PRIMARY KEY(context, action));
            CREATE TABLE IF NOT EXISTS rl_metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')

    def load_policy(self, context):
        key = context_key(context)
        with self.connect() as db:
            rows = db.execute('SELECT * FROM rl_values WHERE context=?',(key,)).fetchall()
        result = {}
        for row in rows:
            if row['action'] not in ACTIONS or type(row['observations']) is not int or row['observations'] < 0 or not isinstance(row['q'],(int,float)) or not math.isfinite(row['q']) or not 0<=row['q']<=1 or not 0<=row['epsilon']<=1:
                raise ValueError('Malformed policy')
            datetime.fromisoformat(row['updated_at'])
            result[row['action']] = dict(row)
        return result

    def update_policy(self, context, action, reward, *, epsilon=0.1, alpha=None):
        if action not in available_actions(context): raise ValueError('Action not permitted for context')
        for value in (reward,epsilon):
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1: raise ValueError('Invalid policy value')
        if alpha is not None and (not math.isfinite(alpha) or not 0<alpha<=1): raise ValueError('Invalid alpha')
        key = context_key(context)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT q,observations FROM rl_values WHERE context=? AND action=?',(key,action)).fetchone()
            old,n = (row['q'],row['observations']) if row else (0.0,0)
            if not math.isfinite(old) or not 0<=old<=1 or type(n) is not int or n<0: raise ValueError('Malformed policy')
            n += 1
            rate = 1/n if alpha is None else alpha
            q = old + rate*(reward-old)
            db.execute('INSERT OR REPLACE INTO rl_values VALUES (?,?,?,?,?,?)',
                       (key,action,n,q,epsilon,datetime.now(timezone.utc).isoformat()))
            # Any training invalidates the previous held-out evaluation stamp.
            db.execute("DELETE FROM rl_metadata WHERE name='evaluated'")
        return q,n

    def save_policy(self):
        """Updates commit atomically; this explicit checkpoint returns observation count."""
        with self.connect() as db:
            return db.execute('SELECT COALESCE(SUM(observations),0) FROM rl_values').fetchone()[0]

    def mark_evaluated(self):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO rl_metadata VALUES ('evaluated','synthetic-heldout-v1')")

    def evaluated(self):
        with self.connect() as db:
            row=db.execute("SELECT value FROM rl_metadata WHERE name='evaluated'").fetchone()
        return bool(row and row[0]=='synthetic-heldout-v1')
