"""No network, models, real accounts, private PDFs, or asyncio needed."""
import random
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.rl_bandit import (ACTIONS, PolicyStore, available_actions, calculate_reward,
                               context_key, extract_context, select_action)
from backend.rl_retrieval import choose_strategy, retrieval_configuration, finish_decision
from backend.evaluate_phase6 import train, evaluate, CONTEXTS

@pytest.fixture
def store(tmp_path):
    result=PolicyStore(tmp_path/'synthetic.sqlite3');result.initialize();return result

C=dict(task_type='question',is_followup=True,query_length='short')

def ready(store,context=C):
    for action in available_actions(context):
        for _ in range(5):store.update_policy(context,action,1 if action=='context_aware' else .2)
    store.mark_evaluated()

@pytest.mark.parametrize('question,task',[('Explain sensors','question'),('Summarize lecture','summary'),('Create five MCQs','quiz'),('Compare and quiz','comparison')])
def test_features(question,task):
    result=extract_context(question)
    assert result['task_type']==task
    assert 'Explain' not in context_key(result)

def test_followup_and_length():
    assert extract_context('How does it work?',[{'role':'student','text':'private'}])['is_followup']
    assert not extract_context('How does it work?')['is_followup']
    assert extract_context('word '*13)['query_length']=='long'

def test_available_actions():
    assert set(available_actions(C))==set(ACTIONS)
    assert available_actions(dict(C,task_type='summary'))==['detailed','context_aware']
    assert available_actions(dict(C,task_type='comparison'))==[]
    assert available_actions(C,page=1)==[]

@pytest.mark.parametrize('bad',[dict(C,task_type='shell'),dict(C,owner='bob')])
def test_bad_context(bad):
    with pytest.raises(ValueError):context_key(bad)

def test_explore_and_exploit():
    values={'fast':{'q':.1},'detailed':{'q':.9},'context_aware':{'q':.2}}
    assert {select_action(values,list(ACTIONS),1,random.Random(n)) for n in range(60)}==set(ACTIONS)
    assert {select_action(values,list(ACTIONS),0,random.Random(n)) for n in range(20)}=={'detailed'}
    with pytest.raises(ValueError):select_action(values,['shell'])
    with pytest.raises(ValueError):select_action(values,list(ACTIONS),float('nan'))

@pytest.fixture
def metrics():return dict(success=True,citation_validity=True,evidence_available=True,task_completion=True,structured_output_validity=None)

def test_reward_formula(metrics):
    # N/A structure: divide remaining weighted score by 0.8.
    assert calculate_reward(metrics,duration_ms=30000,tool_calls=5,model_calls=2)==pytest.approx(.7/.8)
    assert calculate_reward(metrics,duration_ms=0)==1
    assert calculate_reward(dict(metrics,structured_output_validity=False))<calculate_reward(metrics)

@pytest.mark.parametrize('field',['success','citation_validity','evidence_available'])
def test_no_reward_invalid(metrics,field):
    assert calculate_reward(dict(metrics,**{field:False}))==0
    assert calculate_reward(metrics,authorized=False)==0

def test_actual_update_count_and_reload(store):
    assert store.update_policy(C,'fast',.8)==(.8,1)
    q,n=store.update_policy(C,'fast',.4)
    assert q==pytest.approx(.6) and n==2
    q,n=store.update_policy(C,'fast',1,alpha=.25)
    assert q==pytest.approx(.7) and n==3
    loaded=PolicyStore(store.path).load_policy(C)['fast']
    assert loaded['q']==pytest.approx(.7) and loaded['observations']==3
    assert loaded['updated_at'] and loaded['epsilon']==.1
    assert store.save_policy()==3

@pytest.mark.parametrize('action,reward',[('shell',.5),('fast',float('nan')),('fast',1.1),('fast',-.1)])
def test_reject_invalid_updates(store,action,reward):
    with pytest.raises(ValueError):store.update_policy(C,action,reward)
    assert store.save_policy()==0

def test_concurrent_updates(store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:store.update_policy(C,'fast',.6),range(20)))
    assert store.load_policy(C)['fast']['observations']==20
    assert store.load_policy(C)['fast']['q']==pytest.approx(.6)

def test_reproducible_training_and_fair_evaluation(store,tmp_path):
    other=PolicyStore(tmp_path/'other.sqlite3');other.initialize()
    train(store,300,13);train(other,300,13)
    assert store.save_policy()==other.save_policy()==300
    for context in CONTEXTS:
        a,b=store.load_policy(context),other.load_policy(context)
        assert {k:(v['q'],v['observations']) for k,v in a.items()}=={k:(v['q'],v['observations']) for k,v in b.items()}
    report=evaluate(store,200,1013)
    assert store.save_policy()==300
    for name in ('fixed_detailed','random','learned'):
        assert 0<=report[name]['average_simulated_reward']<=1
        assert sum(report[name]['action_frequency'].values())==200
        assert report[name]['evaluation_updates']==0
    assert report['fixed_detailed']['action_frequency']=={'detailed':200}

def test_off_preserves_existing_configuration(monkeypatch):
    monkeypatch.delenv('RL_MODE',raising=False)
    assert choose_strategy('Question') is None
    assert retrieval_configuration(None,'raw','existing contextual query')==('existing contextual query',6)

def test_shadow_does_not_execute_or_learn(store):
    ready(store)
    decision=choose_strategy('How does it work?',[{'role':'student'}],mode='shadow',store=store)
    assert decision['selected_action']=='context_aware' and decision['executed_action'] is None
    assert retrieval_configuration(decision,'raw','context')==('context',6)
    before=store.save_policy()
    assert 'reward_proxy' not in finish_decision(decision,{'success':True})
    assert store.save_policy()==before

def test_active_allowed_and_online_learning_disabled(store,metrics):
    ready(store)
    decision=choose_strategy('How does it work?',[{'role':'student'}],mode='active',store=store)
    assert retrieval_configuration(decision,'raw','resolved')==('resolved',5)
    before=store.save_policy()
    event=finish_decision(decision,metrics)
    assert event['policy_update']=='skipped' and event['reward_proxy']==1
    assert store.save_policy()==before
    assert choose_strategy('Compare lectures',mode='active',store=store)['executed_action'] is None
    assert choose_strategy('page 2',page=2,mode='active',store=store)['executed_action'] is None

def test_cold_and_corrupt_policy_fallback(store):
    assert choose_strategy('How does it work?',[{}],mode='active',store=store)['executed_action'] is None
    ready(store)
    with store.connect() as db:
        db.execute("UPDATE rl_values SET action='shell' WHERE action='fast'")
    decision=choose_strategy('How does it work?',[{}],mode='active',store=store)
    assert decision['executed_action'] is None and decision['reason']=='invalid_policy'

def test_policy_missing_fallback(tmp_path):
    decision=choose_strategy('Question',mode='active',store=PolicyStore(tmp_path/'absent.sqlite3'))
    assert decision['reason']=='policy_unavailable' and decision['executed_action'] is None
    assert not (tmp_path/'absent.sqlite3').exists()

def test_training_invalidates_evaluation(store):
    ready(store);assert store.evaluated()
    store.update_policy(C,'fast',.3)
    assert not store.evaluated()

def test_fast_and_detailed_config():
    assert retrieval_configuration({'executed_action':'fast'},'raw','resolved')==('raw',3)
    assert retrieval_configuration({'executed_action':'detailed'},'raw','resolved')==('raw',5)

def test_security_and_budget_remain_outside_policy(monkeypatch):
    from backend.agent_harness import AgentRunContext, HarnessError
    from backend import course_store
    monkeypatch.setattr(course_store,'course_exists',lambda c,u:c=='a' and u=='alice')
    ctx=AgentRunContext('alice','a')
    with pytest.raises(HarnessError):ctx.authorize('search_course_documents',dict(user_id='bob',course_id='a'))
    with pytest.raises(HarnessError):ctx.authorize('search_course_documents',dict(user_id='alice',course_id='b'))
    with pytest.raises(HarnessError):ctx.authorize('shell',dict(user_id='alice',course_id='a'))
    ctx.limits.tools=0
    with pytest.raises(HarnessError):ctx.charge('tool')
    assert ctx.tool_calls==ctx.model_calls==0
