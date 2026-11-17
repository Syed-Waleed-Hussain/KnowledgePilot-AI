"""Mock APIs/model calls and temporary SQLite only. Research graphs are synchronous."""
import json
import re
import pytest
from fastapi import HTTPException
from backend import course_store, research_store as store
from backend import research_providers as providers
from backend.agent_harness import HarnessError, AgentRunContext, Limits
from backend.research_api import create_router, TopicInput, SearchInput, SaveInput, NoteInput, AnalysisInput, ExportInput, research_context
from backend.research_quality import export_references, research_evidence, render_output
from backend.research_graph import build_research_graph

ATOM=b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"><entry><id>http://arxiv.org/abs/2601.12345v2</id><title>Synthetic Sensor Study</title><author><name>Synthetic Author</name></author><summary>Sensors measure physical quantities.</summary><published>2026-01-01T00:00:00Z</published><updated>2026-02-01T00:00:00Z</updated><arxiv:doi>10.1234/synthetic</arxiv:doi></entry></feed>'''

def paper(n=0):return dict(providers.parse_arxiv(ATOM)[0],external_id=f'2601.{12345+n}',title=f'Synthetic Study {n}',source_url=f'https://arxiv.org/abs/2601.{12345+n}')

@pytest.fixture
def db(tmp_path,monkeypatch):
    monkeypatch.setattr(course_store,'DATABASE_PATH',tmp_path/'private.sqlite3')
    course_store.initialize_database();store.initialize()
    return store.create_topic('Sensors','alice')

@pytest.fixture
def library(db):
    store.record_search(db['id'],'alice','sensor',[paper(i) for i in range(10)])
    return [store.save_paper(db['id'],'alice','arxiv',paper(i)['external_id']) for i in range(10)]

def endpoint(router,path,method):return next(r.endpoint for r in router.routes if r.path==path and method in r.methods)

def generated(task):
    headings={'summary':['Research problem','Main objective','Methodology','Key findings','Limitations'],
              'compare':['Comparison','Similarities','Differences'],
              'review':['Introduction','Research background','Major themes','Comparison of approaches','Research gaps','Conclusion']}[task]
    return '\n\n'.join('## '+h+'\n\nSupported synthetic information [1].' for h in headings)

def test_arxiv_parser_and_version_dedup():
    p=providers.parse_arxiv(ATOM)[0]
    assert p['external_id']=='2601.12345' and p['doi']=='10.1234/synthetic'
    assert p['authors']==['Synthetic Author'] and p['year']==2026
    assert p['published_at'] and p['updated_at']

def test_semantic_missing_fields():
    p=providers.parse_semantic(json.dumps({'data':[{'paperId':'a'*40,'title':'Synthetic','authors':None,'abstract':None}]}).encode())[0]
    assert p['abstract']=='' and p['year'] is None and p['authors']==[] and p['doi'] is None
    assert p['source_url']=='https://www.semanticscholar.org/paper/'+'a'*40

def test_semantic_fields():
    p=providers.parse_semantic(json.dumps({'data':[{'paperId':'a'*40,'title':'Synthetic','authors':[{'name':'Author'}],
        'abstract':'Abstract','year':2020,'citationCount':7,'externalIds':{'DOI':'10.1234/synthetic'},'url':'javascript:bad'}]}))[0]
    assert p['citation_count']==7 and p['doi']=='10.1234/synthetic' and p['source_url'].startswith('https://')

@pytest.mark.parametrize('bad',[b'<html>Error</html>',b'<!DOCTYPE x><feed/>',b'<feed'])
def test_invalid_xml(bad):
    with pytest.raises(providers.ProviderError):providers.parse_arxiv(bad)

def test_provider_cache_and_pacing(db):
    calls=[]
    def fetch(url):calls.append(url);return ATOM
    first=providers.search_provider('arxiv','sensors',fetcher=fetch)
    assert not first['cached']
    assert providers.search_provider('arxiv','sensors',fetcher=fetch)['cached']
    with pytest.raises(providers.ProviderError) as error:providers.search_provider('arxiv','other',fetcher=fetch)
    assert error.value.status_code==429 and len(calls)==1
    assert calls[0].startswith('https://export.arxiv.org/api/query?')

def test_provider_429_cooldown(db):
    def fail(url):raise providers.ProviderError('Wait',429,120)
    with pytest.raises(providers.ProviderError):providers.search_provider('arxiv','sensors',fetcher=fail)
    with course_store.connect() as connection:
        next_at=connection.execute("SELECT next_at FROM research_provider_state WHERE provider='arxiv'").fetchone()[0]
    import time
    assert next_at>time.time()+115
    with pytest.raises(providers.ProviderError) as error:providers.search_provider('arxiv','other',fetcher=lambda u:pytest.fail('No retry'))
    assert error.value.status_code==429

def test_fetch_timeout_and_redirect(monkeypatch):
    class Opener:
        def open(self,*a,**k):raise TimeoutError('secret path')
    monkeypatch.setattr(providers,'build_opener',lambda *a:Opener())
    with pytest.raises(providers.ProviderError) as error:providers.fetch_public('https://export.arxiv.org/api/query')
    assert 'secret' not in str(error.value)
    assert providers.NoRedirect().redirect_request(None,None,None,None,None,None) is None

def test_topic_and_deduplication(db,library):
    assert store.topics('bob')==[] and len(store.topics('alice'))==1
    assert len(store.list_papers(db['id'],'alice'))==10
    assert store.save_paper(db['id'],'alice','arxiv',paper()['external_id'])['id']==library[0]['id']
    with pytest.raises(HTTPException):store.save_paper(db['id'],'alice','arxiv','9999.99999')

def test_notes_and_summary_preserved(db,library):
    store.save_note(library[0]['id'],'alice',text='Private notes')
    store.save_note(library[0]['id'],'alice',summary='Abstract-based summary.')
    assert store.get_paper(library[0]['id'],'alice')['note_text']=='Private notes'

@pytest.mark.parametrize('operation',['topic','list','paper','note','history','outputs','save'])
def test_cross_student_denied(db,library,operation):
    functions={'topic':lambda:store.require_topic(db['id'],'bob'),'list':lambda:store.list_papers(db['id'],'bob'),
        'paper':lambda:store.get_paper(library[0]['id'],'bob'),'note':lambda:store.save_note(library[0]['id'],'bob',text='Overwrite'),
        'history':lambda:store.search_history(db['id'],'bob'),'outputs':lambda:store.outputs(db['id'],'bob'),
        'save':lambda:store.save_paper(db['id'],'bob','arxiv',paper()['external_id'])}
    with pytest.raises(HTTPException) as error:functions[operation]()
    assert error.value.status_code==404

def test_tracking_ids(db):
    assert store.record_search(db['id'],'alice','sensors',[paper()])==['arxiv:2601.12345']
    assert store.record_search(db['id'],'alice','sensors',[paper(),paper(1)])==['arxiv:2601.12346']
    assert len(store.search_history(db['id'],'alice'))==2

def test_exports_no_invented_fields(library):
    text=export_references(library[:2]);bib=export_references(library[:2],'bibtex')
    assert library[0]['source_url'] in text and '@misc{' in bib and 'archivePrefix = {arXiv}' in bib
    assert 'journal =' not in bib
    assert 'year =' not in export_references([dict(library[0],year=None)],'bibtex')
    assert '\\{' in export_references([dict(library[0],title='Untrusted {title}')],'bibtex')

def test_research_evidence_keeps_all_ten(library):
    limits=Limits();limits.passage_count=10
    evidence=research_evidence(library,limits)
    assert len(evidence)==10 and sum(len(p['text']) for p in evidence)<limits.context_chars
    assert all(p['page']=='abstract' for p in evidence)

def test_no_abstract_no_model(library):
    with pytest.raises(HTTPException):research_evidence([dict(library[0],abstract='')],Limits())

@pytest.mark.parametrize('task,count',[('summary',1),('compare',3),('review',10)])
def test_analysis_routes_graph_and_references(db,library,monkeypatch,task,count):
    quota=[];calls=[]
    def answer(prompt,evidence):
        calls.append(evidence)
        return generated(task)+'\n\nEvidence: '+' '.join(f'[{i}]' for i in range(1,len(evidence)+1))
    monkeypatch.setattr('backend.research_graph.generate_answer',answer)
    router=create_router(lambda *args:quota.append(args))
    analyze=endpoint(router,'/research/analyze','POST')
    request=AnalysisInput(topic_id=db['id'],task=task,paper_ids=[p['id'] for p in library[:count]],request_id='request')
    result=analyze(request,{'id':'alice'})
    assert len(calls)==len(quota)==1 and len(calls[0])==count
    assert result['reliability']['tool_calls']==result['reliability']['model_calls']==1
    assert 'full PDFs were not read' in result['answer']
    assert '[R1]('+library[0]['source_url']+')' in result['answer']
    assert '## References' in result['answer']
    assert analyze(request,{'id':'alice'})['replayed'] is True and len(calls)==1
    assert len(store.outputs(db['id'],'alice'))==1

def test_analysis_unauthorized_before_quota(db,library):
    analyze=endpoint(create_router(lambda *a:pytest.fail('No quota')),'/research/analyze','POST')
    request=AnalysisInput(topic_id=db['id'],task='summary',paper_ids=[library[0]['id']],request_id='x')
    with pytest.raises(HTTPException):analyze(request,{'id':'bob'})

def test_analysis_failure_not_saved(db,library,monkeypatch):
    monkeypatch.setattr('backend.research_graph.generate_answer',lambda *a:'Invented [99].')
    analyze=endpoint(create_router(lambda *a:None),'/research/analyze','POST')
    with pytest.raises(HTTPException):analyze(AnalysisInput(topic_id=db['id'],task='summary',paper_ids=[library[0]['id']],request_id='x'),{'id':'alice'})
    assert store.outputs(db['id'],'alice')==[]

def test_research_harness_permissions_and_limits(db,library):
    ctx=research_context('alice',db['id']);ctx.limits.tools=0
    with pytest.raises(HarnessError):ctx.tool_sync('list_saved_research_papers',dict(user_id='alice',topic_id=db['id']),lambda:pytest.fail('No tool'))
    ctx.limits.tools=5
    with pytest.raises(HarnessError):ctx.tool_sync('shell',dict(user_id='alice',topic_id=db['id']),lambda:None)
    with pytest.raises(HarnessError):ctx.tool_sync('list_saved_research_papers',dict(user_id='bob',topic_id=db['id']),lambda:None)
    ctx.limits.models=0
    with pytest.raises(HarnessError):ctx.model(lambda:pytest.fail('No model'))

def test_discovery_route_secondary_failure_keeps_arxiv(db,monkeypatch):
    monkeypatch.setattr(providers,'search_arxiv_papers',lambda *a:dict(papers=[paper()],cached=False))
    def fail(*a):raise providers.ProviderError('Rate limit',429,120)
    monkeypatch.setattr(providers,'search_semantic_scholar',fail)
    discover=endpoint(create_router(lambda *a:pytest.fail('No AI quota')),'/research/discover','POST')
    result=discover(SearchInput(topic_id=db['id'],query='sensors',secondary=True),{'id':'alice'})
    assert len(result['papers'])==1 and result['warnings']
    assert result['reliability']['tool_calls']==2 and result['reliability']['model_calls']==0

def test_all_routes_have_shared_auth():
    from backend.supabase_auth import get_current_user
    router=create_router(lambda *a:None)
    assert all(any(dep.call is get_current_user for dep in route.dependant.dependencies) for route in router.routes)
    with pytest.raises(HTTPException):get_current_user(authorization=None)

def test_client_cannot_supply_metadata_or_identity():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):SaveInput(topic_id='x',provider='arxiv',external_id='2601.12345',title='Invented',user_id='bob')

def test_review_requires_citations_for_every_paper(db,library,monkeypatch):
    monkeypatch.setattr('backend.research_graph.generate_answer',lambda *a:generated('review'))
    analyze=endpoint(create_router(lambda *a:None),'/research/analyze','POST')
    with pytest.raises(HTTPException):analyze(AnalysisInput(topic_id=db['id'],task='review',paper_ids=[p['id'] for p in library[:3]],request_id='x'),{'id':'alice'})
    assert store.outputs(db['id'],'alice')==[]

def test_bad_citations_rejected_with_valid_sections(db,library,monkeypatch):
    monkeypatch.setattr('backend.research_graph.generate_answer',lambda *a:generated('summary').replace('[1]','[99]'))
    analyze=endpoint(create_router(lambda *a:None),'/research/analyze','POST')
    with pytest.raises(HTTPException):analyze(AnalysisInput(topic_id=db['id'],task='summary',paper_ids=[library[0]['id']],request_id='x'),{'id':'alice'})
    assert store.outputs(db['id'],'alice')==[]

def test_metadata_markdown_injection_is_escaped(library):
    output=render_output('summary',generated('summary'),[dict(library[0],title='[Open](javascript:alert(1)) <script>bad</script>')])
    assert '\\[Open\\]' in output and '&lt;script&gt;' in output
    assert '[Original paper]('+library[0]['source_url']+')' in output

def test_cross_topic_selection_blocked(db,library):
    other=store.create_topic('Other','alice')
    with pytest.raises(HTTPException):store.selected_papers(other['id'],'alice',[library[0]['id']])

def test_original_course_rows_survive_migration(db):
    with course_store.connect() as connection:
        connection.execute('INSERT INTO courses(course_id,user_id,name) VALUES (?,?,?)',('legacy','alice','Existing course'))
    store.initialize()
    assert course_store.course_exists('legacy','alice')
