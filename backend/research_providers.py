"""Fixed public API endpoints, bounded bodies, persistent pacing, no PDF downloads."""
import hashlib
import json
import re
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from fastapi import HTTPException
from backend import course_store

ATOM={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'}
ENDPOINTS={'arxiv':'https://export.arxiv.org/api/query',
           'semantic_scholar':'https://api.semanticscholar.org/graph/v1/paper/search'}

class ProviderError(RuntimeError):
    def __init__(self, message, status_code=503, retry_after=None):
        super().__init__(message);self.status_code=status_code;self.retry_after=retry_after
        self.category='research_rate_limit' if status_code==429 else 'research_unavailable'

def clean(value,limit=6000):
    return ' '.join(value.split())[:limit] if isinstance(value,str) else ''


def normalize_query(query):
    """Conservative spelling/terminology fixes; never change the saved topic."""
    query=clean(query,300)
    query=re.sub(r'\bspecial needs? children(?:s)?\b','special needs education',query,flags=re.I)
    query=re.sub(r'\bhealth care\b','healthcare',query,flags=re.I)
    query=re.sub(r'\bagentic ai\b','agentic artificial intelligence',query,flags=re.I)
    return query


def arxiv_queries(query):
    words=[word for word in re.findall(r'[\w-]+',query.lower())
           if word not in {'a','an','the','for','of','in','on','and','with'}][:12]
    if not words:raise ProviderError('Enter a more specific academic topic.',422)
    queries=[' AND '.join('all:'+word for word in words)]
    if 'special' in words and ('needs' in words or 'education' in words):
        queries.append('(all:"special needs" OR all:"special education") AND (all:"digital learning" OR all:"educational technology" OR all:"e-learning")')
    elif 'agentic' in words and 'healthcare' in words:
        queries.append('(all:agentic OR all:"AI agents") AND (all:healthcare OR all:"health care" OR all:clinical OR all:medical)')
    return queries  # At most one bounded alternative, only after a valid empty feed.

def metadata(provider,external_id,title,authors,abstract='',year=None,doi=None,**extra):
    if provider=='arxiv':
        match=re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?',external_id)
        if not match:return None
        external_id=re.sub(r'v\d+$','',external_id)
        url='https://arxiv.org/abs/'+external_id
    elif provider=='semantic_scholar' and re.fullmatch(r'[0-9a-fA-F]{40}',external_id):
        url='https://www.semanticscholar.org/paper/'+external_id
    else:return None
    title=clean(title,500)
    if not title:return None
    year=int(year) if str(year).isdigit() and 1000<=int(year)<=datetime.now().year+1 else None
    doi=clean(doi,200)
    if not re.fullmatch(r'10\.\d{4,9}/[^\s<>"{}]+',doi):doi=None
    return dict(provider=provider,external_id=external_id,title=title,
                authors=[clean(a,150) for a in (authors or [])[:50] if isinstance(a,str) and clean(a)],
                abstract=clean(abstract),year=year,doi=doi,source_url=url,**extra)

def parse_arxiv(body):
    if len(body)>2_000_000 or b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
        raise ProviderError('arXiv returned unsupported metadata.')
    try:root=ET.fromstring(body)
    except ET.ParseError:raise ProviderError('arXiv returned unreadable metadata.') from None
    if root.tag!='{http://www.w3.org/2005/Atom}feed':raise ProviderError('arXiv returned an invalid feed.')
    papers=[]
    for entry in root.findall('a:entry',ATOM)[:10]:
        identifier=entry.findtext('a:id','',ATOM)
        raw_id=identifier.split('/abs/')[-1]
        published=clean(entry.findtext('a:published','',ATOM),40)
        paper=metadata('arxiv',raw_id,entry.findtext('a:title','',ATOM),
            [a.findtext('a:name','',ATOM) for a in entry.findall('a:author',ATOM)],
            entry.findtext('a:summary','',ATOM),published[:4],entry.findtext('x:doi','',ATOM),
            published_at=published or None,updated_at=clean(entry.findtext('a:updated','',ATOM),40) or None)
        if paper:papers.append(paper)
    # arXiv may return an error entry with HTTP 200.
    if root.findall('a:entry',ATOM) and not papers:raise ProviderError('arXiv could not process this search.')
    return papers

def parse_semantic(body):
    try:data=json.loads(body)
    except (ValueError,UnicodeDecodeError):raise ProviderError('Semantic Scholar returned unreadable metadata.') from None
    if not isinstance(data,dict) or not isinstance(data.get('data'),list):raise ProviderError('Semantic Scholar returned invalid metadata.')
    papers=[]
    for item in data['data'][:10]:
        if not isinstance(item,dict):continue
        ids=item.get('externalIds') or {};authors=item.get('authors') or []
        citations=item.get('citationCount')
        paper=metadata('semantic_scholar',str(item.get('paperId') or ''),item.get('title'),
            [a.get('name') for a in authors if isinstance(a,dict)],item.get('abstract'),item.get('year'),
            ids.get('DOI') if isinstance(ids,dict) else None,
            citation_count=citations if type(citations) is int and citations>=0 else None,
            published_at=None,updated_at=None)
        if paper:papers.append(paper)
    return papers

def retry_seconds(value):
    try:
        seconds=float(value)
        if 0<=seconds<=365*86400:return max(3,seconds)
    except (ValueError,TypeError,OverflowError):pass
    try:return max(3,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
    except (ValueError,TypeError,OverflowError):return 60

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fetch_public(url):
    try:
        request=Request(url,headers={'User-Agent':'KnowledgePilot-AcademicResearch/0.1','Accept':'application/atom+xml, application/json'})
        with build_opener(NoRedirect).open(request,timeout=10) as response:
            body=response.read(2_000_001)
            if len(body)>2_000_000:raise ProviderError('Research metadata exceeded the response limit.')
            return body
    except HTTPError as error:
        if error.code==429:raise ProviderError('Research provider rate limit reached. Please wait before checking again.',429,retry_seconds(error.headers.get('Retry-After'))) from None
        raise ProviderError('Research provider is temporarily unavailable.') from None
    except (URLError,TimeoutError,OSError):raise ProviderError('Research provider timed out or could not be reached.') from None

def search_provider(provider,query,limit=10,fetcher=None):
    if provider not in ENDPOINTS:raise ProviderError('Research provider is not permitted.',400)
    query=normalize_query(query)
    if not query:raise ProviderError('Enter a research query.',422)
    limit=max(1,min(limit,10))
    # New query semantics must not reuse old exact-phrase empty caches.
    cache_key=hashlib.sha256(f'keyword-v2:{provider}:{query.casefold()}:{limit}'.encode()).hexdigest()
    now=time.time();lease=uuid.uuid4().hex
    with course_store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        cached=db.execute('SELECT payload FROM research_http_cache WHERE cache_key=? AND expires_at>?',(cache_key,now)).fetchone()
        if cached:
            papers=json.loads(cached['payload'])
            return dict(papers=papers,cached=True,query_used=query,status='ok' if papers else 'empty')
        db.execute('INSERT OR IGNORE INTO research_provider_state(provider) VALUES (?)',(provider,))
        state=db.execute('SELECT * FROM research_provider_state WHERE provider=?',(provider,)).fetchone()
        if max(state['next_at'],state['busy_until'])>now:
            raise ProviderError('Research search is cooling down. Please try again later.',429,max(3,int(max(state['next_at'],state['busy_until'])-now)+1))
        db.execute('UPDATE research_provider_state SET next_at=?,busy_until=?,lease=? WHERE provider=?',(now+3,now+60,lease,provider))
    cooldown=0
    try:
        if provider=='arxiv':
            alternatives=arxiv_queries(query)
            params=dict(search_query=alternatives[0],start=0,max_results=limit,sortBy='relevance',sortOrder='descending')
        else:params=dict(query=query,limit=limit,fields='title,authors,abstract,year,citationCount,externalIds,url')
        body=(fetcher or fetch_public)(ENDPOINTS[provider]+'?'+urlencode(params))
        papers=(parse_arxiv(body) if provider=='arxiv' else parse_semantic(body))[:limit]
        if provider=='arxiv' and not papers and len(alternatives)>1:
            # Keep the persistent provider lease and obey pacing even on alternatives.
            time.sleep(max(0,now+3-time.time()))
            params['search_query']=alternatives[1]
            try:
                body=(fetcher or fetch_public)(ENDPOINTS[provider]+'?'+urlencode(params))
                papers=parse_arxiv(body)[:limit]
            finally:
                with course_store.connect() as db:
                    db.execute('UPDATE research_provider_state SET next_at=MAX(next_at,?) WHERE provider=? AND lease=?',(time.time()+3,provider,lease))
        with course_store.connect() as db:
            # Bounded public query cache. Private libraries are never evicted here.
            db.execute('DELETE FROM research_http_cache WHERE expires_at<?',(time.time(),))
            if db.execute('SELECT COUNT(*) FROM research_http_cache').fetchone()[0]<2000:
                db.execute('INSERT OR REPLACE INTO research_http_cache VALUES (?,?,?)',(cache_key,json.dumps(papers),time.time()+(3600 if papers else 60)))
        return dict(papers=papers,cached=False,query_used=query,status='ok' if papers else 'empty')
    except ProviderError as error:
        cooldown=error.retry_after or 0
        raise
    finally:
        with course_store.connect() as db:
            db.execute('UPDATE research_provider_state SET busy_until=0,next_at=MAX(next_at,?),lease=\'\' WHERE provider=? AND lease=?',(time.time()+cooldown,provider,lease))

def search_arxiv_papers(query,limit=10):return search_provider('arxiv',query,limit)
def search_semantic_scholar(query,limit=5):return search_provider('semantic_scholar',query,limit)
