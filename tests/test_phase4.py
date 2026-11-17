"""Focused Phase 4 protocol, isolation, workflow, and answer-quality checks."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from mcp import Client

from backend import course_store
from backend.answer_quality import normalize_citations, prepare_answer
from backend.mcp_tools import build_document_server, call_document_search
from backend.phase4_graph import build_question_graph
from backend.supabase_auth import get_current_user


SOURCE = {
    "source": "biology.pdf",
    "page": 4,
    "similarity": 0.91,
    "text": "Photosynthesis stores light energy as chemical energy. Respiration releases usable energy.",
}


def allow_only_alice(monkeypatch):
    monkeypatch.setattr(
        course_store,
        "course_exists",
        lambda course_id, user_id: course_id == "course-a" and user_id == "alice",
    )


def test_mcp_client_discovers_tool_executes_it_and_rejects_other_student(monkeypatch):
    allow_only_alice(monkeypatch)
    calls = []
    server = build_document_server(lambda **kwargs: calls.append(kwargs) or [SOURCE], trusted_user_id="alice")

    async def exercise_protocol():
        async with Client(server, mode="legacy") as client:
            discovery = await client.list_tools()
            assert "search_course_documents" in {tool.name for tool in discovery.tools}
            response = await client.call_tool(
                "search_course_documents",
                {"query": "energy", "course_id": "course-a", "user_id": "alice", "limit": 6},
            )
            assert not response.is_error
            assert json.loads(response.content[0].text)[0]["source"] == "biology.pdf"
            denied = await client.call_tool(
                "search_course_documents",
                {"query": "energy", "course_id": "course-a", "user_id": "bob", "limit": 6},
            )
            assert denied.is_error is True
            payload = denied.model_dump_json(by_alias=True)
            assert json.loads(payload)["isError"] is True
            assert len(denied.content) == 1
            assert denied.content[0].text in ("Course unavailable or access denied.", "Error executing tool search_course_documents: Course unavailable or access denied.")
            for private_value in (SOURCE["source"], SOURCE["text"], "course-a", "bob", "sqlite", "Traceback", "private-id", "GROQ_API_KEY", "SUPABASE_ACCESS_TOKEN", "password"):
                assert private_value not in payload

    asyncio.run(exercise_protocol())
    assert len(calls) == 1
    assert calls[0]["user_id"] == "alice"


def test_mcp_helper_reports_real_discovery_and_tool_execution(monkeypatch):
    allow_only_alice(monkeypatch)
    server = build_document_server(lambda **kwargs: [SOURCE], trusted_user_id="alice")
    trace = []
    results = asyncio.run(call_document_search(
        server, query="energy", course_id="course-a", user_id="alice", trace=trace,
    ))
    assert results == [SOURCE]
    assert [(event["step"], event["status"]) for event in trace] == [
        ("mcp.tool_discovery", "ok"),
        ("mcp.search_course_documents", "ok"),
    ]
    assert all(event["duration_ms"] >= 0 for event in trace)


def test_compiled_graph_runs_comparison_and_quiz_through_mcp(monkeypatch):
    allow_only_alice(monkeypatch)
    captured = {}

    def fake_answer(question, passages, history=None):
        captured.update(question=question, passages=passages, history=history)
        return "## Comparison\n\n| Process | Energy |\n|---|---|\n| Photosynthesis | Stores |\n| Respiration | Releases |\n\n### Quiz\nQuestion 1: Which process stores energy?"

    monkeypatch.setattr("backend.phase4_graph.generate_answer", fake_answer)
    graph = build_question_graph(
        search_callback=lambda **kwargs: [SOURCE, {**SOURCE, "source": "second.pdf"}],
        follow_up_callback=lambda question, history: question,
        before_answer=lambda user_id: None,
    )
    structure = graph.get_graph()
    assert {"prepare", "retrieve", "generate"}.issubset(structure.nodes)
    assert {("__start__", "prepare"), ("prepare", "retrieve"),
            ("retrieve", "generate"), ("generate", "__end__")}.issubset(
                {(edge.source, edge.target) for edge in structure.edges}
            )

    request = {
        "question": "Compare photosynthesis and respiration, then create 3 MCQs.",
        "course_id": "course-a",
        "user_id": "alice",
        "history": [],
    }

    async def execute_and_trace():
        updates = []
        async for event in graph.astream(request, stream_mode="updates"):
            updates.extend(event.keys())
        return updates, await graph.ainvoke(request)

    updates, result = asyncio.run(execute_and_trace())
    assert updates == ["prepare", "retrieve", "generate"]
    assert "MCQs" in captured["question"]
    assert len(captured["passages"]) == 2
    assert result["mcp_used"] is True
    assert [event["step"] for event in result["trace"]] == [
        "node.prepare", "mcp.tool_discovery", "mcp.search_course_documents",
        "node.retrieve", "node.compare", "node.generate_quiz", "node.generate",
    ]


@pytest.mark.parametrize("question", [
    "Answer: what is photosynthesis?",
    "Summarize the lecture on photosynthesis.",
    "Create 4 MCQs about photosynthesis.",
    "Compare photosynthesis and respiration.",
])
def test_graph_preserves_supported_study_requests_and_follow_up_history(monkeypatch, question):
    allow_only_alice(monkeypatch)
    received = {}
    history = [{"role": "student", "text": "Explain photosynthesis"}]

    def fake_answer(prompt, passages, previous=None):
        received.update(prompt=prompt, previous=previous)
        return "A grounded answer."

    monkeypatch.setattr("backend.phase4_graph.generate_answer", fake_answer)
    graph = build_question_graph(
        search_callback=lambda **kwargs: [SOURCE],
        follow_up_callback=lambda current, prior: f"{prior[-1]['text']} -> {current}" if current == "and respiration?" else current,
        before_answer=lambda user_id: None,
    )
    query = question
    result = asyncio.run(graph.ainvoke({
        "question": query, "course_id": "course-a", "user_id": "alice", "history": history,
    }))
    assert result["mode"] == "generated"
    assert received["previous"] == history


def test_graph_resolves_a_conversational_follow_up(monkeypatch):
    allow_only_alice(monkeypatch)
    graph = build_question_graph(
        search_callback=lambda **kwargs: [SOURCE],
        follow_up_callback=lambda current, prior: f"Previous: {prior[-1]['text']}\nFollow-up: {current}",
        before_answer=lambda user_id: None,
    )
    monkeypatch.setattr("backend.phase4_graph.generate_answer", lambda *args, **kwargs: "Follow-up answer [1].")
    result = asyncio.run(graph.ainvoke({
        "question": "What about respiration?",
        "course_id": "course-a",
        "user_id": "alice",
        "history": [{"role": "student", "text": "Explain photosynthesis"}],
    }))
    assert result["search_question"] == "Previous: Explain photosynthesis\nFollow-up: What about respiration?"
    assert result["mode"] == "generated"


@pytest.mark.parametrize("question,raw_answer", [
    ("Summarize the lecture.", "## Summary\n- Main idea [1]."),
    ("Create 1 MCQ about 7 + 5.", r"Question 1: What is 7 + 5?\nA) 11 B) 12 C) 13 D) 14\nCorrect Answer: A\nExplanation: Add them."),
    ("Compare the two processes.", "| Process | Result |\n|---|---|\n| Photosynthesis | Stores | [1]"),
    ("What is the main idea?", "The passage explains energy storage [1]."),
])
def test_existing_llm_service_formats_tasks_and_keeps_only_valid_citations(monkeypatch, question, raw_answer):
    import llm_service

    monkeypatch.setenv("GROQ_API_KEY", "local-test-key")
    monkeypatch.setenv("GROQ_MODEL", "local-test-model")
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            content = raw_answer
            if "MCQ" in question:
                from tests.test_phase43 import quiz
                content = json.dumps(quiz())
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    class FakeGroq:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(llm_service, "Groq", FakeGroq)
    answer = llm_service.generate_answer(question, [SOURCE], history=[{"role": "student", "text": "Earlier topic"}])
    assert "[1]" in answer or "[1]" in question or "MCQ" in question
    assert "[99]" not in answer
    if "MCQ" in question:
        assert all(f"**{letter}.**" in answer for letter in "ABCD")
        assert "**Correct Answer:** B" in answer
        assert answer.count("**Correct Answer:**") == 5
    assert any("Earlier topic" in item.get("content", "") for item in captured["messages"])


def test_mcq_normalization_and_explicit_arithmetic_check():
    noisy = (
        r"Question 1: What is 7 + 5?\n"
        r"A) 11 B) 12 C) 13 D) 14\n"
        r"Correct Answer: A\nExplanation: Add the values. [1] 【9】"
    )
    answer = prepare_answer("Create 1 MCQ: What is 7 + 5?", noisy, source_count=1)
    assert "### Question 1" in answer
    for letter in "ABCD":
        assert f"**{letter}.**" in answer
    assert "**Correct Answer:** B" in answer
    assert "7 + 5 = 12" in answer
    assert "[1]" in answer
    assert "【9】" not in answer
    assert "\\n" not in answer


def test_citation_markers_are_normalized_and_limited_to_drawer_sources():
    answer = normalize_citations("Fact 【1】, more [Source 2], bad [9], alt 〔2〕.", 2)
    assert answer == "Fact [1], more [2], bad , alt [2]."


def test_supabase_auth_rejects_missing_bearer_token_without_network():
    with pytest.raises(HTTPException) as error:
        get_current_user(authorization=None)
    assert error.value.status_code == 401


def test_course_store_query_enforces_course_owner(tmp_path, monkeypatch):
    database_path = tmp_path / "isolated-test.sqlite3"
    monkeypatch.setattr(course_store, "DATABASE_PATH", database_path)
    course_store.initialize_database()
    with course_store.connect() as database:
        database.execute(
            "INSERT INTO courses (course_id, user_id, name) VALUES (?, ?, ?)",
            ("course-a", "alice", "Biology"),
        )
    assert course_store.course_exists("course-a", "alice") is True
    assert course_store.course_exists("course-a", "bob") is False
