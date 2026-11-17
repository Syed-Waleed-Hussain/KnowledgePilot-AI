import asyncio
import time
import pytest
from backend import course_store
from backend.agent_harness import AgentRunContext, HarnessError, Limits, bounded_context, run_graph
from backend.phase5_evaluation import evaluate_answer
from backend.evaluate_phase5 import evaluate_scenarios, mock_answer, PASSAGES

@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr(course_store,'course_exists',lambda c,u:c=='a' and u=='alice')
    return AgentRunContext('alice','a')

def test_tool_limit(ctx):
    async def exercise():
        for _ in range(5):
            assert await ctx.tool('search_course_documents',dict(user_id='alice',course_id='a'),lambda: asyncio.sleep(0,result=[]))==[]
        with pytest.raises(HarnessError,match='budget'):
            await ctx.tool('search_course_documents',dict(user_id='alice',course_id='a'),lambda: asyncio.sleep(0))
    asyncio.run(exercise())
    assert ctx.tool_calls==5

def test_model_limit(ctx):
    for _ in range(2): assert ctx.model(lambda:'ok')=='ok'
    with pytest.raises(HarnessError,match='budget'): ctx.model(lambda:'wrong')
    assert ctx.model_calls==2

@pytest.mark.parametrize('tool,user,course',[('shell','alice','a'),('search_course_documents','bob','a'),('search_course_documents','alice','b')])
def test_forbidden_never_executes_or_retries(ctx,tool,user,course):
    calls=[]
    async def execute(): calls.append(1)
    with pytest.raises(HarnessError):
        asyncio.run(ctx.tool(tool,dict(user_id=user,course_id=course),execute))
    assert not calls and ctx.tool_calls==0

def test_missing_auth(ctx):
    ctx.user_id=''
    with pytest.raises(HarnessError):ctx.authorize('search_course_documents',dict(user_id='',course_id='a'))

def test_transient_retry(ctx):
    calls=[]
    def model():
        calls.append(1)
        if len(calls)==1: raise ConnectionError('private data')
        return 'ok'
    assert ctx.model(model)=='ok'
    assert ctx.model_calls==2

def test_rate_limit_no_retry(ctx):
    def model(): raise RuntimeError('Groq rate limit reached secret')
    with pytest.raises(HarnessError,match='rate limit') as error:ctx.model(model)
    assert 'secret' not in str(error.value) and ctx.model_calls==1

def test_authorization_no_model_retry(ctx):
    def model(): raise HarnessError('authorization')
    with pytest.raises(HarnessError):ctx.model(model)
    assert ctx.model_calls==1

def test_context_bounded_latest_question():
    q='Latest question stays complete?'
    limits=Limits(context_chars=1000,passage_chars=300)
    history,passages=bounded_context(q,[dict(role='student',text='x'*10000)]*40,[dict(PASSAGES[0],text='z'*10000)]*30,limits)
    assert len(q)+sum(len(str(p)) for p in passages)+sum(len(str(h)) for h in history)<=limits.context_chars
    assert q=='Latest question stays complete?'
    assert len(history)<=8 and len(passages)<=6

def test_deadline(ctx):
    ctx.started-=31
    with pytest.raises(HarnessError,match='too long'):ctx.model(lambda:'wrong')
    assert ctx.model_calls==0

def test_async_timeout_and_safe_failure(ctx):
    class Graph:
        async def ainvoke(self,state):await asyncio.sleep(.1)
    ctx.limits.seconds=.01
    result=asyncio.run(run_graph(Graph(),dict(question='Q',user_id='alice',course_id='a'),ctx))
    assert result['reliability']['error_category']=='timeout'
    assert result['mode']=='retrieval_only'

def test_citations_and_metrics():
    result=evaluate_answer('Explain','Fact [1].',PASSAGES)
    assert result['passed'] and result['citation_validity']
    assert result['factual_accuracy_evaluated'] is False
    assert not evaluate_answer('Explain','Bad [99].',PASSAGES)['passed']
    assert not evaluate_answer('Explain','Fact [1].',[])['passed']

def test_quiz_structure_and_completion():
    answer=mock_answer('five MCQs',PASSAGES)
    assert evaluate_answer('Create five MCQs',answer,PASSAGES)['passed']
    assert not evaluate_answer('Create five MCQs',answer.replace('**Correct Answer:** A','**Correct Answer:** E',1),PASSAGES)['passed']
    assert not evaluate_answer('Compare and quiz',answer,PASSAGES)['passed']
    combined='## Part 1: Lecture Comparison\nFact [1].\n## Part 2: Quiz\n'+answer
    assert evaluate_answer('Compare and quiz',combined,PASSAGES)['passed']

def test_synthetic_runner():
    rows=asyncio.run(evaluate_scenarios())
    assert len(rows)==10
    assert all(r['passed'] for r in rows),rows

def test_quota_reservation_is_idempotent(tmp_path, monkeypatch):
    from backend.app import reserve_daily_question
    monkeypatch.setattr(course_store,'DATABASE_PATH',tmp_path/'quota.sqlite3')
    course_store.initialize_database()
    reserve_daily_question('alice','same-request','question-hash')
    reserve_daily_question('alice','same-request','question-hash')
    with course_store.connect() as db:
        assert db.execute('SELECT question_count FROM daily_usage').fetchone()[0]==1
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        reserve_daily_question('alice','same-request','changed-question')
    assert error.value.status_code==409

def test_tool_transient_retry_and_safe_error(ctx):
    calls=[]
    async def execute():
        calls.append(1)
        if len(calls)==1:raise ConnectionError('private.pdf secret')
        return PASSAGES
    result=asyncio.run(ctx.tool('search_course_documents',dict(user_id='alice',course_id='a'),execute))
    assert result==PASSAGES and ctx.tool_calls==2
    assert 'private.pdf' not in str(ctx.trace) and 'secret' not in str(ctx.trace)

def test_invalid_quiz_fields():
    from backend.answer_quality import render_quiz
    base=dict(question='Q',options=dict(A='One',B='Two',C='Three',D='Four'),correct_answer='A',explanation='Evidence',source_ids=[1])
    for field,value in [('options',{'A':'One'}),('correct_answer','AB'),('explanation',''),('source_ids',[9])]:
        with pytest.raises(ValueError):render_quiz({'questions':[dict(base,**{field:value})]},1,expected_count=1)
