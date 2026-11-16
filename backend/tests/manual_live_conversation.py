"""Optional live check: cached embeddings and at most two real Groq requests.

Uses a generated PDF and new temporary storage; never changes student data.
Run from the project root. Authentication is represented by a local test identity.
"""
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
storage = Path(tempfile.mkdtemp(prefix=".phase3c-live-", dir=root / "backend/tests"))
os.environ["KNOWLEDGEPILOT_STORAGE_PATH"] = str(storage)
os.environ["HF_HUB_OFFLINE"] = "1"  # Do not download another embedding model.

from backend import app as api
from backend.tests.test_api import DirectRouteClient, pdf_bytes


def main():
    client = DirectRouteClient()
    api.course_store.register_user(client.user["id"])
    course = api.create_course(api.CourseInput(name="CLM live check"), client.user)
    session = api.create_chat(course["course_id"], client.user)["session_id"]
    result = client.post("/documents/upload", data={"course_id": course["course_id"]}, files={
        "file": ("clm-check.pdf", pdf_bytes(
            "CLM means Context Language Model. A CLM uses earlier conversation messages as context. "
            "It combines the current question with previous discussion before finding evidence."
        ), "application/pdf")})
    print("Real PDF upload/index:", result.status_code)
    if result.status_code != 200:
        return
    for index, question in enumerate(["What is CLM?", "How does it work?"]):
        result = api.ask_question(api.QuestionRequest(course_id=course["course_id"],
            session_id=session, question=question, request_id=f"live-{index}"), client.user)
        print("Turn", index + 1, "provider mode:", result["mode"])
        valid_sources = all(source["filename"] == "clm-check.pdf" and source["page"] == 1
                            for source in result["sources"])
        print("Source metadata valid:", bool(result["sources"]) and valid_sources)
        print("Answer mentions context:", "context" in (result.get("answer") or "").lower())
        if result["mode"] != "generated":
            break
    print("Saved messages:", len(api.get_chat_history(course["course_id"], client.user, session)["messages"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Live check could not complete:", type(error).__name__)
        raise SystemExit(1)
