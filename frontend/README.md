# KnowledgePilot AI frontend

React/Vite frontend for the local KnowledgePilot API with Supabase Auth sign-in. Node.js 20.19+ or 22.12+ and npm are required.

## Local setup (PowerShell)

```powershell
cd "D:\Fast University\Semester no 07\Agentic AI\Project\frontend"
Copy-Item .env.example .env.local
# Edit .env.local and set the Supabase project URL and public key.
npm install
npm run dev
```

Run FastAPI in another PowerShell window using the existing environment:

```powershell
cd "D:\Fast University\Semester no 07\Agentic AI\Project"
.\backend\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

Build the frontend with:

```powershell
cd "D:\Fast University\Semester no 07\Agentic AI\Project\frontend"
npm run build
```

## Pages

- **Landing:** existing product introduction and feature overview.
- **Sign in / Create account:** Supabase Auth email/password flow.
- **Dashboard:** authenticated student's courses, course limits and account controls.
- **Study workspace:** that student's PDFs, persistent chat history, citations and course-isolated RAG.

## Notes and limits

- Set the browser values in `frontend/.env.local`; configure the same URL and public key in the root `.env` for backend token verification. Restart Vite after changing local variables.
- The frontend uses Supabase's documented Auth HTTP endpoints because the package registry was unavailable; Supabase handles passwords and issues/refreshes tokens. FastAPI verifies every token through Supabase before it reads private data.
- This is a local single-user-per-account prototype, not a hardened public service. PDFs, SQLite records, and Chroma vectors stay on this computer.
- Prototype limits default to 3 courses/student, 5 PDFs/course, 5 MB/PDF, 10 AI questions/day, and 2 simultaneous PDF processing jobs.
- Existing ownerless legacy course data stays hidden until explicitly assigned. No real signup/login test can run until valid Supabase project settings are entered.
