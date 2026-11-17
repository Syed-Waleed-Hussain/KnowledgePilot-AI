"""CPU-only synthetic experiment; assumptions here are not educational benchmarks."""
import argparse
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path
from backend.rl_bandit import PolicyStore, available_actions, calculate_reward, context_key, select_action

EXPERIMENT_ROOT = Path(__file__).resolve().parent / '.phase6_experiments'
CONTEXTS = [dict(task_type=task,is_followup=follow,query_length=length)
            for task in ('question','summary','quiz') for follow in (False,True) for length in ('short','long')]

def synthetic_outcome(context, action, quality_draw):
    """Known artificial distributions; no retrieval, PDF, Groq, or private data."""
    if action not in available_actions(context): raise ValueError('Unsafe action')
    if context['is_followup']:
        quality = .94 if action=='context_aware' else .40
    elif context['query_length']=='long' or context['task_type']=='quiz':
        quality = .92 if action!='fast' else .48
    else:
        quality = .94
    success = quality_draw < quality
    metrics=dict(success=success,evidence_available=True,citation_validity=success,
                 task_completion=success,structured_output_validity=success if context['task_type']=='quiz' else None)
    duration={'fast':1000,'detailed':2000,'context_aware':2300}[action]
    return calculate_reward(metrics,duration_ms=duration,tool_calls=1,model_calls=1)

def train(store, episodes=1200, seed=7, epsilon=.2, alpha=None):
    rng=random.Random(seed)
    for _ in range(episodes):
        context=rng.choice(CONTEXTS)
        values=store.load_policy(context)
        action=select_action(values,available_actions(context),epsilon,rng)
        reward=synthetic_outcome(context,action,rng.random())
        store.update_policy(context,action,reward,epsilon=epsilon,alpha=alpha)
    return store.save_policy()

def evaluate(store, cases=1200, seed=1007):
    rng=random.Random(seed)
    heldout=[(rng.choice(CONTEXTS),rng.random()) for _ in range(cases)]
    report={}
    # No updates in this loop; all three policies see the same contexts/draws.
    for name in ('fixed_detailed','random','learned'):
        started=time.perf_counter()
        selections=Counter(); rewards=[]; per_context=defaultdict(list)
        policy_rng=random.Random(seed+1)
        for context,draw in heldout:
            allowed=available_actions(context)
            if name=='fixed_detailed': action='detailed'
            elif name=='random': action=policy_rng.choice(allowed)
            else: action=select_action(store.load_policy(context),allowed,0,policy_rng)
            reward=synthetic_outcome(context,action,draw)
            rewards.append(reward);selections[action]+=1;per_context[context_key(context)].append(reward)
        report[name]=dict(average_simulated_reward=sum(rewards)/len(rewards),
            action_frequency=dict(selections),reward_per_context={k:sum(v)/len(v) for k,v in sorted(per_context.items())},
            duration_seconds=time.perf_counter()-started,exploration_rate=0 if name!='random' else 1,
            evaluation_updates=0)
    learned=report['learned']['average_simulated_reward']
    report['comparison']=dict(outperformed_fixed=learned>report['fixed_detailed']['average_simulated_reward'],
        outperformed_random=learned>report['random']['average_simulated_reward'])
    return report

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reset',action='store_true',help='Clear ONLY this synthetic experiment policy')
    parser.add_argument('--evaluate-only',action='store_true')
    parser.add_argument('--episodes',type=int,default=1200)
    parser.add_argument('--cases',type=int,default=1200)
    parser.add_argument('--seed',type=int,default=7)
    parser.add_argument('--epsilon',type=float,default=.2)
    args=parser.parse_args(argv)
    if not 1<=args.episodes<=100000 or not 1<=args.cases<=100000 or not 0<=args.epsilon<=1:
        parser.error('Episodes/cases must be 1..100000; epsilon must be 0..1')
    if args.reset and args.evaluate_only: parser.error('Reset cannot be combined with evaluate-only')
    store=PolicyStore(EXPERIMENT_ROOT/'synthetic.sqlite3')
    if args.evaluate_only and not store.path.exists(): parser.error('Train a synthetic policy first')
    store.initialize()
    if args.reset:
        with store.connect() as db:
            db.execute('DELETE FROM rl_values');db.execute('DELETE FROM rl_metadata')
    started=time.perf_counter()
    if not args.evaluate_only: train(store,args.episodes,args.seed,args.epsilon)
    training_seconds=time.perf_counter()-started
    updates=store.save_policy()
    report=evaluate(store,args.cases,args.seed+1000)
    if report['comparison']['outperformed_fixed']: store.mark_evaluated()
    payload=dict(label='SYNTHETIC ONLY; not factual accuracy',seed=args.seed,evaluation_seed=args.seed+1000,
                 episodes_this_run=0 if args.evaluate_only else args.episodes,observations=updates,
                 training_epsilon=args.epsilon,training_seconds=training_seconds,results=report)
    (EXPERIMENT_ROOT/'latest_metrics.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print('SYNTHETIC ONLY: no claims about real student answer quality')
    print(f"{'Policy':18} {'Mean reward':>12} {'Eval updates':>13} {'Seconds':>10}")
    for name in ('fixed_detailed','random','learned'):
        row=report[name]
        print(f"{name:18} {row['average_simulated_reward']:12.4f} {row['evaluation_updates']:13} {row['duration_seconds']:10.3f}")
    print(f'Observations: {updates}; training epsilon: {args.epsilon}; training seconds: {training_seconds:.3f}')
    print('Comparison:',report['comparison'])
    print('Action frequencies:',{k:report[k]['action_frequency'] for k in ('fixed_detailed','random','learned')})
    print('Metrics:',EXPERIMENT_ROOT/'latest_metrics.json')
    return 0

if __name__=='__main__':raise SystemExit(main())
