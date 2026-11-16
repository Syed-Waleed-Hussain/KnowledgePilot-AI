# KnowledgePilot local API

This FastAPI service connects the React study workspace to the existing PDF and RAG helper modules. It is a local, single-user prototype. SQLite stores course/document metadata, PDF files use generated safe names, and ChromaDB stores persistent course-tagged vectors. These new files live under `backend/storage_phase3/` and are ignored by Git.

## Start the API (PowerShell)

Use the existing backend environment; this phase does not recreate either virtual environment:

```powershell
cd "D:\Fast University\Semester no 07\Agentic AI\Project"
.\backend\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

Run the frontend separately from the project `frontend/` folder with `npm run dev`. Configure Groq by adding `GROQ_API_KEY` to the project root `.env` file. The key is read only by Python and is never returned by the health endpoint. Without it, upload and retrieval can work, while answer generation returns a retrieval-only response.

The authenticated API accepts PDFs up to 5 MB by default, requires selectable text, and does not run OCR. Restarting the backend reloads metadata and vectors from local storage. New uploads are persisted. The local prototype allows 3 courses per student, 5 PDFs per course and 10 answer requests per day; limits can be changed with the `MAX_*` values in `.env`. Do not expose this development API to a public network.

## Supabase Auth setup (free plan)

1. Create one Supabase project on its **Free** plan. Do not add a billing method or enable paid add-ons.
2. In the project settings, copy the Project URL and the publishable (or legacy anon) public key.
3. Copy `frontend/.env.example` to `frontend/.env.local`. Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` to those values.
4. Put the same values in the project-root `.env` as `SUPABASE_URL` and `SUPABASE_ANON_KEY`. Never use a `service_role` or secret key in the browser.
5. In Auth URL settings, set the local site URL to `http://localhost:5173` and include `http://127.0.0.1:5173` as a redirect URL. Restart both local servers. Hosted email confirmation is enabled by default. The built-in email service can send only to team addresses and is limited to 2 emails/hour. For a local classroom-only demonstration, you may disable confirmation in the test project (email ownership will then be unverified); do not use that setting for a public service or configure paid SMTP.

The database and PDFs remain local in `backend/storage_phase3/`; Supabase is used only for accounts and token verification. The prior ownerless course/PDF remains private and hidden. If it should belong to a specific account, use the interactive assignment command in the viva notes only after confirming the account's Supabase user ID. Supabase Free has quotas and may pause inactive projects; review the provider's current limits before inviting users. Groq also has free-tier request limits; the app returns errors when limits are reached and must never be upgraded to a billable tier under the PKR 0 requirement.

### Optional legacy ownership assignment

The old `Agentic AI` course and its PDF remain ownerless until you choose an account. Stop FastAPI, find that student's **user ID** in Supabase Authentication → Users, then run this from the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m backend.assign_legacy_course <course_id> <supabase_user_uuid>
```

The script asks you to type the exact course ID and user ID before assigning the course, document records, and vectors. If you do not confirm, it changes nothing. Do not assign records to an account unless you verified the UUID.

## Phase 4: LangGraph + local MCP

The `/chat/ask` request now runs through a small LangGraph workflow:

1. **Prepare** resolves a follow-up question using the same bounded saved conversation history as Phase 3C.
2. **Retrieve** calls the read-only `search_course_documents` MCP tool. Its in-process MCP client/server uses the official MCP protocol without opening a network port or starting another Python process. Search remains scoped to the authenticated user's selected course. If MCP fails, the graph falls back to the same local Chroma search used before Phase 4.
3. **Generate** calls the existing Groq service using the retrieved PDF passages and conversation history. If answer generation is unavailable, the existing retrieval-only response behavior is preserved.

MCP tools cannot access arbitrary paths, run commands, or search another user's course. The API checks course ownership before the tool call and the tool checks it again at the data boundary. MCP and LangGraph run locally; they do not add hosting or usage fees. Groq and Supabase remain external existing integrations, so use only their available free usage and do not enable billing. The app must never switch to a paid service automatically.

### Install and run on Windows

From the project root, install backend dependencies into the existing backend environment:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Start the backend in one PowerShell window:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

Start the frontend in another PowerShell window:

```powershell
Set-Location frontend
npm run dev
```

Open the Vite URL printed in the terminal, sign in, open a course with an indexed PDF, and ask a question. The existing React API contract is unchanged. If needed, check `http://127.0.0.1:8001/docs` for the existing `/chat/ask` endpoint.

### Manual acceptance checklist

1. Ask a question answered by an indexed PDF; confirm the answer and its filename/page references appear.
2. Ask a follow-up using “it” or “that”; confirm the saved conversation context helps retrieve the right evidence.
3. Open a second chat in the same course; confirm it does not show the first chat's messages.
4. Switch courses; confirm retrieval only uses the selected course's PDFs.
5. Retry a completed request with the same request ID; confirm the saved response is returned without creating duplicate messages.
6. With MCP available, confirm normal answers succeed through the LangGraph workflow. If MCP is unavailable, confirm local retrieval fallback works.
7. Temporarily make the LLM unavailable or omit its key; confirm the API returns the existing retrieval-only behavior and no paid provider is contacted.

Do not publish this development API directly to a public network. Any future public deployment must first use a hosting option that meets the PKR 0 requirement and must not require a card or paid upgrade.
