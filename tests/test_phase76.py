"""Synthetic SQLite, mocked Groq/MCP transport. No real provider tokens used.

The immediate coroutine driver avoids this sandbox's blocked event-loop sockets.
It tests real graph nodes/routes, not real MCP transport or async deadlines.
"""
import inspect
import json
import sqlite3
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from backend import app as api, course_store, phase4_graph
from backend.chat_memory import load_history, retrieval_question
from backend.agent_harness import AgentRunContext, Limits, HarnessError
from backend.answer_quality import prepare_answer, render_quiz
from backend.phase5_evaluation import evaluate_answer
from backend.rl_retrieval import choose_strategy
from llm_service import LLMServiceError, load_groq_settings, generate_answer

EVIDENCE = dict(text='Job Design defines tasks, responsibilities and relationships. Job rotation develops skills.', source='Lecture13.pdf', page=4, similarity=.9)

def immediate(coro):
    try:
        coro.send(None)
    except StopIteration as done:
        return done.value
    finally:
        coro.close()
    raise AssertionError('Unexpected real async I/O in mocked test')

class Nodes:
    def __init__(self, *args): self.nodes = {}
    def add_node(self, name, callback): self.nodes[name] = callback
    def add_edge(self, *args): pass
    def compile(self): return self

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(course_store, 'DATABASE_PATH', tmp_path/'courses.sqlite3')
    course_store.initialize_database()
    user = dict(id='alice')
    course = api.create_course(api.CourseInput(name='PPIT'), user)['course_id']
    session = api.create_chat(course, user)['session_id']
    with course_store.connect() as db:
        db.execute('INSERT INTO documents(document_id,user_id,course_id,filename,file_hash,stored_path,page_count,chunk_count,status) VALUES (?,?,?,?,?,?,?,?,?)',
                   ('doc','alice',course,'Lecture13.pdf','synthetic','synthetic.pdf',1,1,'indexed'))
    queries = []
    monkeypatch.setattr(api, 'get_collection', lambda: SimpleNamespace(count=lambda: 1))
    monkeypatch.setattr(api, 'get_model', lambda: None)
    def search(*args, **kwargs):
        queries.append((args[1], kwargs['where']))
        return [dict(EVIDENCE)]
    monkeypatch.setattr(api, 'search_relevant_chunks', search)
    monkeypatch.setattr(phase4_graph, 'StateGraph', Nodes)
    async def transport(server, trace, **kwargs):
        return server(**kwargs)
    monkeypatch.setattr(phase4_graph, 'build_document_server', lambda callback, **kwargs: callback)
    monkeypatch.setattr(phase4_graph, 'call_document_search', transport)
    async def run(graph, state, ctx):
        ctx.authorize('search_course_documents', state)
        state['run_context'] = ctx
        try:
            for node in ('prepare','retrieve','generate'):
                update = graph.nodes[node](state)
                state.update(await update if inspect.isawaitable(update) else update)
        except HarnessError as error:
            state.update(answer='', mode='retrieval_only', error=str(error), error_category=error.category)
        state['retryable'] = state.get('error_category') in ('rate_limit','provider_timeout','provider_connection','provider_server','mcp')
        state['evaluation'] = evaluate_answer(state['question'], state.get('answer',''), state.get('passages',[]))
        return state
    monkeypatch.setattr(api, 'run_graph', run)
    def answer(question, passages, history=None):
        if 'quiz' in question:
            return render_quiz({'questions':[dict(question=f'Job Design question {i}', options=dict(A='Tasks',B='Weather',C='Sports',D='Cooking'),correct_answer='A',explanation='Tasks are defined.',source_ids=[1]) for i in range(5)]},1)
        return 'Job Design defines responsibilities [1].'
    monkeypatch.setattr(api, 'generate_answer', answer)
    def ask(text, key, chat=session):
        return immediate(api.ask_question(api.QuestionRequest(course_id=course,session_id=chat,question=text,request_id=key),user))
    return SimpleNamespace(user=user, course=course, session=session, queries=queries, ask=ask)

@pytest.mark.parametrize('follow',['Explain more','In detail please','Give an example','Make a quiz','Explain the second point','What are its advantages?'])
def test_obvious_followups(follow):
    history = [dict(role='student',text='Can you define Job Design topic in detail?'),dict(role='generated',text='1. Tasks\n2. Responsibilities [1]')]
    assert 'Job Design' in retrieval_question(follow, history)
    assert retrieval_question(follow, []) == follow

def test_exact_conversation_and_new_chat(setup):
    s = setup
    for n, text in enumerate(['Please explain topics covered in lecture 13 in short','Can you define job design topic in detail?', 'in detail please','please explain it in detail','make a quiz for this topic']):
        result = s.ask(text, str(n))
        assert result['mode'] == 'generated'
        assert all(1 <= int(i) <= len(result['sources']) for i in __import__('re').findall(r'\[(\d+)\]',result['answer']))
    assert 'job design' in s.queries[2][0].lower()
    assert 'job design' in s.queries[4][0].lower()
    assert all(where == {'$and':[{'course_id':s.course},{'user_id':'alice'}]} for _,where in s.queries)
    fresh = api.create_chat(s.course,s.user)['session_id']
    assert s.ask('in detail please','fresh',fresh)['error_category'] == 'context_missing'
    assert len(load_history(s.session,s.course,'alice')) == 10

@pytest.mark.parametrize('failure',['rate_limit','provider_timeout','provider_connection','provider_server','model_unavailable','provider_auth'])
def test_failure_saved_retry_is_idempotent(setup, monkeypatch, failure):
    s=setup
    s.ask('Define Job Design','first')
    good=api.generate_answer
    def fail(*args): raise LLMServiceError('Synthetic provider failure',failure)
    monkeypatch.setattr(api,'generate_answer',fail)
    result=s.ask('in detail please','retry')
    assert result['answer'] is None and result['success'] is False
    assert result['error_category']==failure
    history=load_history(s.session,s.course,'alice')
    assert len(history)==3 and history[-1]['request_id']=='retry'
    monkeypatch.setenv('GROQ_CREDENTIAL','replacement')
    monkeypatch.setattr(api,'generate_answer',good)
    assert s.ask('in detail please','retry')['mode']=='generated'
    before=len(s.queries)
    assert s.ask('in detail please','retry')['mode']=='generated'
    assert len(s.queries)==before and len(load_history(s.session,s.course,'alice'))==4
    with course_store.connect() as db:
        assert db.execute('SELECT question_count FROM daily_usage').fetchone()[0]==2
    with pytest.raises(HTTPException): s.ask('different question','retry')

def test_no_evidence_and_rewrite_retry(setup,monkeypatch):
    s=setup
    s.ask('Define Job Design','topic')
    calls=[]
    def retrieve(*args,**kwargs):
        calls.append(args[1]); return [] if 'Follow-up:' in args[1] else [EVIDENCE]
    monkeypatch.setattr(api,'search_relevant_chunks',retrieve)
    assert s.ask('in detail please','resolved')['mode']=='generated'
    assert len(calls)==2 and calls[-1]=='Define Job Design'
    monkeypatch.setattr(api,'search_relevant_chunks',lambda *a,**k:[])
    assert s.ask('Define unrelated topic','none')['error_category']=='no_evidence'
    assert s.ask('in detail please','rewrite')['error_category']=='context_retrieval'

def test_quota_and_privacy_and_restart(setup,monkeypatch):
    s=setup
    monkeypatch.setattr(api,'MAX_DAILY_QUESTIONS',1)
    s.ask('Define Job Design','one')
    with pytest.raises(HTTPException) as error: s.ask('Define job rotation','two')
    assert error.value.status_code==429 and error.value.detail['error_category']=='app_quota'
    assert error.value.detail['resets_at'].endswith('T00:00:00Z')
    monkeypatch.setattr(api,'MAX_DAILY_QUESTIONS',30)
    assert s.ask('Define job rotation','two')['mode']=='generated'
    course_store.initialize_database()  # additive restart, no data recreation
    assert len(load_history(s.session,s.course,'alice'))==4
    with sqlite3.connect(course_store.DATABASE_PATH) as db:
        assert db.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0]==4
    for course,user in [(s.course,'bob'),('other','alice')]:
        with pytest.raises(HTTPException): load_history(s.session,course,user)

def test_markdown_math_code_and_citations():
    text='Job Design [1]\\\nMath $x \\times y$\n```\npath\\\n```\n## Sources\n[1] Lecture13.pdf'
    result=prepare_answer('Explain Job Design',text,1)
    assert 'Design [1]\\' not in result and r'\times' in result and 'path\\' in result
    assert '## Sources' not in result and '[1]' in result
    assert '[99]' not in prepare_answer('Explain','Invalid [99], valid [1]',1)

def test_limits_and_rl_default(setup,monkeypatch):
    monkeypatch.delenv('RL_MODE',raising=False)
    assert choose_strategy('Define Job Design') is None
    ctx=AgentRunContext(user_id='alice',course_id=setup.course,limits=Limits(models=1,tools=0))
    assert ctx.model(lambda:'ok')=='ok'
    with pytest.raises(HarnessError): ctx.model(lambda:'extra')
    with pytest.raises(HarnessError): ctx.tool_sync('search_course_documents',dict(course_id=setup.course,user_id='alice'),lambda:[])

def test_manual_credential_selection(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','synthetic-primary')
    monkeypatch.setenv('GROQ_REPLACEMENT_API_KEY','synthetic-replacement')
    monkeypatch.setenv('GROQ_CREDENTIAL','primary')
    assert load_groq_settings()[0]=='synthetic-primary'
    monkeypatch.setenv('GROQ_CREDENTIAL','replacement')
    assert load_groq_settings()[0]=='synthetic-replacement'

def test_real_sdk_429_mapping_no_rotation(setup, monkeypatch):
    import httpx
    import llm_service
    from groq import RateLimitError
    monkeypatch.setenv('GROQ_API_KEY','synthetic-primary')
    monkeypatch.setenv('GROQ_CREDENTIAL','primary')
    calls=[]
    def fail(**kwargs):
        calls.append(kwargs)
        raise RateLimitError('limited',response=httpx.Response(429,headers={'retry-after':'15'},request=httpx.Request('POST','https://api.groq.com')),body=None)
    monkeypatch.setattr(llm_service,'Groq',lambda **kwargs:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail))))
    with pytest.raises(LLMServiceError) as exc: generate_answer('Define Job Design',[EVIDENCE])
    assert exc.value.category=='rate_limit' and exc.value.retry_after==15 and len(calls)==1
    monkeypatch.setenv('GROQ_CREDENTIAL','replacement')
    monkeypatch.setenv('GROQ_REPLACEMENT_API_KEY','synthetic-replacement')
    with pytest.raises(LLMServiceError) as again: generate_answer('Define Job Design',[EVIDENCE])
    assert again.value.category=='rate_limit' and len(calls)==1


def test_explicit_question_is_not_implicit():
    assert retrieval_question('Why is Job Design important?',[]) == 'Why is Job Design important?'


def test_long_followup_chain_keeps_resolved_topic(setup):
    s=setup
    s.ask('Define Job Design','topic')
    for index in range(8):
        assert s.ask('in detail please','long'+str(index))['mode']=='generated'
    assert 'Job Design' in s.queries[-1][0]


def test_environment_limit(monkeypatch):
    monkeypatch.delenv('MAX_AI_QUESTIONS_PER_DAY',raising=False)
    assert api.daily_question_limit()==10
    monkeypatch.setenv('MAX_AI_QUESTIONS_PER_DAY','30')
    assert api.daily_question_limit()==30
    monkeypatch.setenv('MAX_AI_QUESTIONS_PER_DAY','0')
    assert api.daily_question_limit()==1


def test_server_created_session_retry(setup):
    s=setup
    result=s.ask('Define Job Design','server-session',None)
    count=len(s.queries)
    replay=s.ask('Define Job Design','server-session',result['session_id'])
    assert replay['answer']==result['answer'] and len(s.queries)==count


def test_retry_uses_original_context(setup,monkeypatch):
    s=setup
    s.ask('Define Job Design','topic')
    good=api.generate_answer
    def fail(*args): raise LLMServiceError('Timeout','provider_timeout')
    monkeypatch.setattr(api,'generate_answer',fail)
    s.ask('in detail please','old')
    monkeypatch.setattr(api,'generate_answer',good)
    s.ask('Define workplace ethics','newtopic')
    s.ask('in detail please','old')
    assert 'Job Design' in s.queries[-1][0] and 'workplace ethics' not in s.queries[-1][0]
    rows=load_history(s.session,s.course,'alice')
    assert rows[2]['text']=='in detail please' and rows[3]['role']=='generated'
    assert rows[4]['text']=='Define workplace ethics'


def test_harness_retains_provider_category(setup,monkeypatch):
    from backend import agent_harness as harness
    class Deadline:
        async def __aenter__(self): pass
        async def __aexit__(self,*args): pass
    monkeypatch.setattr(harness.asyncio,'timeout',lambda seconds:Deadline())
    async def invoke(state):
        state['run_context'].model(lambda: (_ for _ in ()).throw(LLMServiceError('limited','rate_limit',12)))
    graph=SimpleNamespace(ainvoke=invoke)
    ctx=AgentRunContext(user_id='alice',course_id=setup.course)
    result=immediate(harness.run_graph(graph,dict(user_id='alice',course_id=setup.course,question='Define Job Design'),ctx))
    assert result['error_category']=='rate_limit' and result['retry_after']==12
    assert ctx.model_calls==1 and result['retryable'] is True
