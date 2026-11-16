"""Persistence and course-isolation tests using temporary local storage."""

import sys
import asyncio
import inspect
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import chromadb
import fitz
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import app as api
from backend import course_store


class TinyEmbeddingModel:
    """Small deterministic vectors make route tests independent of downloads."""

    def encode(self, texts, normalize_embeddings=True):
        vectors = []
        for text in texts:
            lower = text.lower()
            vectors.append([
                1.0 if "orchid" in lower else 0.1,
                1.0 if "volcano" in lower else 0.1,
            ])
        return vectors


class FakeCollection:
    def __init__(self):
        self.records = {}

    def count(self):
        return len(self.records)

    def add(self, ids, documents, metadatas, **_values):
        for vector_id, text, metadata in zip(ids, documents, metadatas):
            self.records[vector_id] = {"text": text, "metadata": metadata}

    def get(self, where, include):
        document_id = where["document_id"]
        records = [(key, value) for key, value in self.records.items()
                   if value["metadata"].get("document_id") == document_id]
        return {"ids": [key for key, _ in records],
                "metadatas": [value["metadata"] for _, value in records]}

    def update(self, ids, metadatas):
        for vector_id, metadata in zip(ids, metadatas):
            self.records[vector_id]["metadata"] = metadata

    def delete(self, where):
        conditions = where.get("$and", [where])
        for vector_id, value in list(self.records.items()):
            if all(value["metadata"].get(key) == expected for item in conditions for key, expected in item.items()):
                del self.records[vector_id]


class RouteResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.text = json.dumps(data)

    def json(self):
        return self.data


class DirectRouteClient:
    """Call route functions directly because this Windows sandbox blocks TestClient sockets."""
    def __init__(self):
        self.user = {"id": "student-a", "email": "a@example.test"}

    @staticmethod
    def run_upload(coroutine):
        try:
            coroutine.send(None)
        except StopIteration as result:
            return result.value
        raise RuntimeError("The test upload unexpectedly waited for external I/O.")

    def call(self, function, *args, **kwargs):
        try:
            result = function(*args, **kwargs)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            return RouteResponse(result)
        except HTTPException as error:
            return RouteResponse({"detail": error.detail}, error.status_code)
        except ValidationError as error:
            return RouteResponse({"detail": str(error)}, 422)

    def get(self, path):
        parts = urlsplit(path).path.strip("/").split("/")
        if parts == ["health"]:
            return self.call(api.health)
        if parts == ["courses"]:
            return self.call(api.list_courses, self.user)
        if len(parts) == 3 and parts[0] == "courses" and parts[2] == "documents":
            return self.call(api.list_course_documents, parts[1], self.user)
        if len(parts) == 3 and parts[0] == "courses" and parts[2] == "chat":
            return self.call(api.get_chat_history, parts[1], self.user)
        return RouteResponse({"detail": "Not found"}, 404)

    def post(self, path, json=None, data=None, files=None):
        if path == "/courses":
            response = self.call(api.create_course, api.CourseInput(**json), self.user)
            if response.status_code == 200:
                response.status_code = 201
            return response
        if path == "/chat/ask":
            return self.call(api.ask_question, api.QuestionRequest(**json), self.user)
        if path == "/documents/upload":
            filename, content, content_type = files["file"]
            class LocalFile:
                def __init__(self):
                    self.filename, self.content_type = filename, content_type
                async def read(self, _limit):
                    return content
            try:
                result = self.run_upload(api.upload_document(
                    course_id=data["course_id"], file=LocalFile(), user=self.user
                ))
                return RouteResponse(result)
            except HTTPException as error:
                return RouteResponse({"detail": error.detail}, error.status_code)
        return RouteResponse({"detail": "Not found"}, 404)

    def patch(self, path, json=None):
        course_id = urlsplit(path).path.split("/")[2]
        return self.call(api.rename_course, course_id, api.CourseInput(**json), self.user)

    def delete(self, path):
        parsed = urlsplit(path)
        confirmed = parse_qs(parsed.query).get("confirmed", ["false"])[0].lower() == "true"
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "courses":
            return self.call(api.delete_course, parts[1], confirmed, self.user)
        if len(parts) == 2 and parts[0] == "documents":
            return self.call(api.delete_document, parts[1], confirmed, self.user)
        return RouteResponse({"detail": "Not found"}, 404)


def pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    document.new_page().insert_text((72, 72), text)
    result = document.tobytes()
    document.close()
    return result


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch, request):
    monkeypatch.setattr(course_store, "DATABASE_PATH", tmp_path / "courses.sqlite3")
    monkeypatch.setattr(course_store, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(api, "PDF_FOLDER", tmp_path / "documents")
    api.PDF_FOLDER.mkdir()
    if request.node.name.startswith("test_pdf_metadata_vectors_and_file_survive_backend_restart"):
        api.vector_client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
        api.collection = api.vector_client.get_or_create_collection(
            name=api.COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )
    else:
        api.vector_client = None
        api.collection = FakeCollection()
    api.embedding_model = TinyEmbeddingModel()
    api.search_relevant_chunks = REAL_SEARCH
    api.generate_answer = REAL_ANSWER
    course_store.initialize_database()
    course_store.register_user("student-a")
    client.user = {"id": "student-a", "email": "a@example.test"}
    yield tmp_path


client = DirectRouteClient()
REAL_SEARCH = api.search_relevant_chunks
REAL_ANSWER = api.generate_answer


def create_course(name: str) -> dict:
    response = client.post("/courses", json={"name": name})
    assert response.status_code == 201
    return response.json()


def upload(course: dict, filename: str, text: str) -> dict:
    response = client.post(
        "/documents/upload",
        data={"course_id": course["course_id"]},
        files={"file": (filename, pdf_bytes(text), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()["document"]


def test_create_rename_and_reject_unknown_course():
    course = create_course("Botany")
    renamed = client.patch(f"/courses/{course['course_id']}", json={"name": "Plant Science"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Plant Science"
    assert client.get("/courses/not-a-course/documents").status_code == 404
    assert client.post("/documents/upload", data={"course_id": "bad"}, files={
        "file": ("note.pdf", pdf_bytes("orchids"), "application/pdf")
    }).status_code == 404


def test_courses_retrieve_only_their_own_documents():
    course_a = create_course("Botany")
    course_b = create_course("Geology")
    upload(course_a, "orchids.pdf", "An orchid is a flowering plant.")
    upload(course_b, "volcanoes.pdf", "A volcano can release hot lava.")
    def fake_search(_collection, _question, _model, where=None, **_options):
        values = {key: value for clause in where["$and"] for key, value in clause.items()}
        assert values["user_id"] == "student-a"
        if values["course_id"] == course_a["course_id"]:
            if "volcano" in _question.lower():
                return []
            return [{"text": "An orchid is a flowering plant.", "source": "orchids.pdf", "page": 1, "similarity": .9}]
        return [{"text": "A volcano can release hot lava.", "source": "volcanoes.pdf", "page": 1, "similarity": .9}]
    api.search_relevant_chunks = fake_search
    api.generate_answer = lambda question, passages: "A grounded example answer."

    result = client.post("/chat/ask", json={
        "course_id": course_a["course_id"], "question": "Tell me about the orchid."
    })
    assert result.status_code == 200
    assert [source["filename"] for source in result.json()["sources"]] == ["orchids.pdf"]
    assert all("volcano" not in source["text"].lower() for source in result.json()["sources"])
    blocked = client.post("/chat/ask", json={
        "course_id": course_a["course_id"], "question": "Tell me about the volcano."
    })
    assert blocked.status_code == 404
    assert "this course" in blocked.json()["detail"]


@pytest.mark.parametrize("isolated_storage", [True], indirect=True)
def test_pdf_metadata_vectors_and_file_survive_backend_restart(isolated_storage):
    course = create_course("Biology")
    record = upload(course, "cell.pdf", "An orchid cell contains a nucleus.")
    environment = os.environ.copy()
    environment["KNOWLEDGEPILOT_STORAGE_PATH"] = str(isolated_storage)
    check_code = """
import json
import sys
sys.path.insert(0, '.')
from backend import app
rows = app.course_store.course_documents(%r, 'student-a')
collection = app.get_collection()
metadata = collection.get(include=['metadatas'])['metadatas']
print(json.dumps({'docs': len(rows), 'id': rows[0]['document_id'], 'vectors': collection.count(), 'course': metadata[0]['course_id'], 'owner': metadata[0]['user_id'], 'file': (app.PDF_FOLDER / (rows[0]['document_id'] + '.pdf')).exists()}))
""" % course["course_id"]
    result = subprocess.run(
        [sys.executable, "-c", check_code],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=90,
    )
    persisted = json.loads(result.stdout.strip().splitlines()[-1])
    assert persisted == {
        "docs": 1,
        "id": record["document_id"],
        "vectors": 1,
        "course": course["course_id"],
        "owner": "student-a",
        "file": True,
    }


def test_duplicate_upload_and_document_delete_remove_vectors():
    course = create_course("Botany")
    content = pdf_bytes("An orchid is a flowering plant.")
    record = client.post("/documents/upload", data={"course_id": course["course_id"]}, files={
        "file": ("orchid.pdf", content, "application/pdf")
    }).json()["document"]
    duplicate = client.post("/documents/upload", data={"course_id": course["course_id"]}, files={
        "file": ("renamed.pdf", content, "application/pdf")
    })
    assert duplicate.json()["duplicate"] is True
    assert api.collection.count() == 1

    deleted = client.delete(f"/documents/{record['document_id']}?confirmed=true")
    assert deleted.status_code == 200
    assert api.collection.count() == 0
    assert client.get(f"/courses/{course['course_id']}/documents").json()["documents"] == []


def test_course_delete_requires_confirmation_and_cascades():
    course = create_course("Temporary class")
    record = upload(course, "orchid.pdf", "An orchid is a flowering plant.")
    assert client.delete(f"/courses/{course['course_id']}").status_code == 400
    assert client.delete(f"/courses/{course['course_id']}?confirmed=true").status_code == 200
    assert client.get("/courses").json()["courses"] == []
    assert api.collection.count() == 0
    assert not (api.PDF_FOLDER / f"{record['document_id']}.pdf").exists()


def test_invalid_file_is_rejected():
    course = create_course("Botany")
    result = client.post("/documents/upload", data={"course_id": course["course_id"]}, files={
        "file": ("notes.pdf", b"not a pdf", "application/pdf")
    })
    assert result.status_code == 400


def test_missing_token_is_rejected(isolated_storage):
    with pytest.raises(HTTPException) as error:
        api.get_current_user(None)
    assert error.value.status_code == 401


def test_health_is_public_and_workspace_routes_require_authorization(isolated_storage):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    schema = api.app.openapi()
    course_parameters = schema["paths"]["/courses"]["get"]["parameters"]
    assert any(parameter["name"] == "authorization" and parameter["in"] == "header" for parameter in course_parameters)


def test_accounts_cannot_read_or_delete_other_student_data(isolated_storage):
    course_a = create_course("Private Biology")
    record_a = upload(course_a, "student-a.pdf", "Student A studies orchids.")
    course_store.register_user("student-b")
    client.user = {"id": "student-b", "email": "b@example.test"}
    course_store.register_user("student-b")
    course_b = create_course("Private Biology")
    record_b = upload(course_b, "student-b.pdf", "Student B studies volcanoes.")

    assert client.get("/courses").json()["courses"][0]["course_id"] == course_b["course_id"]
    assert client.get(f"/courses/{course_a['course_id']}/documents").status_code == 404
    assert client.delete(f"/documents/{record_a['document_id']}?confirmed=true").status_code == 404
    assert client.post("/chat/ask", json={
        "course_id": course_a["course_id"], "question": "volcano", "user_id": "student-a"
    }).status_code == 404

    client.user = {"id": "student-a", "email": "a@example.test"}
    assert client.get("/courses").json()["courses"][0]["course_id"] == course_a["course_id"]
    assert client.delete(f"/documents/{record_b['document_id']}?confirmed=true").status_code == 404


def test_daily_question_limit_is_saved_in_sqlite(isolated_storage, monkeypatch):
    course = create_course("Daily limit")
    upload(course, "orchids.pdf", "An orchid is a flowering plant.")
    monkeypatch.setattr(api, "MAX_DAILY_QUESTIONS", 2)
    api.search_relevant_chunks = lambda *_args, **_kwargs: [
        {"text": "An orchid is a flowering plant.", "source": "orchids.pdf", "page": 1, "similarity": .9}
    ]
    api.generate_answer = lambda *_args: "An orchid is a flowering plant."
    payload = {"course_id": course["course_id"], "question": "What is an orchid?"}
    assert client.post("/chat/ask", json=payload).status_code == 200
    assert client.post("/chat/ask", json=payload).status_code == 200
    limited = client.post("/chat/ask", json=payload)
    assert limited.status_code == 429
    assert "tomorrow" in limited.json()["detail"]


def test_account_and_course_upload_limits_are_enforced(isolated_storage, monkeypatch):
    monkeypatch.setattr(api, "MAX_COURSES", 1)
    monkeypatch.setattr(api, "MAX_DOCUMENTS_PER_COURSE", 1)
    course = create_course("Bounded course")
    assert client.post("/courses", json={"name": "Second course"}).status_code == 429
    upload(course, "first.pdf", "An orchid is a flowering plant.")
    second_pdf = client.post("/documents/upload", data={"course_id": course["course_id"]}, files={
        "file": ("second.pdf", pdf_bytes("A different text about orchids."), "application/pdf")
    })
    assert second_pdf.status_code == 429
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 8)
    large_pdf = client.post("/documents/upload", data={"course_id": course["course_id"]}, files={
        "file": ("large.pdf", pdf_bytes("An oversized local PDF."), "application/pdf")
    })
    assert large_pdf.status_code == 413


def test_concurrent_processing_limit_uses_sqlite(isolated_storage, monkeypatch):
    monkeypatch.setattr(api, "MAX_PROCESSING_TASKS", 1)
    first_job = api.reserve_processing_slot("student-a", "course-one")
    with pytest.raises(HTTPException) as error:
        api.reserve_processing_slot("student-b", "course-two")
    assert error.value.status_code == 429
    api.finish_processing(first_job, "complete")


def test_retrieval_filter_includes_owner_and_course(isolated_storage):
    course_a = create_course("Own course")
    upload(course_a, "own.pdf", "An orchid is a flowering plant.")
    course_store.register_user("student-b")
    client.user = {"id": "student-b", "email": "b@example.test"}
    course_b = create_course("Other course")
    upload(course_b, "other.pdf", "A volcano can release hot lava.")
    client.user = {"id": "student-a", "email": "a@example.test"}
    filters = []

    def retrieve(_collection, _question, _model, where=None, **_options):
        filters.append(where)
        return [{"text": "An orchid is a flowering plant.", "source": "own.pdf", "page": 1, "similarity": .9}]

    api.search_relevant_chunks = retrieve
    api.generate_answer = lambda *_args: "An orchid is a plant."
    response = client.post("/chat/ask", json={
        "course_id": course_a["course_id"], "question": "What is an orchid?"
    })
    assert response.status_code == 200
    assert filters == [{"$and": [{"course_id": course_a["course_id"]}, {"user_id": "student-a"}]}]
    assert [source["filename"] for source in response.json()["sources"]] == ["own.pdf"]


def test_chat_history_is_owner_scoped(isolated_storage):
    course_a = create_course("History A")
    upload(course_a, "orchid.pdf", "An orchid is a flowering plant.")
    api.search_relevant_chunks = lambda *_args, **_kwargs: [
        {"text": "An orchid is a flowering plant.", "source": "orchid.pdf", "page": 1, "similarity": .9}
    ]
    api.generate_answer = lambda *_args: "It is a plant."
    result = client.post("/chat/ask", json={"course_id": course_a["course_id"], "question": "What is it?"})
    assert result.status_code == 200
    assert client.get(f"/courses/{course_a['course_id']}/chat").json()["messages"][1]["text"] == "It is a plant."

    client.user = {"id": "student-b", "email": "b@example.test"}
    course_store.register_user("student-b")
    assert client.get(f"/courses/{course_a['course_id']}/chat").status_code == 404
