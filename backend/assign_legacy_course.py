"""Interactively assign one old ownerless course to a verified Supabase user."""

import sys
import uuid
from pathlib import Path

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import course_store


def assign_course(course_id: str, user_id: str) -> None:
    """Assign an existing legacy course, its documents, and vectors together."""
    course_store.initialize_database()
    try:
        uuid.UUID(user_id)
    except ValueError as error:
        raise ValueError("Use the UUID shown for the account in Supabase Auth.") from error
    with course_store.connect() as database:
        course = database.execute(
            "SELECT course_id, name, user_id FROM courses WHERE course_id = ?", (course_id,)
        ).fetchone()
        if not course or course["user_id"] is not None:
            raise ValueError("That course does not exist or already has an owner.")
        documents = database.execute(
            "SELECT document_id FROM documents WHERE course_id = ? AND user_id IS NULL", (course_id,)
        ).fetchall()

    confirm = input(f"Type ASSIGN {course_id} TO {user_id} to continue: ").strip()
    if confirm != f"ASSIGN {course_id} TO {user_id}":
        print("No data was changed.")
        return

    vector_path = course_store.STORAGE_ROOT / "chroma"
    if vector_path.exists():
        client = chromadb.PersistentClient(path=str(vector_path))
        collection = client.get_or_create_collection("knowledgepilot_course_documents")
        for document in documents:
            records = collection.get(where={"document_id": document["document_id"]}, include=["metadatas"])
            if records["ids"]:
                metadata = [dict(item or {}, user_id=user_id) for item in records["metadatas"]]
                collection.update(ids=records["ids"], metadatas=metadata)

    with course_store.connect() as database:
        database.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        database.execute("UPDATE courses SET user_id = ? WHERE course_id = ? AND user_id IS NULL", (user_id, course_id))
        database.execute("UPDATE documents SET user_id = ? WHERE course_id = ? AND user_id IS NULL", (user_id, course_id))
    print(f"Assigned '{course['name']}' and {len(documents)} document(s) to the selected student.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m backend.assign_legacy_course <course_id> <verified_supabase_user_id>")
        raise SystemExit(2)
    try:
        assign_course(sys.argv[1], sys.argv[2])
    except ValueError as error:
        print(str(error))
        raise SystemExit(1) from error
