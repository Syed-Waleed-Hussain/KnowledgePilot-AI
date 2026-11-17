"""Synthetic, offline scenarios. No real PDFs, accounts, or provider calls."""
import asyncio
import json
import tempfile
from pathlib import Path
from backend import course_store
from backend.agent_harness import AgentRunContext, run_graph
from backend.phase4_graph import build_question_graph
from backend.answer_quality import render_quiz
from backend.chat_memory import retrieval_question

SCENARIOS = [
    ('Basic QA','What is a sensor?', 'ok'),
    ('Follow-up','How does it work?', 'ok'),
    ('Summary','Summarize the lecture.', 'ok'),
    ('Five MCQs','Create five MCQs.', 'ok'),
    ('Comparison','Compare both lectures.', 'ok'),
    ('Comparison + quiz','Compare both lectures and generate a quiz.', 'ok'),
    ('Missing document','Explain missing lecture.', 'empty'),
    ('Invalid course','Explain sensors.', 'invalid'),
    ('Cross-student','Explain sensors.', 'cross'),
    ('Provider failure','Explain sensors.', 'failure'),
]
PASSAGES = [dict(source=name, page=1, similarity=.9, text=text) for name,text in [
    ('synthetic-sensors.pdf','A sensor measures a physical quantity.'),
    ('synthetic-control.pdf','A controller uses feedback to adjust an actuator.')]]

def mock_answer(prompt, evidence, history=None):
    if 'MCQ' in prompt or 'quiz' in prompt.lower():
        return render_quiz(dict(questions=[dict(question=f'Synthetic concept {i}?',
            options=dict(A='Sensor',B='Controller',C='Actuator',D='Display'),
            correct_answer='A', explanation='Sensors measure physical quantities.', source_ids=[1]) for i in range(5)]),len(evidence))
    return 'The sensor measures a physical quantity [1].'

async def evaluate_scenarios():
    rows = []
    original = course_store.DATABASE_PATH
    with tempfile.TemporaryDirectory() as folder:
        course_store.DATABASE_PATH = Path(folder)/'synthetic.sqlite3'
        try:
            course_store.initialize_database()
            with course_store.connect() as db:
                db.executemany('INSERT INTO courses (course_id,user_id,name) VALUES (?,?,?)', [('a','alice','Synthetic A'),('b','bob','Synthetic B')])
            for name,question,kind in SCENARIOS:
                search_calls = []
                def search(**kwargs):
                    search_calls.append(kwargs)
                    return [] if kind=='empty' else PASSAGES
                def model(*args):
                    if kind=='failure': raise ConnectionError('synthetic outage')
                    return mock_answer(*args)
                graph = build_question_graph(search_callback=search, follow_up_callback=retrieval_question,
                    before_answer=lambda u:None, answer_callback=model)
                course = 'missing' if kind=='invalid' else 'b' if kind=='cross' else 'a'
                ctx = AgentRunContext('alice',course)
                result = await run_graph(graph,dict(question=question,user_id='alice',course_id=course,
                    history=[dict(role='student',text='Explain sensors.')] if name=='Follow-up' else []),ctx)
                expected = 'succeeded' if kind=='ok' else 'failed'
                passed = ctx.status==expected
                if kind in ('cross','invalid'): passed &= ctx.tool_calls==ctx.model_calls==0
                if kind=='empty': passed &= ctx.model_calls==0
                if name=='Follow-up': passed &= bool(search_calls) and 'Explain sensors.' in search_calls[0]['query']
                if kind=='failure': passed &= ctx.model_calls==2
                rows.append(dict(scenario=name,passed=passed,duration_ms=ctx.summary()['duration_ms'],
                    tool_calls=ctx.tool_calls,model_calls=ctx.model_calls,
                    citation_validity=result.get('evaluation',{}).get('citation_validity')))
        finally:
            course_store.DATABASE_PATH = original
    return rows

def main():
    rows=asyncio.run(evaluate_scenarios())
    print(f"{'Scenario':24} {'Result':6} {'ms':>9} {'Tools':>5} {'Models':>6} {'Citations':>9}")
    for row in rows:
        print(f"{row['scenario']:24} {'PASS' if row['passed'] else 'FAIL':6} {row['duration_ms']:9.2f} {row['tool_calls']:5} {row['model_calls']:6} {str(row['citation_validity']):>9}")
    return 0 if all(r['passed'] for r in rows) else 1

if __name__=='__main__': raise SystemExit(main())
