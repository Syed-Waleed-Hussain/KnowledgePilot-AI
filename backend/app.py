"""Local FastAPI app for private courses and document-based study."""

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path, PurePath
from typing import Any

import chromadb
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import course_store
from backend.chat_memory import load_history, retrieval_question
from backend.phase4_graph import build_question_graph
from backend.supabase_auth import get_current_user
from llm_service import LLMServiceError, generate_answer
from pdf_processor import extract_pdf_pages, split_text_into_chunks
from rag_engine import add_document_chunks, load_embedding_model, search_relevant_chunks

STORAGE_ROOT = course_store.STORAGE_ROOT
PDF_FOLDER = STORAGE_ROOT / "documents"
CHROMA_FOLDER = STORAGE_ROOT / "chroma"
COLLECTION_NAME = "knowledgepilot_course_documents"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_PDF_BYTES", str(5 * 1024 * 1024)))
MAX_COURSES = int(os.getenv("MAX_COURSES_PER_USER", "3"))
MAX_DOCUMENTS_PER_COURSE = int(os.getenv("MAX_DOCUMENTS_PER_COURSE", "5"))
MAX_DAILY_QUESTIONS = int(os.getenv("MAX_AI_QUESTIONS_PER_DAY", "10"))
MAX_PROCESSING_TASKS = int(os.getenv("MAX_CONCURRENT_PROCESSING", "2"))

STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
PDF_FOLDER.mkdir(parents=True, exist_ok=True)
course_store.initialize_database()
vector_client: Any = None
collection: Any = None
embedding_model: Any = None

app = FastAPI(title="KnowledgePilot Local API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    # Allow Vite's fallback ports while keeping browser access on loopback only.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):[0-9]{1,5}$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


class CourseInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class QuestionRequest(BaseModel):
    course_id: str
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    request_id: str | None = Field(default=None, max_length=80)


def get_model() -> Any:
    """Load and keep one copy of the embedding model in this process."""
    global embedding_model
    if embedding_model is None:
        embedding_model = load_embedding_model()
    return embedding_model


def get_collection() -> Any:
    """Open the persistent vector collection when the first RAG call needs it."""
    global vector_client, collection
    if collection is None:
        CHROMA_FOLDER.mkdir(parents=True, exist_ok=True)
        vector_client = chromadb.PersistentClient(path=str(CHROMA_FOLDER))
        collection = vector_client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )
    return collection


def require_course(course_id: str, user_id: str) -> None:
    if not course_store.course_exists(course_id, user_id):
        # Do not reveal whether another student's course ID exists.
        raise HTTPException(status_code=404, detail="Course not found.")


def add_vector_owner(vector_collection: Any, document_id: str, user_id: str) -> None:
    """Tag new vectors after using the original shared embedding helper."""
    records = vector_collection.get(where={"document_id": document_id}, include=["metadatas"])
    metadata = [dict(item or {}, user_id=user_id) for item in records["metadatas"]]
    if records["ids"]:
        vector_collection.update(ids=records["ids"], metadatas=metadata)


def delete_course_data(course_id: str, user_id: str) -> None:
    rows = course_store.course_documents(course_id, user_id)
    vector_collection = get_collection()
    if vector_collection.count():
        vector_collection.delete(where={"$and": [{"course_id": course_id}, {"user_id": user_id}]})
    for row in rows:
        (PDF_FOLDER / f"{row['document_id']}.pdf").unlink(missing_ok=True)
    with course_store.connect() as database:
        database.execute("DELETE FROM courses WHERE course_id = ? AND user_id = ?", (course_id, user_id))


def reserve_processing_slot(user_id: str, course_id: str) -> str:
    job_id = uuid.uuid4().hex
    with course_store.connect() as database:
        database.execute("BEGIN IMMEDIATE")
        active = database.execute(
            "SELECT COUNT(*) FROM processing_jobs WHERE status = 'processing'"
        ).fetchone()[0]
        if active >= MAX_PROCESSING_TASKS:
            raise HTTPException(status_code=429, detail="The local PDF processor is busy. Try again in a moment.")
        indexed = database.execute(
            "SELECT COUNT(*) FROM documents WHERE user_id = ? AND course_id = ?",
            (user_id, course_id),
        ).fetchone()[0]
        pending = database.execute(
            "SELECT COUNT(*) FROM processing_jobs WHERE user_id = ? AND course_id = ? AND status = 'processing'",
            (user_id, course_id),
        ).fetchone()[0]
        if indexed + pending >= MAX_DOCUMENTS_PER_COURSE:
            raise HTTPException(status_code=429, detail=f"A course can contain up to {MAX_DOCUMENTS_PER_COURSE} PDFs.")
        database.execute(
            "INSERT INTO processing_jobs (job_id, user_id, course_id, status) VALUES (?, ?, ?, 'processing')",
            (job_id, user_id, course_id),
        )
    return job_id


def finish_processing(job_id: str, status: str) -> None:
    with course_store.connect() as database:
        database.execute("UPDATE processing_jobs SET status = ? WHERE job_id = ?", (status, job_id))


def reserve_daily_question(user_id: str) -> None:
    today = date.today().isoformat()
    with course_store.connect() as database:
        database.execute("BEGIN IMMEDIATE")
        row = database.execute(
            "SELECT question_count FROM daily_usage WHERE user_id = ? AND usage_date = ?",
            (user_id, today),
        ).fetchone()
        count = int(row["question_count"]) if row else 0
        if count >= MAX_DAILY_QUESTIONS:
            raise HTTPException(status_code=429, detail="You have reached today's AI question limit. Try again tomorrow.")
        if row:
            database.execute(
                "UPDATE daily_usage SET question_count = question_count + 1 WHERE user_id = ? AND usage_date = ?",
                (user_id, today),
            )
        else:
            database.execute(
                "INSERT INTO daily_usage (user_id, usage_date, question_count) VALUES (?, ?, 1)",
                (user_id, today),
            )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "application": "KnowledgePilot Local API",
        "llm_configured": bool(os.getenv("GROQ_API_KEY")),
        "authentication_configured": bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY")),
    }


@app.get("/courses")
def list_courses(user: dict[str, str] = Depends(get_current_user)) -> dict[str, list[dict[str, Any]]]:
    with course_store.connect() as database:
        courses = database.execute(
            "SELECT course_id, name, created_at FROM courses WHERE user_id = ? ORDER BY name",
            (user["id"],),
        ).fetchall()
        result = []
        for course in courses:
            item = course_store.row_to_dict(course)
            item["document_count"] = database.execute(
                "SELECT COUNT(*) FROM documents WHERE course_id = ? AND user_id = ?",
                (item["course_id"], user["id"]),
            ).fetchone()[0]
            result.append(item)
    return {"courses": result}


@app.post("/courses", status_code=201)
def create_course(request: CourseInput, user: dict[str, str] = Depends(get_current_user)) -> dict[str, Any]:
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Enter a course name.")
    course_id = uuid.uuid4().hex
    try:
        with course_store.connect() as database:
            database.execute("BEGIN IMMEDIATE")
            count = database.execute("SELECT COUNT(*) FROM courses WHERE user_id = ?", (user["id"],)).fetchone()[0]
            if count >= MAX_COURSES:
                raise HTTPException(status_code=429, detail=f"You can create up to {MAX_COURSES} courses in this prototype.")
            database.execute(
                "INSERT INTO courses (course_id, user_id, name) VALUES (?, ?, ?)",
                (course_id, user["id"], name),
            )
    except Exception as error:
        if "UNIQUE" in str(error):
            raise HTTPException(status_code=409, detail="You already have a course with this name.") from None
        raise
    return {"course_id": course_id, "name": name, "document_count": 0}


@app.patch("/courses/{course_id}")
def rename_course(course_id: str, request: CourseInput, user: dict[str, str] = Depends(get_current_user)) -> dict[str, Any]:
    require_course(course_id, user["id"])
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Enter a course name.")
    try:
        with course_store.connect() as database:
            database.execute("UPDATE courses SET name = ? WHERE course_id = ? AND user_id = ?", (name, course_id, user["id"]))
    except Exception as error:
        if "UNIQUE" in str(error):
            raise HTTPException(status_code=409, detail="You already have a course with this name.") from None
        raise
    return {"course_id": course_id, "name": name, "document_count": len(course_store.course_documents(course_id, user["id"]))}


@app.delete("/courses/{course_id}")
def delete_course(course_id: str, confirmed: bool = Query(False), user: dict[str, str] = Depends(get_current_user)) -> dict[str, str]:
    require_course(course_id, user["id"])
    if not confirmed:
        raise HTTPException(status_code=400, detail="Confirm course deletion first.")
    delete_course_data(course_id, user["id"])
    return {"status": "deleted", "course_id": course_id}


@app.get("/courses/{course_id}/documents")
def list_course_documents(course_id: str, user: dict[str, str] = Depends(get_current_user)) -> dict[str, list[dict[str, Any]]]:
    require_course(course_id, user["id"])
    return {"documents": course_store.course_documents(course_id, user["id"])}


@app.get("/courses/{course_id}/chats")
def list_chats(course_id: str, user: dict[str, str] = Depends(get_current_user)):
    require_course(course_id, user["id"])
    with course_store.connect() as database:
        rows = database.execute(
            "SELECT s.session_id, s.created_at, COALESCE((SELECT substr(content,1,70) FROM chat_messages m "
            "WHERE m.session_id=s.session_id AND m.role='student' ORDER BY m.rowid LIMIT 1), 'New chat') AS title "
            "FROM chat_sessions s WHERE s.course_id=? AND s.user_id=? ORDER BY s.rowid DESC",
            (course_id, user["id"]),
        ).fetchall()
    return {"sessions": [dict(row) for row in rows]}


@app.post("/courses/{course_id}/chats")
def create_chat(course_id: str, user: dict[str, str] = Depends(get_current_user)):
    require_course(course_id, user["id"])
    session_id = uuid.uuid4().hex
    with course_store.connect() as database:
        database.execute("INSERT INTO chat_sessions (session_id,user_id,course_id) VALUES (?,?,?)",
                         (session_id,user["id"],course_id))
    return {"session_id": session_id}


@app.get("/courses/{course_id}/chat")
def get_chat_history(course_id: str, user: dict[str, str] = Depends(get_current_user), session_id: str | None = None):
    require_course(course_id, user["id"])
    if not session_id:
        sessions = list_chats(course_id, user)["sessions"]
        session_id = sessions[0]["session_id"] if sessions else None
    return {"session_id": session_id, "messages": load_history(session_id, course_id, user["id"], 200)}


@app.post("/documents/upload")
async def upload_document(
    course_id: str = Form(...),
    file: UploadFile = File(...),
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, Any]:
    require_course(course_id, user["id"])
    filename = PurePath(file.filename or "").name
    if not filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Choose a PDF file.")
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="The uploaded file must be a PDF.")
    pdf_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"PDF must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="File contents are not a valid PDF.")
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    with course_store.connect() as database:
        duplicate = database.execute(
            "SELECT document_id, course_id, filename, page_count, chunk_count, status FROM documents WHERE user_id = ? AND course_id = ? AND file_hash = ?",
            (user["id"], course_id, file_hash),
        ).fetchone()
    if duplicate:
        return {"document": course_store.row_to_dict(duplicate), "duplicate": True}
    job_id = reserve_processing_slot(user["id"], course_id)
    document_id = uuid.uuid4().hex
    stored_path = PDF_FOLDER / f"{document_id}.pdf"
    vector_collection = None
    try:
        vector_collection = get_collection()
        pages = extract_pdf_pages(pdf_bytes)
        chunks = split_text_into_chunks(pages)
        if not chunks:
            raise ValueError("This PDF does not contain readable text.")
        stored_path.write_bytes(pdf_bytes)
        add_document_chunks(
            vector_collection, chunks, filename, file_hash, get_model(),
            document_id=document_id, course_id=course_id,
        )
        add_vector_owner(vector_collection, document_id, user["id"])
        with course_store.connect() as database:
            database.execute(
                "INSERT INTO documents (document_id, user_id, course_id, filename, file_hash, stored_path, page_count, chunk_count, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (document_id, user["id"], course_id, filename, file_hash, stored_path.name,
                 max(int(page["page"]) for page in pages), len(chunks), "indexed"),
            )
        finish_processing(job_id, "complete")
    except ValueError as error:
        finish_processing(job_id, "failed")
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception:
        finish_processing(job_id, "failed")
        if vector_collection is not None:
            vector_collection.delete(where={"document_id": document_id})
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="PDF indexing failed. Check the file and try again.") from None
    return {"document": {
        "document_id": document_id, "course_id": course_id, "filename": filename,
        "page_count": max(int(page["page"]) for page in pages), "chunk_count": len(chunks), "status": "indexed",
    }, "duplicate": False}


@app.delete("/documents/{document_id}")
def delete_document(document_id: str, confirmed: bool = Query(False), user: dict[str, str] = Depends(get_current_user)) -> dict[str, str]:
    with course_store.connect() as database:
        row = database.execute(
            "SELECT document_id, stored_path FROM documents WHERE document_id = ? AND user_id = ?",
            (document_id, user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")
    if not confirmed:
        raise HTTPException(status_code=400, detail="Confirm document deletion first.")
    vector_collection = get_collection()
    vector_collection.delete(where={"$and": [{"document_id": document_id}, {"user_id": user["id"]}]})
    (PDF_FOLDER / Path(row["stored_path"]).name).unlink(missing_ok=True)
    with course_store.connect() as database:
        database.execute("DELETE FROM documents WHERE document_id = ? AND user_id = ?", (document_id, user["id"]))
    return {"status": "deleted", "document_id": document_id}


@app.post("/chat/ask")
async def ask_question(request: QuestionRequest, user: dict[str, str] = Depends(get_current_user)) -> dict[str, Any]:
    require_course(request.course_id, user["id"])
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Enter a question.")
    history = load_history(request.session_id, request.course_id, user["id"])
    # A retry of a completed turn returns its saved answer without a second LLM call.
    answer_id = f"answer:{user['id']}:{request.course_id}:{request.session_id}:{request.request_id}" if request.request_id else uuid.uuid4().hex
    with course_store.connect() as database:
        saved = database.execute(
            "SELECT content, sources_json, session_id FROM chat_messages WHERE message_id=? AND user_id=? AND course_id=?",
            (answer_id, user["id"], request.course_id),
        ).fetchone()
    if saved:
        with course_store.connect() as database:
            original = database.execute("SELECT content FROM chat_messages WHERE message_id=?", ("student:" + answer_id,)).fetchone()
        if saved["session_id"] != request.session_id or not original or original["content"] != question:
            raise HTTPException(409, "This request ID already belongs to a different message.")
        return {"answer": saved["content"], "sources": json.loads(saved["sources_json"]),
                "mode": "generated", "session_id": saved["session_id"], "error": None,
                "workflow_executed": False, "mcp_tool_executed": False, "workflow_trace": []}
    documents = course_store.course_documents(request.course_id, user["id"])
    if not documents:
        raise HTTPException(status_code=404, detail="This course has no indexed documents yet.")

    combined = bool(re.search(r"compare|comparison", question, re.I) and re.search(r"quiz|mcq", question, re.I))
    selected_documents = []
    if combined:
        context = question + " " + " ".join(item.get("text", "") for item in history[-8:] if item.get("role") == "student")
        selected_documents = [d for d in documents if d["filename"].casefold() in context.casefold()]
        if len(selected_documents) != 2 and len(documents) == 2:
            selected_documents = documents
        if len(selected_documents) != 2 or len({d["filename"] for d in selected_documents}) != 2:
            raise HTTPException(422, "Please name the two lecture PDF filenames to compare.")
    requested_page = re.search(r"\bpage\s+(\d+)\b", question, re.IGNORECASE)

    def search_course(
        *, query: str, course_id: str, user_id: str, limit: int,
        page: int | None = None,
    ) -> list[dict[str, Any]]:
        # Recheck ownership at the data boundary, even after the route check.
        require_course(course_id, user_id)
        vector_collection = get_collection()
        filters = [{"course_id": course_id}, {"user_id": user_id}]
        if page is not None:
            filters.append({"page": page})
        if combined:
            passages = []
            for document in selected_documents:
                passages.extend(search_relevant_chunks(
                    vector_collection, query, get_model(), top_k=3,
                    where={"$and": filters + [{"document_id": document["document_id"]}]},
                ))
            return passages
        return search_relevant_chunks(
            vector_collection, query, get_model(),
            top_k=max(vector_collection.count(), 1) if page is not None else limit,
            where={"$and": filters},
        )

    graph = build_question_graph(
        search_callback=search_course,
        follow_up_callback=retrieval_question,
        before_answer=reserve_daily_question,
        answer_callback=generate_answer,
    )
    try:
        result = await graph.ainvoke({
            "question": question,
            "course_id": request.course_id,
            "user_id": user["id"],
            "history": history,
            "page": int(requested_page.group(1)) if requested_page else None,
        })
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Document retrieval failed. Try again or restart the local API.") from None
    passages = result.get("passages", [])
    if not passages:
        raise HTTPException(status_code=404, detail="No relevant text was found in this course's documents.")
    passages = passages[:6]
    sources = [{
        "filename": item["source"], "page": item["page"],
        "similarity": round(float(item["similarity"]), 3), "text": item["text"],
    } for item in passages]
    mode = result.get("mode", "retrieval_only")
    answer = result.get("answer", "")
    error = result.get("error")
    session_id = request.session_id
    if mode != "generated":
        return {"answer": None, "error": error or "The AI answer service is unavailable. Review the retrieved passages below and try again later.",
                "sources": sources, "mode": mode, "session_id": session_id,
                "workflow_executed": True, "mcp_tool_executed": bool(result.get("mcp_used")),
                "workflow_trace": result.get("trace", [])}
    if not session_id:
        session_id = create_chat(request.course_id, user)["session_id"]
    with course_store.connect() as database:
        # Both messages are saved atomically. The request ID prevents duplicate saved turns.
        database.executemany(
            "INSERT OR IGNORE INTO chat_messages (message_id, session_id, user_id, course_id, role, content, sources_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [("student:" + answer_id, session_id, user["id"], request.course_id, "student", question, "[]"),
             (answer_id, session_id, user["id"], request.course_id, "generated", answer, json.dumps(sources))],
        )
    return {"answer": answer, "error": None, "sources": sources, "mode": mode, "session_id": session_id,
            "workflow_executed": True, "mcp_tool_executed": bool(result.get("mcp_used")),
            "workflow_trace": result.get("trace", [])}
