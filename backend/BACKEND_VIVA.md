# Backend viva notes

- **FastAPI** is a Python framework that exposes functions through HTTP endpoints.
- **SQLite** is a small database stored in a local file. It stores course names and document details. **Persistence** means this information remains after the Python process stops.
- An **API** is a defined way for two programs to exchange requests and results.
- An **HTTP request** carries a method, address, and sometimes data. `GET` reads information; `POST` sends information to be processed.
- **CORS** is a browser rule. The API allows requests from the local Vite addresses used by this project.
- React calls the Python server with browser `fetch`. The upload uses `POST /documents/upload`; questions use `POST /chat/ask`.
- The upload route checks the filename, size, and PDF signature, then calls the existing `extract_pdf_pages`, `split_text_into_chunks`, and `add_document_chunks` helpers.
- Every course receives a random course ID. Documents store that ID, their display filename, hash, page count, chunk count, and generated PDF storage name as metadata in SQLite. The original filename is never used as a path.
- The existing RAG engine turns text chunks and the student's question into embeddings. Chroma stores chunk text and metadata. Search returns the closest passages.
- In this phase Chroma uses a local persistent collection. Each chunk includes its course ID, so the vector query filters on the selected course before it returns passages. SQLite tracks ownership and files; Chroma stores searchable text vectors.
- The API passes retrieved passages to the existing LLM helper. Each returned source filename and page is copied from the stored chunk metadata, so citations are not guessed.
- The API key stays in Python's environment and `.env`. The browser never receives it.
- **Groq** hosts language models behind an API. An **API key** is a private credential that lets the backend use the account. It belongs in `.env`, which is excluded from Git.
- A **model ID** is the provider's name for a model. `GROQ_MODEL` selects which compatible model receives the retrieved passages. The previous configured model was retired; the currently configured candidate is `openai/gpt-oss-20b`.
- When the API key is configured, `client.models.list()` checks the account's current model IDs. The configured model was present in that response.
- The backend sends the student's question and retrieved passages to Groq's chat-completions endpoint. The model is told to treat PDF passages as untrusted evidence. The API builds citations from the source filename and page stored with each retrieved chunk, rather than asking the model to invent metadata.
- If Groq is unavailable, the API returns `mode: retrieval_only`, a clear error, and the passages it did find. It does not make up an answer.
- The earlier prototype did not have sign-in. Phase 3B verifies Supabase accounts and scopes local course, document, chat, and vector queries to the verified account. SQLite and ChromaDB still run on this computer, so this is not a public production service.

```text
PDF in React --POST upload--> FastAPI --extract/chunk/embed--> Chroma
Question + course ID in React --POST ask--> FastAPI --course-filtered retrieval--> LLM
React <-- answer + stored filename/page citations -----------------+
```

An in-memory list disappears when Python exits. The SQLite file, generated-name PDF files, and Chroma storage folder are retained between restarts. Phase 3B adds verified account IDs and ownership filtering. The data remains on this one computer, and the app has not been hardened for public deployment.
# Phase 3B: Authentication and private data

- **Authentication** checks who signed in. **Authorization** checks what that person may access.
- **Supabase Auth** handles email/password registration and issues access tokens. The browser calls its standard Auth HTTP endpoints because the package registry was unreachable during setup.
- A **JWT** is a signed access token. React sends it as `Authorization: Bearer ...` with protected API calls.
- FastAPI sends that token to Supabase's `/auth/v1/user` endpoint and uses only the user ID returned by Supabase. It never trusts a user ID from a browser request or merely decodes a token.
- SQLite stores `user_id` on each course and document. A course ID identifies a course, and a document ID identifies one PDF record. A user can list, change, or delete rows only when the SQL query also matches their verified user ID.
- ChromaDB vectors carry the same user ID and course ID. Retrieval filters by both values, so another account's vectors are excluded.
- Chat sessions and messages are stored with the same owner and course. A session lookup checks the owner before returning history.
- Daily AI use is counted in SQLite. Course, PDF size, PDF count, and concurrent processing limits are checked on the backend, not in the browser.
- A Supabase public/publishable key is not a password. The Groq key stays in the backend `.env`; neither key is placed in React.
- The app is still a local prototype. It has no admin role, account recovery UI, or public deployment hardening, and local PDFs/vectors stay on this computer.

```text
React sign-up/sign-in -> Supabase Auth -> access token
React API request + token -> FastAPI verifies with Supabase /auth/v1/user
Verified user ID -> SQLite ownership check -> course-filtered Chroma retrieval -> Groq answer
```


## Phase 3C: conversation memory

Conversation memory is the recent discussion in one chat. RAG searches PDF text for factual evidence. Memory helps interpret a question; it does not replace document evidence.

Flow: User Question -> Load Recent History -> Resolve Follow-Up -> Retrieve Documents -> Generate Grounded Answer -> Save Messages -> Display Answer.

- `chat_sessions` and `chat_messages` are reused with no schema migration. Existing data stays in place. Source checkpoints are in `backend/backups/phase3c-source/`.
- A chat belongs to a verified user and a course. Every session lookup checks all three IDs before retrieval or Groq calls. IDs supplied by the browser never decide ownership.
- `GET /courses/{course_id}/chats` lists conversations. `POST` on that path creates an empty conversation. `GET /courses/{course_id}/chat?session_id=...` reopens it (latest 200 messages).
- `chat_memory.load_history` reads at most 12 messages for memory. `retrieval_question` adds recent user topics only for questions containing references such as 'it', 'that', or 'and'. This deterministic context enrichment costs no extra Groq request. It is a retrieval query, not a new factual answer. Some ambiguous questions still need the student to name the topic.
- Groq receives the last eight messages, shortened to 1,000 characters each, and at most six current passages. A system message makes current evidence authoritative. Old assistant messages are not verified evidence. The original question is displayed and saved.
- A generated turn saves both messages in one SQLite transaction. The browser sends a stable request ID on retry; a completed retry returns its saved answer. SQLite message IDs prevent duplicate saved turns. Concurrent retries may still consume extra provider calls; this is not a background queue.
- Provider errors return explicitly labeled retrieval-only content and are not saved as successful answers. Missing evidence returns a clear error and allows editing/retrying the original question.
- Citations are the actual retrieved filename/page/text, saved with that answer. They are never taken from a different conversation's latest response.

Verification: `python -m pytest tests backend/tests/test_api.py backend/tests/test_supabase_auth.py backend/tests/test_conversation.py -q` uses isolated data. Provider calls and embeddings are mocked in most automated route tests. The optional `backend/tests/manual_live_conversation.py` creates a test PDF and fresh storage, uses cached real embeddings, and makes at most two real Groq calls. It does not log secrets. A fresh-process SQLite read checks persistence; no user database or vectors are removed.

This phase adds no paid service, model change, or deployment. Real Supabase login needs an actual account/session; mocked ownership checks are not a substitute for a live login test.

Executed Phase 3C checks: the original/RAG/backend regression run passed 25 collected tests; final conversation checks include retry-ID conflict rejection and provider-failure persistence. A generated one-page clm-check.pdf was embedded with the real cached model; two real Groq turns returned generated answers with verified filename/page metadata. A disposable HTTP backend was started, stopped, and started again against that isolated live-check storage: four messages and their references were identical after restart. Identity was mocked only inside those disposable HTTP test processes. The normal application authentication dependency was never bypassed. A separate normal-auth server returned 401 without a token. User documents/databases were not used for these tests.
