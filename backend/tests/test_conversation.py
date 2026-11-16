"""Conversation tests use temporary storage and mocked retrieval/provider calls."""
import json
import asyncio
import subprocess
import sys

import pytest
from fastapi import HTTPException
from backend.tests.test_api import api, course_store, create_course, upload, isolated_storage
from backend.chat_memory import load_history, retrieval_question


def test_followup_new_chat_retry_and_reopen(isolated_storage, monkeypatch):
    course = create_course("CLM")
    upload(course, "clm.pdf", "A Context Language Model uses context.")
    user = {"id": "student-a"}
    session = api.create_chat(course["course_id"], user)["session_id"]
    queries, histories = [], []

    def retrieve(*args, **kwargs):
        queries.append((args[1], kwargs["where"]))
        return [{"text": "A CLM uses context.", "source": "clm.pdf", "page": 1, "similarity": .9}]

    def answer(question, passages, history=None):
        histories.append(history or [])
        return "A CLM uses context [1]."

    monkeypatch.setattr(api, "search_relevant_chunks", retrieve)
    monkeypatch.setattr(api, "generate_answer", answer)
    def ask(text, chat, request_id):
        return asyncio.run(api.ask_question(api.QuestionRequest(course_id=course["course_id"],
            question=text, session_id=chat, request_id=request_id), user))

    ask("What is CLM?", session, "first")
    result = ask("How does it work?", session, "second")
    assert "What is CLM?" in queries[-1][0]
    assert histories[-1][0]["text"] == "What is CLM?"
    assert queries[-1][1] == {"$and": [{"course_id": course["course_id"]}, {"user_id": "student-a"}]}
    assert result["sources"][0]["filename"] == "clm.pdf"
    assert result["sources"][0]["page"] == 1
    ask("How does it work?", session, "second")
    assert len(queries) == 2
    with pytest.raises(HTTPException) as conflict:
        ask("A different question", session, "second")
    assert conflict.value.status_code == 409
    assert len(api.get_chat_history(course["course_id"], user, session)["messages"]) == 4
    fresh = api.create_chat(course["course_id"], user)["session_id"]
    ask("How does it work?", fresh, "fresh")
    assert queries[-1][0] == "How does it work?"
    assert histories[-1] == []
    # Read the saved messages from a fresh Python process (no in-memory state).
    code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('SELECT COUNT(*) FROM chat_messages WHERE session_id=?',(sys.argv[2],)).fetchone()[0])"
    output = subprocess.check_output([sys.executable, "-c", code, str(course_store.DATABASE_PATH), session], text=True)
    assert output.strip() == "4"


def test_session_privacy_and_invalid_ids(isolated_storage):
    own = create_course("Own")
    session = api.create_chat(own["course_id"], {"id": "student-a"})["session_id"]
    for owner, course, session_id in [("student-b", own["course_id"], session),
                                      ("student-a", own["course_id"], "invalid")]:
        with pytest.raises(HTTPException) as error:
            load_history(session_id, course, owner)
        assert error.value.status_code == 404
    other = create_course("Other")
    with pytest.raises(HTTPException):
        api.get_chat_history(other["course_id"], {"id": "student-a"}, session)


def test_rewrite_is_bounded_and_keeps_standalone_questions():
    history = [{"role": "student", "text": "topic " * 1000}] * 20
    assert len(retrieval_question("How does it work?", history)) < 1300
    assert retrieval_question("Explain photosynthesis", history) == "Explain photosynthesis"


def test_provider_failure_is_not_saved_as_an_answer(isolated_storage, monkeypatch):
    course = create_course("Provider failure")
    upload(course, "clm.pdf", "A CLM uses context.")
    user = {"id": "student-a"}
    session = api.create_chat(course["course_id"], user)["session_id"]
    monkeypatch.setattr(api, "search_relevant_chunks", lambda *args, **kwargs: [
        {"text": "A CLM uses context.", "source": "clm.pdf", "page": 1, "similarity": .9}])
    def unavailable(*args):
        raise api.LLMServiceError("Provider unavailable")
    monkeypatch.setattr(api, "generate_answer", unavailable)
    result = asyncio.run(api.ask_question(api.QuestionRequest(course_id=course["course_id"],
        session_id=session, question="Explain CLM"), user))
    assert result["mode"] == "retrieval_only"
    assert result["answer"] is None
    assert load_history(session, course["course_id"], user["id"]) == []
