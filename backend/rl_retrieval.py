"""Optional retrieval decisions only. Real-interaction learning is deliberately disabled."""
import os
import random
import sqlite3
from backend.rl_bandit import ACTIONS, PolicyStore, available_actions, calculate_reward, extract_context, select_action

def choose_strategy(question, history=(), page=None, *, mode=None, store=None):
    mode = os.getenv('RL_MODE','off') if mode is None else mode
    if mode not in ('shadow','active'): return None
    features=extract_context(question,history)
    allowed=available_actions(features,page=page)
    decision=dict(policy='contextual_epsilon_greedy', mode=mode, selected_action=None,
                  executed_action=None, policy_update='skipped', reason='task_specific', features=features)
    if not allowed: return decision
    try:
        store=store or PolicyStore(os.getenv('RL_POLICY_PATH') or None)
        if not store.path.is_file():
            decision['reason']='policy_unavailable'
            return decision
        values=store.load_policy(features)
        minimum=max(1,int(os.getenv('RL_MIN_OBSERVATIONS','5')))
        if not store.evaluated() or any(values.get(a,{}).get('observations',0)<minimum for a in allowed):
            decision['reason']='policy_uncertain'
            return decision
        # Student requests exploit only. Exploration is confined to offline training.
        selected=select_action(values,allowed,epsilon=0,rng=random.Random(0))
        decision.update(selected_action=selected, reason='evaluated_synthetic_policy')
        if mode=='active': decision['executed_action']=selected
    except (sqlite3.Error,ValueError,TypeError,OverflowError,OSError):
        decision['reason']='invalid_policy'
    return decision

def retrieval_configuration(decision, question, contextual_query):
    action=(decision or {}).get('executed_action')
    if action not in ACTIONS: return contextual_query,6
    return (contextual_query if action=='context_aware' else question),ACTIONS[action]

def finish_decision(decision, metrics):
    """Do not credit a shadow alternative for an outcome it did not produce."""
    if not decision: return None
    event=dict(step='rl.outcome',policy=decision['policy'],mode=decision['mode'],
               selected_action=decision['selected_action'],executed_action=decision['executed_action'],
               policy_update='skipped',reason='online_learning_disabled')
    if decision['mode']=='active' and decision['executed_action']:
        event['reward_proxy']=calculate_reward(metrics,duration_ms=metrics.get('duration_ms',0),
            tool_calls=metrics.get('tool_calls',0),model_calls=metrics.get('model_calls',0))
    return event
