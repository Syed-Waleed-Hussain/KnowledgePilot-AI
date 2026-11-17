"""Run locally when asyncio is available. All provider/MCP results are mocked."""
import asyncio
import pytest
from backend import course_store
from backend.agent_harness import AgentRunContext, run_graph
from backend.phase4_graph import build_question_graph
from backend.rl_bandit import PolicyStore, extract_context, available_actions

@pytest.mark.parametrize('mode,expected_limit',[('off',6),('shadow',6),('active',3)])
def test_graph_modes_keep_filters_and_harness(tmp_path,monkeypatch,mode,expected_limit):
    store=PolicyStore(tmp_path/'synthetic.sqlite3');store.initialize()
    features=extract_context('What is a sensor?')
    for action in available_actions(features):
        for _ in range(5):store.update_policy(features,action,1 if action=='fast' else .2)
    store.mark_evaluated()
    monkeypatch.setenv('RL_MODE',mode)
    monkeypatch.setenv('RL_POLICY_PATH',str(store.path))
    monkeypatch.setattr(course_store,'course_exists',lambda c,u:c=='a' and u=='alice')
    calls=[]
    async def search(server,**kwargs):
        calls.append(kwargs)
        assert kwargs['user_id']=='alice' and kwargs['course_id']=='a'
        return [dict(source='synthetic.pdf',text='A sensor measures quantities.',page=1,similarity=.9)]
    monkeypatch.setattr('backend.phase4_graph.call_document_search',search)
    graph=build_question_graph(search_callback=lambda **k:[],follow_up_callback=lambda q,h:q,
        before_answer=lambda u:None,answer_callback=lambda *a:'A sensor measures quantities [1].')
    ctx=AgentRunContext('alice','a')
    state=dict(question='What is a sensor?',user_id='alice',course_id='a',history=[])
    result=asyncio.run(run_graph(graph,state,ctx))
    assert result['mode']=='generated'
    assert calls[0]['limit']==expected_limit
    assert ctx.tool_calls==ctx.model_calls==1
    assert store.save_policy()==15  # No real-interaction online updates.
    if mode=='shadow': assert ctx.retrieval_decision['executed_action'] is None

@pytest.mark.parametrize('owner,limit',[('bob',5),('alice',0)])
def test_rl_cannot_bypass_owner_or_budget(monkeypatch,owner,limit):
    monkeypatch.setenv('RL_MODE','active')
    monkeypatch.setattr(course_store,'course_exists',lambda c,u:c=='a' and u=='alice')
    calls=[]
    async def search(*args,**kwargs):calls.append(1);return []
    monkeypatch.setattr('backend.phase4_graph.call_document_search',search)
    graph=build_question_graph(search_callback=lambda **k:[],follow_up_callback=lambda q,h:q,
        before_answer=lambda u:pytest.fail('No quota should be reserved'),answer_callback=lambda *a:pytest.fail('No model call'))
    ctx=AgentRunContext(owner,'a');ctx.limits.tools=limit
    result=asyncio.run(run_graph(graph,dict(question='Q',user_id=owner,course_id='a'),ctx))
    assert result['mode']=='retrieval_only' and not calls
    assert ctx.model_calls==0
    assert ctx.error_category==('authorization' if owner=='bob' else 'budget')
