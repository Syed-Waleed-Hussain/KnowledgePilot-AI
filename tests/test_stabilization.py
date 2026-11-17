"""Demo failures: synthetic data and provider/Groq mocks; no live tokens."""
import hashlib
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
import pytest
from fastapi import HTTPException
from test_phase76 import setup, immediate, EVIDENCE
from test_phase7 import ATOM, endpoint
from backend import app as api, course_store, research_store, research_providers as providers
from backend.research_api import create_router, SearchInput
from backend.phase5_evaluation import evaluate_answer
from backend import agent_harness as harness

EMPTY=b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
QUESTION='please tell me how can i prepare for exam of these 2 lectures'

@pytest.fixture
def research(setup):
    research_store.initialize()
    return research_store.create_topic('Agentic AI in health care','alice')

def test_query_normalization_and_encoding(research):
    urls=[]
    result=providers.search_provider('arxiv','Digital Learning for Special Need Childrens',fetcher=lambda url:urls.append(url) or ATOM)
    query=parse_qs(urlsplit(urls[0]).query)['search_query'][0]
    assert query=='all:digital AND all:learning AND all:special AND all:needs AND all:education'
    assert result['query_used']=='Digital Learning for special needs education'
    assert result['papers'][0]['source_url']=='https://arxiv.org/abs/2601.12345'

def test_bounded_alternative_obeys_pacing(research,monkeypatch):
    urls=[];waits=[]
    monkeypatch.setattr(providers.time,'sleep',lambda delay:waits.append(delay))
    def fetch(url): urls.append(url);return EMPTY if len(urls)==1 else ATOM
    result=providers.search_provider('arxiv','Agentic AI in health care',fetcher=fetch)
    assert len(urls)==2 and len(waits)==1 and waits[0]>0
    assert 'all:healthcare' in parse_qs(urlsplit(urls[1]).query)['search_query'][0]
    assert result['papers']
    with pytest.raises(providers.ProviderError) as error:
        providers.search_provider('arxiv','different topic',fetcher=lambda url:pytest.fail('Pacing bypass'))
    assert error.value.status_code==429

def test_legacy_empty_cache_not_reused(research):
    query='Agentic AI in health care'
    old_key=hashlib.sha256(f'arxiv:{query.casefold()}:10'.encode()).hexdigest()
    with course_store.connect() as db:
        db.execute('INSERT INTO research_http_cache VALUES (?,?,?)',(old_key,'[]',time.time()+3600))
    urls=[]
    result=providers.search_provider('arxiv',query,fetcher=lambda url:urls.append(url) or ATOM)
    assert urls and result['papers'] and not result['cached']

def test_provider_failure_is_not_cached_or_retried(research):
    calls=[]
    def fail(url):calls.append(url);raise providers.ProviderError('Unavailable',503)
    with pytest.raises(providers.ProviderError):providers.search_provider('arxiv','sensors',fetcher=fail)
    assert len(calls)==1
    with course_store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM research_http_cache').fetchone()[0]==0

def test_empty_success_short_cache(research):
    result=providers.search_provider('arxiv','unusualword',fetcher=lambda url:EMPTY)
    assert result['status']=='empty' and result['papers']==[]
    cached=providers.search_provider('arxiv','unusualword',fetcher=lambda url:pytest.fail('Cached empty should not fetch immediately'))
    assert cached['cached'] and cached['status']=='empty'
    with course_store.connect() as db:
        ttl=db.execute('SELECT expires_at FROM research_http_cache').fetchone()[0]-time.time()
        assert 0<ttl<=60

def discover(topic,secondary=True):
    fn=endpoint(create_router(lambda *a:pytest.fail('No Groq quota for discovery')),'/research/discover','POST')
    return fn(SearchInput(topic_id=topic['id'],query=topic['title'],secondary=secondary),{'id':'alice'})

def test_primary_failure_does_not_hide_secondary_results(research,monkeypatch):
    def fail(*a):raise providers.ProviderError('arXiv unavailable',503)
    monkeypatch.setattr(providers,'search_arxiv_papers',fail)
    paper=providers.parse_arxiv(ATOM)[0]
    monkeypatch.setattr(providers,'search_semantic_scholar',lambda *a:dict(papers=[paper],cached=False))
    result=discover(research)
    assert result['papers'] and result['search_status']=='results'
    assert result['provider_status'][0]['status']=='unavailable'
    assert result['reliability']['tool_calls']==2
    # Saving remains based on verified discovery metadata and owner checks.
    saved=research_store.save_paper(research['id'],'alice',paper['provider'],paper['external_id'])
    assert saved['source_url']==paper['source_url']
    with pytest.raises(HTTPException):research_store.get_paper(saved['id'],'bob')

def test_all_down_is_not_successful_zero(research,monkeypatch):
    def fail(*a):raise providers.ProviderError('Unavailable',503)
    monkeypatch.setattr(providers,'search_arxiv_papers',fail)
    monkeypatch.setattr(providers,'search_semantic_scholar',fail)
    result=discover(research)
    assert result['search_status']=='unavailable' and not result['cached']
    assert result['reliability']['status']=='failed'
    assert research_store.search_history(research['id'],'alice')==[]

def test_genuine_zero_and_secondary_limit_are_distinct(research,monkeypatch):
    monkeypatch.setattr(providers,'search_arxiv_papers',lambda *a:dict(papers=[],cached=False))
    def limited(*a):raise providers.ProviderError('Limit',429,25)
    monkeypatch.setattr(providers,'search_semantic_scholar',limited)
    result=discover(research)
    assert result['search_status']=='empty'
    assert [s['status'] for s in result['provider_status']]==['empty','rate_limited']
    assert result['provider_status'][1]['retry_after']==25

def lectures(setup,monkeypatch,missing=False):
    with course_store.connect() as db:
        db.execute("UPDATE documents SET filename='PIT Lecture 13.pdf' WHERE document_id='doc'")
        db.execute('INSERT INTO documents(document_id,user_id,course_id,filename,file_hash,stored_path,page_count,chunk_count,status) VALUES (?,?,?,?,?,?,?,?,?)',
            ('doc15','alice',setup.course,'PIT Lecture 15.pdf','synthetic15','synthetic15.pdf',1,1,'indexed'))
    calls=[]
    def search(*args,**kwargs):
        calls.append(kwargs)
        filters=kwargs['where']['$and']
        assert {'user_id':'alice'} in filters and {'course_id':setup.course} in filters
        document=next(f['document_id'] for f in filters if 'document_id' in f)
        if missing and document=='doc15':return []
        return [dict(EVIDENCE,source='PIT Lecture 13.pdf' if document=='doc' else 'PIT Lecture 15.pdf')]
    monkeypatch.setattr(api,'search_relevant_chunks',search)
    return calls

def test_exam_plan_retrieves_both_without_quiz_validation(setup,monkeypatch):
    calls=lectures(setup,monkeypatch)
    prompts=[]
    def answer(q,passages,history=None):
        prompts.append(q)
        assert len(passages)==2
        return '## Exam preparation\nRevise the tasks in Lecture 13 [1]. Then revise the responsibilities in Lecture 15 [2].'
    monkeypatch.setattr(api,'generate_answer',answer)
    result=setup.ask(QUESTION,'exam')
    assert result['mode']=='generated' and len(calls)==2
    assert 'study plan' in prompts[0] and 'quiz' not in prompts[0].lower()
    metric=evaluate_answer(QUESTION,result['answer'],[dict(EVIDENCE,source=s['filename']) for s in result['sources']],['PIT Lecture 13.pdf','PIT Lecture 15.pdf'])
    assert metric['passed'] and metric['structured_output_validity'] is None
    count=len(calls)
    assert setup.ask(QUESTION,'exam')['answer']==result['answer'] and len(calls)==count

def test_partial_lecture_coverage_is_explicit(setup,monkeypatch):
    lectures(setup,monkeypatch,missing=True)
    monkeypatch.setattr(api,'generate_answer',lambda *a:'Revise the supplied tasks [1].')
    result=setup.ask(QUESTION,'partial')
    assert result['mode']=='generated'
    assert 'Coverage limitation' in result['answer'] and 'PIT Lecture 15.pdf' in result['answer']
    assert len(result['sources'])==1

def test_exam_plan_through_mocked_groq_stays_prose(setup,monkeypatch):
    import llm_service
    lectures(setup,monkeypatch)
    monkeypatch.setenv('GROQ_API_KEY','synthetic-test-only')
    monkeypatch.setenv('GROQ_CREDENTIAL','primary')
    def create(**kwargs):
        prompt=kwargs['messages'][-1]['content']
        assert 'Return ONLY a JSON object' not in prompt
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Revise the supplied tasks [1], then the responsibilities [2].'))])
    monkeypatch.setattr(llm_service,'Groq',lambda **kwargs:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(api,'generate_answer',llm_service.generate_answer)
    result=setup.ask(QUESTION,'sdk-plan')
    assert result['mode']=='generated' and 'full exam coverage' in result['answer']

@pytest.mark.parametrize('marker',['[99]','[Source 99]','【99】'])
def test_invalid_citation_not_silently_cleaned(setup,monkeypatch,marker):
    import llm_service
    monkeypatch.setenv('GROQ_API_KEY','synthetic-test-only')
    monkeypatch.setenv('GROQ_CREDENTIAL','primary')
    response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Tasks [1]. Invalid '+marker))])
    monkeypatch.setattr(llm_service,'Groq',lambda **kwargs:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:response))))
    with pytest.raises(llm_service.LLMServiceError) as error:llm_service.generate_answer('Prepare for exam',[EVIDENCE])
    assert error.value.category=='validation'

@pytest.mark.parametrize('answer,reason', [('Uncited study plan','missing_citations'),('Study plan [99]','unsupported_citations'),('Only lecture 13 [1]','missing_lecture_citations')])
def test_validation_diagnoses_actual_rejection(setup,monkeypatch,answer,reason):
    class Deadline:
        async def __aenter__(self):pass
        async def __aexit__(self,*a):pass
    monkeypatch.setattr(harness.asyncio,'timeout',lambda seconds:Deadline())
    passages=[dict(EVIDENCE,source='PIT Lecture 13.pdf'),dict(EVIDENCE,source='PIT Lecture 15.pdf')]
    async def invoke(state):return dict(answer=answer,passages=passages,mode='generated')
    result=immediate(harness.run_graph(SimpleNamespace(ainvoke=invoke),dict(question=QUESTION,user_id='alice',course_id=setup.course,document_names=[p['source'] for p in passages]),harness.AgentRunContext('alice',setup.course)))
    assert result['mode']=='retrieval_only' and result['answer']==''
    assert reason in result['evaluation']['failure_reasons']
    assert result['evaluation']['structured_output_validity'] is None
    assert result['passages']==passages and result['retryable']
