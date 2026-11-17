# KnowledgePilot AI — Phase 7.5 readiness

Audit date: 16 November 2026. No deployment, account creation, migration, commit or push is authorized by this phase.

## Decision

Ready for continued local acceptance testing, **not cleared for public production**. No verified card-free hosted configuration preserves the current SQLite + Chroma + PDF architecture unchanged. Keep the existing local disk authoritative. Do not deploy these files onto ephemeral container storage and call that persistence.

## Architecture, in viva language

React is the interface. Supabase signs students in. Every private API request carries a bearer token; FastAPI asks Supabase `/auth/v1/user` to verify it, with a six-second timeout. The backend takes identity from that verified response, not a student ID supplied by the browser. A missing token fails closed. This is remote token verification, not merely decoding a JWT.

After login, Main Workspace offers Learning and Research. Hash routes preserve selected course/topic on refresh and browser navigation without server rewrites. Learning keeps existing courses, PDFs, citations and chats. Research adds separate owner-scoped topics, saved metadata, notes, search history and generated drafts in the same SQLite database. Returning to Workspace switches interfaces without changing identity. The UI component key now includes identity to prevent reuse of a previous student's component state.

LangGraph runs explicit workflow steps. Learning calls the official MCP document tools within a trusted user/course scope; MCP is not mounted as a public HTTP tool server. Research uses fixed public metadata endpoints and abstract evidence, not automatic PDF downloads or full-paper reading. Citations support checking sources but do not prove every generated statement true.

The Harness bounds tools, model calls, retries, history and evidence, checks resource ownership, records execution traces, and validates outputs. It is not a guarantee against hallucination. Synchronous work cannot always be forcibly interrupted by a cooperative deadline; provider timeouts still matter.

RL is a small contextual epsilon-greedy bandit choosing retrieval strategies, not training Groq or a neural language model. It uses coarse task/follow-up/query-length categories and synthetic offline rewards. It remains off by default. Real student interactions do not update the policy. Research does not silently join Learning RL.

## Integration and security findings

| Area | Finding / action |
| --- | --- |
| Ownership | Learning requires owner + course; research requires owner + topic/paper. Foreign IDs return unavailable. Route dependencies require verified auth. Direct function tests alone are not HTTP acceptance. |
| Logout | Fixed in-flight token refresh restoring a session after logout; local credentials now clear immediately. Regression test mocks a delayed refresh. Existing server token lifetime/revocation semantics still depend on Supabase; offline logout cannot guarantee immediate remote revocation. |
| Identity changes | Component remount includes verified user ID; route protection remains in place. |
| CORS | Added comma-separated exact `CORS_ALLOWED_ORIGINS`; loopback Vite remains supported. CORS is not authorization. Use only the eventual HTTPS frontend origin. |
| API address | Production no longer silently falls back to the visitor's localhost when `VITE_API_URL` is missing; administrator error is shown. |
| Upload rollback | ValueError during indexing now removes this attempted upload's partial vectors/file, matching general failure cleanup. Existing student records are not touched by this change. |
| Upload security | 5 MiB content read limit, PDF signature/type checks, UUID disk names, sanitized deletion basename. No public static PDF directory. Multipart parsing can spool before the route reads; an eventual proxy must also bound request bodies. PDF extraction CPU/page explosion is not fully bounded. |
| Providers | Groq has 30-second timeout and no SDK retries; shared local daily AI quota. Research has bounded responses, fixed endpoints, redirect rejection, persistent pacing and cooldowns. Provider-wide quotas can be exhausted across users. |
| Rendering | Markdown skips HTML, disallows images, limits URL schemes; external links use noopener/noreferrer. Existing loading/error states and responsive CSS retained. Visual mobile/browser acceptance pending. |
| Secrets | Root dotenv loads without overriding host variables. Frontend receives public Supabase settings only; Groq key remains backend-only. No secret values printed during audit. |
| Logging | Existing Uvicorn access logs and Harness traces are available. Do not log tokens, request bodies, notes or PDF content. Access URLs may contain resource IDs; restrict log access/retention. No centralized production alerting established. |
| Errors | Auth/provider/Harness failures use safe messages. Unexpected infrastructure failures still require server logs and proxy handling; health is liveness, not proof all external providers are available. |
| Git | Ignore rules extended for PDFs, SQLite variants, DB journals, upload/vector/cache directories and venv. Tracked-file pattern check found only env examples, no tracked PDF/database/env secrets. Ignore rules do not remove historical secrets; a full Git-history credential audit was not performed. |

## Current free service feasibility

Official documentation was read on the audit date. Limits can change; account-specific onboarding/card requirements must be checked again without accepting payment. A quoted free allowance is not unlimited or a lifetime promise.

| Component / option | Published limits and payment constraints | Decision |
| --- | --- | --- |
| React: Cloudflare Pages | Product page says no credit card required. Free: 500 builds/month, one concurrent build, 20-minute build timeout, 20,000 files, 25 MiB/file. Provider pages.dev URL means no purchased domain needed. Static hosting runs no embedding CPU or persistent backend process. | Suitable frontend candidate only. |
| FastAPI: Render Free | 512 MiB RAM, 0.1 CPU on pricing; sleeps after 15 idle minutes, cold start; 750 instance hours/workspace/month. No persistent disk. Free Postgres expires after 30 days. Bandwidth/build quotas also apply; services can suspend without a payment method. Onboarding verification may still request a card: reject if required. | Cannot host current persistent app safely; PyTorch/embeddings also need measured memory well above a comfortable 512 MiB budget. |
| Hugging Face Spaces | Current docs say creating Docker/Gradio compute Spaces requires paid PRO/Team; CPU Basic resource table lists 2 vCPU, 16 GB RAM, 50 GB ephemeral disk. Free ZeroGPU Gradio eligibility does not establish compatibility with this FastAPI service. | Do not repeat the old claim that a new Docker Space is card-free. Rejected for this plan. |
| Existing Supabase Free Auth | 50,000 monthly active users; Free project has shared CPU/500 MB RAM, 500 MB database, 1 GB object storage, 5 GB egress plus 5 GB cached egress; 2 active projects, pause after one inactive week. Existing free auth does not provide an OS disk for SQLite/Chroma. No paid upgrade or new project created. Reconfirm card-free signup before any future account creation. | Continue existing auth; storage/Postgres are only future alternatives, requiring approved migration. |
| Local Chroma + sentence-transformers | CPU inference, model download/cache and in-memory model/index costs. No external embedding bill. Free static hosts cannot execute it. | Retain locally pending a durable backend decision and measured peak RAM. |
| PDFs | Existing local disk persists; Supabase private object storage could hold a future bounded corpus, with authenticated access, RLS and egress limits. At 5 MB/file, 1 GB is only roughly 200 files before overhead/other usage. | Do not move files now; do not use public buckets. |
| arXiv | Public metadata API; terms require at least three-second pacing, one connection and caching. No paid API selected. | Existing bounded, manually triggered search is appropriate; live reachability still pending. |
| Semantic Scholar | Primary product URL returned HTTP 403; official webflow documentation was discoverable and lists 1,000 requests/second shared across all unauthenticated users, introductory API keys 1 request/second. Shared capacity is not a personal allowance. No key requested or card eligibility verified. | Optional only; no availability promise or paid fallback. |
| Groq Free | Existing account/key unchanged. Rate-limit table lists gpt-oss-20b at 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD; actual organization limits are authoritative. Developer upgrade is separate. | Remain on Free; verify dashboard allowance before acceptance. Quotas are shared, not per student; local 10/day cap cannot guarantee provider capacity. |

An 8 GB laptop has durable disk, model cache and substantially more memory than a 512 MiB service, although Windows also consumes RAM. Measure peak RAM during indexing and simultaneous requests; successful local execution does not establish free-host compatibility. Use a single backend worker initially; each worker loads its own model. Do not use account cycling, keep-alive pings or public dataset repositories as private database substitutes.

Sources:

- https://www.cloudflare.com/products/pages/
- https://developers.cloudflare.com/pages/platform/limits/
- https://render.com/docs/free
- https://render.com/pricing
- https://render.com/docs/compute-plans
- https://huggingface.co/docs/hub/spaces-overview
- https://huggingface.co/docs/hub/spaces-storage
- https://supabase.com/pricing
- https://supabase.com/docs/guides/platform/billing-on-supabase
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/billing-faqs
- https://info.arxiv.org/help/api/tou.html
- https://webflow.semanticscholar.org/product/api

## Persistence plan — no migration performed

The authoritative root is `backend/storage_phase3` unless `KNOWLEDGEPILOT_STORAGE_PATH` overrides it. Preserve the whole root: SQLite metadata including users, courses, documents, chats, quotas, research tables and policies; Chroma collection/index; uploaded `documents/*.pdf`. Keep model identity/chunking configuration with a backup. Chroma can be rebuilt from PDFs, but private notes/chats cannot be recovered from embeddings.

For a future backup, stop writes and the backend before copying the entire root to a private second disk. Alternatively use SQLite's backup API plus a coordinated vector/PDF snapshot. Copying only a live SQLite main file can omit journal/WAL data. Validate restore on a separate directory, compare counts and checksums, and verify two-user isolation; never restore over the original as a test. This phase neither copied nor migrated actual student data.

Smallest architecture-preserving PKR-0 option: continue on the existing local machine for supervised acceptance/demo, with private local backups. This uses already-owned hardware/internet and has power/availability limits; it is not verified always-on cloud hosting or guaranteed zero electricity cost. A free frontend alone does not make the backend publicly reachable.

If a fully hosted service is mandatory, the smallest candidate adjustment is a separately approved migration to the existing Supabase project's bounded Postgres/private object storage and durable vector storage, keeping the UI, auth, LangGraph and Harness. This still needs a card-free compute option and embedding-memory proof. It is a proposal, not an approved implementation or a verified complete deployment configuration. Do not upload a live SQLite file to object storage and overwrite it after requests; that loses concurrent writes and is not a database.

## Verification commands

Observed in this session:

- Focused `test_phase7.py`, `test_phase6.py`, `test_supabase_auth.py`: **67 passed**, 47.01 seconds. Providers/models mocked, SQLite temporary.
- Existing frontend render/route suite: **18 passed**; production build passed. Existing Motion directive warnings and a bundle above 500 kB remain.
- New delayed-refresh/logout regression: **1 passed** (rerun after the final auth edit).
- New partial-index rollback regression: passed individually in a two-test diagnostic run; cross-student route test then stalled. Do not count the diagnostic run as a completed suite.
- `pip check`: no broken requirements. Python compilation and `git diff --check`: passed (Git emitted line-ending warnings).
- Full initial backend attempt stopped after five passes when progress stalled. The bounded verbose verification attempt collected 139 tests and stalled at `test_mcp_client_discovers_tool_executes_it_and_rejects_other_student`. The entire suite is not verified. No async/MCP tests were removed or marked skipped to obtain green results.
- The complete verification script returned **exit 1**: backend timed out after 120 seconds; dependency check, 18 frontend checks, logout regression and final production build all passed. The final bundle was 584.91 kB (182.76 kB gzip); warnings remain visible. The separate cross-student route diagnostic was interrupted after stalling; it is pending, not passing.
- Authenticated HTTP/browser, live Groq/research calls, mobile visual QA, memory profiling, restart/restore acceptance and remote token-revocation behavior remain pending. No live student data or credentials were used for testing.

Run from the repository root in PowerShell, using the existing environment:

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\verify_phase75.py
```

The script runs every backend phase including ownership tests, dependency compatibility, frontend navigation checks, the logout race test and production build. It always uses a unique temporary storage root; keeps test files for inspection; returns nonzero on failure or timeout. It does not exclude async tests. The backend step times out after 120 seconds so sandbox hangs are reported rather than presented as passes. Slow local runs can use the unbounded diagnostic command below:

```powershell
$env:KNOWLEDGEPILOT_STORAGE_PATH = Join-Path $env:TEMP ('kp-final-' + [guid]::NewGuid().ToString('N'))
& .\backend\.venv\Scripts\python.exe -m pytest tests backend/tests -v --tb=short
& .\backend\.venv\Scripts\python.exe -m pip check
Remove-Item Env:KNOWLEDGEPILOT_STORAGE_PATH
```

For manual acceptance, start the backend with a separate temporary storage root as above and existing auth/key settings, then in a second terminal start Vite:

```powershell
& .\backend\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
# Second terminal, from project root:
Set-Location frontend
npm run dev
```

Use two existing approved test identities, not real student records. Check login, workspace selector, create a synthetic course/PDF/chat, citation links, research topic/discovery/save/note/draft/export, return to Workspace, refresh both deep links, browser Back/Forward, logout and Back. Student B must not see A's lists and must receive unavailable for A's course/topic/paper/document/chat identifiers. Unauthenticated HTTP requests must receive 401. Test invalid/expired tokens, 5 MB overflow, provider 429/timeouts, narrow 375 px layout, keyboard focus and Markdown links. Never paste a bearer token into a shared transcript. Email confirmation redirects need Supabase Site URL/allowlist for the eventual origin; current password flow is direct REST, not OAuth callback handling. Do not assume a confirmation link signs the user in automatically.

## Phase 8 proposal — only after acceptance

1. Resolve all full-suite hangs/failures locally; record authenticated HTTP/browser evidence and measure peak RAM.
2. Choose between supervised local operation and separately approved persistence adjustment. Recheck no-card terms and durable storage first; stop if a payment method is required.
3. Review a concrete backup/restore and owner mapping plan before any migration. Prove restore on a copy and obtain separate migration authorization.
4. After deployment authorization, set production `VITE_API_URL` to HTTPS and rebuild; set exact backend CORS origin and Supabase Site URL/redirect allowlist. Do not publish secrets or PDFs.
5. Configure body limits, one worker, private logs, timeout behavior and bounded provider quotas. Recheck dependencies using the existing lockfile/environment; broad Python ranges are not a reproducible production lock.
6. Deploy only the approved configuration, then repeat cold-start, restart/persistence and two-user security acceptance. A deployed landing page is not evidence that the full app works.

No paid services, keys, accounts, resets, migrations, commits or pushes were used in Phase 7.5.
