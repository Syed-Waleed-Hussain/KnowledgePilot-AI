"""Private research data in the existing SQLite database. No learning tables change."""
import json
import uuid
from fastapi import HTTPException
from backend import course_store

def initialize():
    with course_store.connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS research_topics (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(id,user_id));
        CREATE TABLE IF NOT EXISTS research_public_papers (
          provider TEXT NOT NULL, external_id TEXT NOT NULL, metadata_json TEXT NOT NULL,
          PRIMARY KEY(provider,external_id));
        CREATE TABLE IF NOT EXISTS research_papers (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, topic_id TEXT NOT NULL,
          provider TEXT NOT NULL, external_id TEXT NOT NULL, metadata_json TEXT NOT NULL,
          saved_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(id,user_id),
          UNIQUE(user_id,topic_id,provider,external_id),
          FOREIGN KEY(topic_id,user_id) REFERENCES research_topics(id,user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS research_notes (
          paper_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, note_text TEXT NOT NULL DEFAULT '',
          generated_summary TEXT NOT NULL DEFAULT '', updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(paper_id,user_id) REFERENCES research_papers(id,user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS research_seen (
          user_id TEXT NOT NULL, topic_id TEXT NOT NULL, provider TEXT NOT NULL, external_id TEXT NOT NULL,
          first_seen TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,topic_id,provider,external_id),
          FOREIGN KEY(topic_id,user_id) REFERENCES research_topics(id,user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS research_searches (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, topic_id TEXT NOT NULL, search_query TEXT NOT NULL,
          checked_at TEXT DEFAULT CURRENT_TIMESTAMP, result_count INTEGER NOT NULL,
          FOREIGN KEY(topic_id,user_id) REFERENCES research_topics(id,user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS research_outputs (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, topic_id TEXT NOT NULL, task TEXT NOT NULL,
          paper_ids_json TEXT NOT NULL, answer TEXT NOT NULL, request_key TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,request_key),
          FOREIGN KEY(topic_id,user_id) REFERENCES research_topics(id,user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS research_http_cache (
          cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS research_provider_state (
          provider TEXT PRIMARY KEY, next_at REAL NOT NULL DEFAULT 0,
          busy_until REAL NOT NULL DEFAULT 0, lease TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS idx_research_topics_owner ON research_topics(user_id);
        CREATE INDEX IF NOT EXISTS idx_research_papers_owner ON research_papers(user_id,topic_id);
        CREATE INDEX IF NOT EXISTS idx_research_searches_owner ON research_searches(user_id,topic_id);
        ''')

def require_topic(topic_id,user_id):
    with course_store.connect() as db:
        row=db.execute('SELECT * FROM research_topics WHERE id=? AND user_id=?',(topic_id,user_id)).fetchone()
    if not row: raise HTTPException(404,'Research topic unavailable.')
    return dict(row)

def topics(user_id):
    with course_store.connect() as db:
        return [dict(row) for row in db.execute('SELECT * FROM research_topics WHERE user_id=? ORDER BY rowid DESC',(user_id,))]

def create_topic(title,user_id):
    title=title.strip()
    if not 1<=len(title)<=120: raise HTTPException(422,'Use a topic title of 1–120 characters.')
    topic_id=uuid.uuid4().hex
    with course_store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT COUNT(*) FROM research_topics WHERE user_id=?',(user_id,)).fetchone()[0]>=10:
            raise HTTPException(429,'You can create up to 10 research topics.')
        db.execute('INSERT INTO research_topics(id,user_id,title) VALUES (?,?,?)',(topic_id,user_id,title))
    return require_topic(topic_id,user_id)

def record_search(topic_id,user_id,query,papers):
    require_topic(topic_id,user_id)
    new_ids=[]
    with course_store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for paper in papers[:10]:
            key=(user_id,topic_id,paper['provider'],paper['external_id'])
            exists=db.execute('SELECT 1 FROM research_seen WHERE user_id=? AND topic_id=? AND provider=? AND external_id=?',key).fetchone()
            if not exists: new_ids.append(paper['provider']+':'+paper['external_id'])
            db.execute('INSERT OR IGNORE INTO research_seen(user_id,topic_id,provider,external_id) VALUES (?,?,?,?)',key)
            db.execute('INSERT OR REPLACE INTO research_public_papers VALUES (?,?,?)',
                       (paper['provider'],paper['external_id'],json.dumps(paper)))
        db.execute('INSERT INTO research_searches(id,user_id,topic_id,search_query,result_count) VALUES (?,?,?,?,?)',
                   (uuid.uuid4().hex,user_id,topic_id,query,len(papers[:10])))
    return new_ids

def save_paper(topic_id,user_id,provider,external_id):
    require_topic(topic_id,user_id)
    with course_store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # Only server-discovered metadata can enter the library.
        paper=db.execute('SELECT p.metadata_json FROM research_public_papers p JOIN research_seen s ON '
          's.provider=p.provider AND s.external_id=p.external_id WHERE s.user_id=? AND s.topic_id=? AND s.provider=? AND s.external_id=?',
          (user_id,topic_id,provider,external_id)).fetchone()
        if not paper: raise HTTPException(404,'Discover this paper in your topic before saving it.')
        existing=db.execute('SELECT id FROM research_papers WHERE user_id=? AND topic_id=? AND provider=? AND external_id=?',
                            (user_id,topic_id,provider,external_id)).fetchone()
        if existing: return get_paper(existing['id'],user_id)
        if db.execute('SELECT COUNT(*) FROM research_papers WHERE user_id=? AND topic_id=?',(user_id,topic_id)).fetchone()[0]>=100:
            raise HTTPException(429,'A research topic can contain up to 100 saved papers.')
        paper_id=uuid.uuid4().hex
        db.execute('INSERT INTO research_papers(id,user_id,topic_id,provider,external_id,metadata_json) VALUES (?,?,?,?,?,?)',
                   (paper_id,user_id,topic_id,provider,external_id,paper['metadata_json']))
    return get_paper(paper_id,user_id)

def unpack(row):
    result=dict(row);metadata=json.loads(result.pop('metadata_json'))
    return dict(metadata,**result)

def get_paper(paper_id,user_id):
    with course_store.connect() as db:
        row=db.execute('SELECT * FROM research_papers WHERE id=? AND user_id=?',(paper_id,user_id)).fetchone()
        if not row: raise HTTPException(404,'Research paper unavailable.')
        note=db.execute('SELECT note_text,generated_summary,updated_at AS note_updated_at FROM research_notes WHERE paper_id=? AND user_id=?',(paper_id,user_id)).fetchone()
    return dict(unpack(row),**(dict(note) if note else dict(note_text='',generated_summary='',note_updated_at=None)))

def list_papers(topic_id,user_id):
    require_topic(topic_id,user_id)
    with course_store.connect() as db:
        rows=db.execute('SELECT p.*,COALESCE(n.note_text,\'\') AS note_text,n.updated_at AS note_updated_at '
                        'FROM research_papers p LEFT JOIN research_notes n ON n.paper_id=p.id AND n.user_id=p.user_id '
                        'WHERE p.topic_id=? AND p.user_id=? ORDER BY p.saved_at DESC,p.rowid DESC',(topic_id,user_id)).fetchall()
    return [unpack(row) for row in rows]

def selected_papers(topic_id,user_id,paper_ids):
    require_topic(topic_id,user_id)
    if len(set(paper_ids))!=len(paper_ids): raise HTTPException(422,'Select distinct papers.')
    result=[get_paper(paper_id,user_id) for paper_id in paper_ids]
    if any(p['topic_id']!=topic_id for p in result): raise HTTPException(404,'Research paper unavailable.')
    return result

def save_note(paper_id,user_id,text=None,summary=None):
    get_paper(paper_id,user_id)
    if text is not None and len(text)>5000: raise HTTPException(422,'Notes are limited to 5000 characters.')
    with course_store.connect() as db:
        db.execute('INSERT OR IGNORE INTO research_notes(paper_id,user_id) VALUES (?,?)',(paper_id,user_id))
        if text is not None:
            db.execute('UPDATE research_notes SET note_text=?,updated_at=CURRENT_TIMESTAMP WHERE paper_id=? AND user_id=?',(text,paper_id,user_id))
        if summary is not None:
            db.execute('UPDATE research_notes SET generated_summary=?,updated_at=CURRENT_TIMESTAMP WHERE paper_id=? AND user_id=?',(summary,paper_id,user_id))
    return get_paper(paper_id,user_id)

def search_history(topic_id,user_id):
    require_topic(topic_id,user_id)
    with course_store.connect() as db:
        return [dict(r) for r in db.execute('SELECT search_query,checked_at,result_count FROM research_searches WHERE topic_id=? AND user_id=? ORDER BY rowid DESC LIMIT 30',(topic_id,user_id))]

def outputs(topic_id,user_id):
    require_topic(topic_id,user_id)
    with course_store.connect() as db:
        return [dict(r) for r in db.execute('SELECT id,task,answer,created_at FROM research_outputs WHERE topic_id=? AND user_id=? ORDER BY rowid DESC LIMIT 30',(topic_id,user_id))]
