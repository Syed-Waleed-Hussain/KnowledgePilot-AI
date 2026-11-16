# KnowledgePilot AI

KnowledgePilot AI is a local study workspace for asking questions about course PDFs. The current app uses a React/Vite frontend and a FastAPI backend. SQLite stores course, document, and chat metadata; ChromaDB stores document vectors under `backend/storage_phase3/`.

## Current workflow

Chat requests pass through a LangGraph workflow: prepare the question with bounded conversation history, retrieve evidence through a local read-only MCP document search tool, then generate an answer with the existing Groq integration. If MCP is unavailable, the graph falls back to the same local Chroma retrieval path. PDF passages remain the source of factual answers, with existing references preserved.

The local MCP client and server use the official MCP protocol in process. This requires no MCP hosting, network port, or separate process. MCP and LangGraph do not add hosting charges. Groq and Supabase are existing external integrations; use only available free usage and never enable billing or paid upgrades. If the LLM is unavailable, the API returns retrieved evidence with a retrieval-only response.

## Windows setup

Use the project's existing Python 3.12 environment. From the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Configure the project-root `.env` with your own Groq key and, if using sign-in, Supabase project URL and public/anon key. Keep `.env` private; do not put secrets in frontend files or `.env.example`.

Start the backend in a PowerShell window:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

Start the frontend in a second PowerShell window:

```powershell
Set-Location frontend
npm run dev
```

Open the Vite URL shown in the terminal, sign in, select a course with an indexed text-based PDF, and ask a question. API documentation is available locally at `http://127.0.0.1:8001/docs`.

## Notes

- Default limits: 3 courses per account, 5 PDFs per course, 5 MB per PDF, and 10 AI questions per day.
- Scanned PDFs are not OCR-processed.
- Supabase is used for authentication; course data and PDFs remain local.
- Do not expose the development API directly to a public network.
- See [backend/README.md](backend/README.md) for the Phase 3C/4 details and manual acceptance checklist.
- The original Streamlit prototype remains in `app.py`; it is not the current React/FastAPI launch path.
