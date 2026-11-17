"""Pure output checks and real local MCP/graph integration checks."""
import asyncio
import json
import pytest
from backend.answer_quality import prepare_answer, render_quiz
from backend import course_store
from backend.mcp_tools import build_document_server, call_document_search
from backend.phase4_graph import build_question_graph


def quiz():
    return {'questions': [dict(question=f'Concept {n}?', options=dict(A='First', B='Second', C='Third', D='Fourth'), correct_answer='B', explanation='Supported by lecture.', source_ids=[1]) for n in range(5)]}


def test_structured_quiz():
    text = render_quiz(quiz(), 2)
    assert text.count('**Correct Answer:**') == 5
    assert text.count('**Explanation:**') == 5
    assert 'Not provided' not in text


@pytest.mark.parametrize('field,value', [('correct_answer', None), ('correct_answer', 'E'), ('explanation', ''), ('source_ids', [9]), ('options', {'A': 'one'})])
def test_invalid_quiz(field, value):
    data = quiz()
    data['questions'][0][field] = value
    with pytest.raises(ValueError):
        render_quiz(data, 2)


def test_legacy_inline_labels():
    raw = '### Question 1\n**Which lecture introduces the harness?** **Answer:** B **Explanation:** The harness manages context[2].\n- **A.** CLMs\n- **B.** Harness\n- **C.** Both\n- **D.** Neither **Answer:** Not provided by the model. **Explanation:** Not provided by the model.'
    text = prepare_answer('Generate a quiz', raw, 2)
    assert text.count('**Correct Answer:**') == 1
    assert text.count('**Explanation:**') == 1
    assert '**Correct Answer:** B' in text
    assert 'Not provided' not in text


def test_real_protocol_and_combined_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(course_store, 'DATABASE_PATH', tmp_path / 'courses.sqlite3')
    course_store.initialize_database()
    with course_store.connect() as db:
        db.execute('INSERT INTO courses (course_id,user_id,name) VALUES (?,?,?)', ('a', 'alice', 'Course A'))
        db.execute('INSERT INTO courses (course_id,user_id,name) VALUES (?,?,?)', ('b', 'bob', 'Course B'))
    passages = [dict(source=name, page=1, text='Temporary evidence', similarity=.9) for name in ['first.pdf', 'second.pdf']]
    calls = []
    def search(**kwargs):
        calls.append(kwargs)
        return passages
    server = build_document_server(search, trusted_user_id="alice")
    async def exercise():
        trace = []
        assert await call_document_search(server, query='compare', course_id='a', user_id='alice', trace=trace) == passages
        assert [e['step'] for e in trace] == ['mcp.tool_discovery', 'mcp.search_course_documents']
        with pytest.raises(Exception):
            await call_document_search(server, query='private', course_id='b', user_id='alice')
        assert len(calls) == 1
        def model(prompt, evidence, history=None):
            assert evidence == passages
            return render_quiz(quiz(), 2) if 'MCQs' in prompt else '| Main concepts | First | Second |\n|---|---|---|\n| Concept | One [1] | Two [2] |'
        graph = build_question_graph(search_callback=search, follow_up_callback=lambda q,h:q, before_answer=lambda u:None, answer_callback=model)
        result = await graph.ainvoke(dict(question='Compare the two lectures and generate a quiz.', course_id='a', user_id='alice', history=[]))
        assert result['mcp_used'] and not result['fallback_used']
        assert 'Part 1: Lecture Comparison' in result['answer']
        assert 'Part 2: Quiz' in result['answer']
        assert result['answer'].count('**Correct Answer:**') == 5
        assert [e['step'] for e in result['trace']] == ['node.prepare', 'mcp.tool_discovery', 'mcp.search_course_documents', 'node.retrieve', 'node.compare', 'node.generate_quiz', 'node.generate']
        print(json.dumps(result['trace']))
    asyncio.run(asyncio.wait_for(exercise(), timeout=30))

def test_mcp_identity_boundary(tmp_path, monkeypatch):
    from mcp import Client
    monkeypatch.setattr(course_store, 'DATABASE_PATH', tmp_path / 'private.sqlite3')
    course_store.initialize_database()
    with course_store.connect() as db:
        db.executemany('INSERT INTO courses (course_id,user_id,name) VALUES (?,?,?)', [('a', 'alice', 'A'), ('b', 'bob', 'B')])
    calls = []
    def search(**kwargs):
        calls.append(kwargs)
        return [dict(source=kwargs['user_id'] + '-private.pdf', text='private passage', document_id='private-id', page=1)]
    async def exercise():
        for owner, course, other_course, other_user in [('alice', 'a', 'b', 'bob'), ('bob', 'b', 'a', 'alice')]:
            server = build_document_server(search, trusted_user_id=owner)
            async with Client(server, mode='legacy', read_timeout_seconds=10) as client:
                assert 'search_course_documents' in {t.name for t in (await client.list_tools()).tools}
                allowed = await client.call_tool('search_course_documents', dict(query='topic', course_id=course, user_id=owner))
                assert not allowed.is_error
                assert json.loads(allowed.content[0].text)[0]['source'] == owner + '-private.pdf'
                for target, supplied_user in [(other_course, owner), (other_course, other_user), ('missing', owner)]:
                    before = len(calls)
                    denied = await client.call_tool('search_course_documents', dict(query='topic', course_id=target, user_id=supplied_user))
                    assert denied.is_error is True
                    assert len(denied.content) == 1
                    assert denied.content[0].text in ("Course unavailable or access denied.", "Error executing tool search_course_documents: Course unavailable or access denied.")
                    assert denied.model_dump(by_alias=True).get('structuredContent') is None
                    payload = denied.model_dump_json()
                    for secret in ['private.pdf', 'private passage', 'private-id', str(tmp_path), 'Traceback', 'GROQ_API_KEY', 'SUPABASE_ACCESS_TOKEN', 'password']:
                        assert secret not in payload
                    assert len(calls) == before
        assert len(calls) == 2
    asyncio.run(asyncio.wait_for(exercise(), 30))
