"""Focused Task 4 checks with synthetic SQLite, mocked MCP and mocked Groq.

No live provider tokens or network sockets are used.
"""

import asyncio
import inspect
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend import app as api
from backend import course_store, phase4_graph
from backend import infographic as info
from backend.agent_harness import AgentRunContext, HarnessError, run_graph
from backend.chat_memory import load_history
from backend.infographic import (
    InvalidInfographic,
    detect_infographic_intent,
    extract_topic,
    infer_layout,
    validate_infographic,
)
from backend.supabase_auth import get_current_user

EVIDENCE = dict(text='Job Design defines tasks, responsibilities and relationships. Job rotation develops skills.',
                source='Lecture13.pdf', page=4, similarity=.9)
EVIDENCE_2 = dict(text='Job enrichment adds responsibility and autonomy to a role.',
                  source='Lecture13.pdf', page=5, similarity=.88)

OVERVIEW = {
    'title': 'Job Design Essentials',
    'layout': 'overview',
    'introduction': 'Job design defines tasks, responsibilities and relationships in a role.',
    'sections': [
        {'heading': 'Task scope', 'body': 'Job design specifies the tasks and responsibilities of a role.', 'icon': 'target',
         'definition': 'The process of organising work.', 'example': 'A production team rotates tasks.'},
        {'heading': 'Skill variety', 'body': 'Job rotation develops employee skills across different tasks.', 'icon': 'refresh'},
    ],
    'steps': [], 'columns': [], 'similarities': [], 'differences': [],
    'takeaways': ['Job design shapes responsibilities.', 'Rotation builds skills.'],
    'source_ids': [1],
}
PROCESS = {
    'title': 'Grounded RAG Flow',
    'layout': 'process',
    'introduction': 'A retrieval-augmented generation pipeline retrieves evidence before answering.',
    'sections': [],
    'steps': [
        {'title': 'Prepare the question', 'detail': 'The student question is normalised for retrieval.', 'icon': 'settings'},
        {'title': 'Retrieve evidence', 'detail': 'Course PDF passages are filtered by owner and course.', 'icon': 'search'},
        {'title': 'Generate the answer', 'detail': 'The model answers only from the retrieved evidence.', 'icon': 'sparkles'},
    ],
    'columns': [], 'similarities': [], 'differences': [],
    'takeaways': ['Retrieval happens before generation.', 'Evidence stays course-scoped.'],
    'source_ids': [1, 2],
}
COMPARISON = {
    'title': 'Job Rotation vs Job Enlargement',
    'layout': 'comparison',
    'introduction': 'Job rotation and job enlargement change work in different ways.',
    'sections': [],
    'steps': [],
    'columns': [
        {'title': 'Job rotation', 'points': ['Moves between tasks', 'Builds broad skills']},
        {'title': 'Job enlargement', 'points': ['Adds related tasks', 'Increases task variety']},
    ],
    'similarities': ['Both change task scope.', 'Both aim to improve motivation.'],
    'differences': ['Rotation changes roles.', 'Enlargement adds tasks.'],
    'takeaways': ['Rotation builds breadth.', 'Enlargement adds depth.'],
    'source_ids': [1, 2],
}


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


class FakeCompletions:
    def __init__(self, state): self.state = state
    def create(self, **kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.state['response']))])


class FakeGroq:
    def __init__(self, state): self.chat = SimpleNamespace(completions=FakeCompletions(state))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(course_store, 'DATABASE_PATH', tmp_path / 'courses.sqlite3')
    course_store.initialize_database()
    alice, bob = dict(id='alice'), dict(id='bob')
    course = api.create_course(api.CourseInput(name='PPIT'), alice)['course_id']
    session = api.create_chat(course, alice)['session_id']
    bob_course = api.create_course(api.CourseInput(name='Bob Course'), bob)['course_id']
    bob_session = api.create_chat(bob_course, bob)['session_id']
    with course_store.connect() as db:
        for document_id, user_id, course_id, filename in (
            ('doc-alice', 'alice', course, 'Lecture13.pdf'),
            ('doc-bob', 'bob', bob_course, 'BobLecture.pdf'),
        ):
            db.execute(
                'INSERT INTO documents(document_id,user_id,course_id,filename,file_hash,stored_path,page_count,chunk_count,status) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                (document_id, user_id, course_id, filename, 'synthetic-' + document_id, document_id + '.pdf', 2, 2, 'indexed'),
            )

    queries = []
    monkeypatch.setattr(api, 'get_collection', lambda: SimpleNamespace(count=lambda: 2))
    monkeypatch.setattr(api, 'get_model', lambda: None)

    def search(*args, **kwargs):
        queries.append(args[1] if len(args) > 1 else kwargs.get('query'))
        return [dict(EVIDENCE), dict(EVIDENCE_2)]

    monkeypatch.setattr(api, 'search_relevant_chunks', search)
    monkeypatch.setattr(phase4_graph, 'StateGraph', Nodes)

    async def transport(server, trace, **kwargs):
        return server(**kwargs)

    monkeypatch.setattr(phase4_graph, 'build_document_server', lambda callback, **kwargs: callback)
    monkeypatch.setattr(phase4_graph, 'call_document_search', transport)

    async def run(graph, state, ctx, *, evaluate_answer_quality=True):
        ctx.authorize('search_course_documents', state)
        state['run_context'] = ctx
        try:
            for node in ('prepare', 'retrieve', 'generate'):
                update = graph.nodes[node](state)
                state.update(await update if inspect.isawaitable(update) else update)
        except HarnessError as error:
            state.update(answer='', mode='retrieval_only', error=str(error), error_category=error.category)
        state['retryable'] = state.get('error_category') in (
            'rate_limit', 'provider_timeout', 'provider_connection', 'provider_server', 'mcp',
            'invalid_infographic', 'validation',
        )
        state['evaluation'] = {'passed': state.get('mode') == 'generated', 'failure_reasons': []}
        return state

    monkeypatch.setattr(api, 'run_graph', run)
    monkeypatch.setattr(api, 'generate_answer', lambda question, passages, history=None: 'Job design defines responsibilities [1].')

    state = {'response': json.dumps(OVERVIEW)}
    monkeypatch.setattr(info, '_groq_client', lambda: (FakeGroq(state), 'test-model'))

    def ask(text, key, chat=None, user=None):
        return immediate(api.ask_question(api.QuestionRequest(
            course_id=course, session_id=chat or session, question=text, request_id=key), user or alice))

    def ask_info(text, key, chat=None, user=None):
        return immediate(api.generate_infographic_route(api.QuestionRequest(
            course_id=course, session_id=chat or session, question=text, request_id=key), user or alice))

    def set_response(payload):
        state['response'] = payload if isinstance(payload, str) else json.dumps(payload)

    return SimpleNamespace(user=alice, course=course, session=session, bob=bob,
                           bob_course=bob_course, bob_session=bob_session,
                           queries=queries, ask=ask, ask_info=ask_info, set_response=set_response)


def test_intent_detection_and_layout_inference():
    assert detect_infographic_intent('Make an infographic about Job Design.')
    assert detect_infographic_intent('Explain KV Cache visually.')
    assert detect_infographic_intent('Show the process of retrieval-augmented generation as an infographic.')
    assert detect_infographic_intent('Compare job rotation and job enlargement visually.')
    assert not detect_infographic_intent('Explain Job Design.')
    assert not detect_infographic_intent('What is visual perception?')
    assert infer_layout('Make an infographic about Job Design.') == 'overview'
    assert infer_layout('Show the process of RAG as an infographic.') == 'process'
    assert infer_layout('Compare job rotation and job enlargement visually.') == 'comparison'
    assert extract_topic('Make an infographic about Job Design.') == 'Job Design'
    assert extract_topic('Explain KV Cache visually.') == 'KV Cache'
    assert extract_topic('Create an infographic of Lecture 13.') == 'Lecture 13'


def test_overview_layout_generation_and_restoration(setup):
    setup.set_response(OVERVIEW)
    result = setup.ask_info('Make an infographic about Job Design.', 'overview-1')
    assert result['mode'] == 'generated'
    assert result['output'] == 'infographic'
    assert result['infographic']['layout'] == 'overview'
    assert [section['heading'] for section in result['infographic']['sections']] == ['Task scope', 'Skill variety']

    history = load_history(setup.session, setup.course, setup.user['id'], 20)
    saved = [message for message in history if message['role'] == 'infographic']
    assert saved and saved[-1]['infographic']['title'] == 'Job Design Essentials'
    assert json.loads(saved[-1]['text'])['layout'] == 'overview'
    assert saved[-1]['sources'][0]['filename'] == 'Lecture13.pdf'

    refreshed = api.get_chat_history(setup.course, setup.user, setup.session)
    restored = [message for message in refreshed['messages'] if message['role'] == 'infographic']
    assert restored and restored[0]['infographic']['introduction'].startswith('Job design defines')


def test_process_layout_generation_through_chat_ask(setup):
    setup.set_response(PROCESS)
    result = setup.ask('Show the process of retrieval-augmented generation as an infographic.', 'process-1')
    assert result['mode'] == 'generated'
    assert result['output'] == 'infographic'
    assert result['infographic']['layout'] == 'process'
    assert [step['title'] for step in result['infographic']['steps']] == [
        'Prepare the question', 'Retrieve evidence', 'Generate the answer',
    ]
    assert any('retrieval-augmented generation' in str(query).lower() for query in setup.queries)


def test_comparison_layout_generation(setup):
    setup.set_response(COMPARISON)
    result = setup.ask('Compare job rotation, job enlargement and job enrichment visually.', 'compare-1')
    assert result['infographic']['layout'] == 'comparison'
    assert len(result['infographic']['columns']) == 2
    assert result['infographic']['similarities']
    assert result['infographic']['differences']


def test_valid_structured_output_and_source_ids():
    document = validate_infographic(OVERVIEW, 2, 'overview')
    assert document['source_ids'] == [1]
    document = validate_infographic(PROCESS, 2, 'process')
    assert document['source_ids'] == [1, 2]


def test_invalid_structured_output_and_source_ids_rejected():
    broken = dict(OVERVIEW, sections=[{'heading': 'Only one card', 'body': 'This overview has one card.'}])
    with pytest.raises(InvalidInfographic):
        validate_infographic(broken, 2, 'overview')
    with pytest.raises(InvalidInfographic):
        validate_infographic(dict(OVERVIEW, source_ids=[3]), 2, 'overview')
    with pytest.raises(InvalidInfographic):
        validate_infographic(dict(OVERVIEW, source_ids=[0]), 2, 'overview')
    with pytest.raises(InvalidInfographic):
        validate_infographic(dict(OVERVIEW, source_ids=['one']), 2, 'overview')
    with pytest.raises(InvalidInfographic):
        validate_infographic(dict(OVERVIEW, sections=[
            {'heading': 'Script card', 'body': '<script>alert(1)</script>', 'icon': 'target'},
            {'heading': 'Other', 'body': 'A sufficiently long body for the second card.'},
        ]), 2, 'overview')


def test_invalid_model_output_is_reported_without_saving_an_infographic(setup):
    setup.set_response('this is not json')
    result = setup.ask_info('Make an infographic about Job Design.', 'invalid-1')
    assert result['success'] is False
    assert result['error_category'] == 'invalid_infographic'
    assert result.get('infographic') is None
    history = load_history(setup.session, setup.course, setup.user['id'], 20)
    assert not [message for message in history if message['role'] == 'infographic']


def test_course_ownership_and_cross_student_isolation(setup):
    setup.set_response(OVERVIEW)
    setup.ask_info('Make an infographic about Job Design.', 'alice-private')
    with pytest.raises(HTTPException) as error:
        setup.ask_info('Make an infographic about Job Design.', 'bob-denied', chat=setup.bob_session, user=setup.bob)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        load_history(setup.session, setup.course, setup.bob['id'])
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        api.get_chat_history(setup.course, setup.bob, setup.session)
    assert error.value.status_code == 404

    bob_history = load_history(setup.bob_session, setup.bob_course, setup.bob['id'], 20)
    assert not [message for message in bob_history if message['role'] == 'infographic']
    bob_chat = api.get_chat_history(setup.bob_course, setup.bob)
    assert all(message['role'] != 'infographic' for message in bob_chat['messages'])


def test_context_aware_follow_up(setup):
    setup.set_response(OVERVIEW)
    setup.ask('Explain Job Design in detail.', 'topic-1')
    setup.queries.clear()
    result = setup.ask_info('Make an infographic about it.', 'follow-up-1')
    assert result['mode'] == 'generated'
    assert result['infographic']['layout'] == 'overview'
    assert any('Job Design' in str(query) for query in setup.queries)


def test_normal_chat_still_works(setup):
    result = setup.ask('Explain job design.', 'normal-1')
    assert result['mode'] == 'generated'
    assert result['answer'].startswith('Job design defines responsibilities')
    assert result.get('infographic') is None
    history = load_history(setup.session, setup.course, setup.user['id'], 20)
    assert [message for message in history if message['role'] == 'generated']


def _route_paths(routes):
    """Collect real paths, including routers FastAPI keeps lazily included."""
    paths = set()
    for route in routes:
        path = getattr(route, 'path', None)
        if path:
            paths.add(path)
        original = getattr(route, 'original_router', None)
        if original is not None:
            paths |= _route_paths(getattr(original, 'routes', []))
    return paths


def test_research_environment_and_routes_remain_registered():
    paths = _route_paths(api.app.routes)
    assert '/chat/ask' in paths
    assert '/chat/infographic' in paths
    assert '/research/topics' in paths
    assert '/research/discover' in paths
    route = next(route for route in api.app.routes if getattr(route, 'path', '') == '/chat/infographic')
    assert any(dependency.call is get_current_user for dependency in route.dependant.dependencies)


def test_structured_infographic_can_skip_markdown_quality_evaluation(setup):
    class FakeGraph:
        async def ainvoke(self, state):
            return {'answer': json.dumps({'title': 'Structured output'}), 'mode': 'generated', 'passages': [EVIDENCE]}

    async def exercise(evaluate):
        context = AgentRunContext(user_id='alice', course_id=setup.course)
        state = {'question': 'Make an infographic.', 'history': [],
                 'user_id': 'alice', 'course_id': setup.course}
        return await run_graph(FakeGraph(), state, context, evaluate_answer_quality=evaluate)

    structured = asyncio.run(exercise(False))
    assert structured['mode'] == 'generated'
    assert structured['evaluation']['passed'] is True
    legacy = asyncio.run(exercise(True))
    assert legacy['mode'] == 'retrieval_only'
    assert legacy['error_category'] == 'validation'
