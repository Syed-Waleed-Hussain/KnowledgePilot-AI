# Phase 7.6 — conversation continuity and free-tier reliability

## What was wrong

`chat_memory.retrieval_question` only detected pronouns and a few opening words. `in detail please` matched neither and was sent unchanged to vector search. The vector layer discards matches below 0.25 similarity; a vague query therefore can return no evidence. `please explain it in detail` matched `it`, explaining why similar wording took a different path. This code defect is confirmed; the original live PDF embeddings, provider response and logs were not replayed, so the precise similarity score and historical Groq failure are not claimed as measured.

The old failure path also returned before saving the student's message, the frontend cleared the pending request ID even for a failed result, and every non-generated response received the same AI-unavailable label. The Harness inferred some categories from text and replaced messages, losing details such as Retry-After. These were separate defects, not proof every failure was a Groq quota error.

## Continuity fix

Obvious follow-ups (detail, example, quiz, ordinal point, implicit pronouns) resolve deterministically against the latest explicit student topic. No Groq rewrite call is needed. Original wording stays in `content`; the separate `resolved_query` stores retrieval intent, not document facts. Saving that query keeps the topic available after a chain of vague requests outgrows the bounded model history. It is computed before Harness history truncation.

The retriever still goes through the scoped MCP tool. If the contextual query returns no passages, it tries the explicit topic alone once through the same ownership checks and tool budget. It never fabricates evidence or treats a previous generated answer as a source. Ordinal point labels from the latest answer provide intent only; fresh PDF evidence remains mandatory. With no reliable topic, the response asks for clarification. Empty retrieval after a contextual attempt has a distinct `context_retrieval` category.

Each request rechecks course ownership, and Chroma filters include owner and course. Session reads check session + course + owner. New Chat has no inherited context. RL remains off by default; even when enabled, a retrieval strategy cannot strip a resolved implicit topic.

## Durable failed turns and retry

Three additive columns on `chat_messages` preserve `request_id`, `resolved_query` and `failure_json`. Existing tables/records are not recreated or deleted. The original student question is stored before workflow execution. Failures update metadata; they do not insert a successful empty assistant answer. Successful completion inserts one assistant message and clears failure metadata atomically. Old successful answers replay by request ID without another model invocation.

The frontend reloads authoritative SQLite history after completion/failure and offers **Retry this question** using the same original message, session and request ID. Local connection failure also retains an optimistic question when the server has not received it. Refresh/reopen restores retry metadata. No provider-specific conversation is required. Administrator credential replacement cannot reset history.

An in-flight turn has a 120-second lease to reject simultaneous same-ID attempts. A crashed process leaves that saved question retryable after the lease expires. Groq Retry-After sets a persisted per-turn delay plus a shared SQLite provider cooldown, independent of credential selection. This is a small cooldown, not a queue or a distributed rate limiter.

Retrying an older failed turn uses its original resolved query and history before that turn; it cannot acquire a newer conversation topic. A recovered answer displays next to its original question, not after a newer turn. API callers who let the server create a session can retry with the returned session and request ID.

## Failure categories

| Category | Meaning / behavior |
| --- | --- |
| `context_missing` | No reliable topic; ask student to name one. |
| `no_evidence` | No matching PDF passages; no model call or quota reservation. |
| `context_retrieval` | Contextual and topic-only searches found no evidence; request explicit wording. |
| `rate_limit` | Groq organization-wide HTTP 429 or ongoing cooldown; honor Retry-After, never switch keys. |
| `provider_timeout`, `provider_connection` | Provider network failure; saved turn can be retried. |
| `provider_server` | Groq 5xx; manual retry later, no aggressive SDK retry. |
| `provider_auth` | Invalid/missing configured key; administrator must fix it. |
| `model_unavailable` | Missing/decommissioned/unavailable configured model; administrator action. |
| `provider_request`, `provider_response` | Rejected request or unreadable/empty output; never label empty output successful. |
| `budget`, `timeout` | Harness execution/model/tool budgets or deadline, separate from provider quota. |
| `app_quota` | Authenticated student's daily local allowance; HTTP 429 includes zero remaining and next UTC reset. |
| `mcp`, `internal`, `validation`, `invalid_quiz` | Tool/workflow/output-validation failures, distinct from absence of PDF evidence. |

For compatibility, a completed workflow with unavailable generation still returns the existing HTTP response envelope with `mode=retrieval_only`, `success=false`, `answer=null`, structured category and retry metadata. It is explicitly a failed answer. App-quota and turn-cooldown rejections retain HTTP 429. The UI displays the persisted failure on its original student turn rather than adding a generic AI-unavailable answer bubble.

## Quotas and credentials

Keep the actual existing configuration name:

```dotenv
MAX_AI_QUESTIONS_PER_DAY=10
GROQ_CREDENTIAL=primary
```

For local testing, explicitly set `MAX_AI_QUESTIONS_PER_DAY=30` in the private root `.env`, then restart FastAPI. This phase did **not** change the real `.env`, Groq key or existing usage rows. Default remains 10; zero/negative input cannot enable unlimited access. Invalid nonnumeric configuration fails startup rather than disabling quotas.

SQLite `daily_usage` counts unique requests reserved immediately before model execution, per verified user and UTC date. The first failed provider attempt still uses one app allowance; retrying its same request ID uses no additional allowance, including after restart. No evidence, missing context and preflight budget rejection do not reserve an AI question. A compare-plus-quiz request uses one app question but its two internal model calls each consume Harness budget and provider capacity. Historical reservation records are not refunded/reset/deleted. A UTC date rollover creates a new dated usage row; it does not clear the old one.

Groq limits are organization-wide, not per API key. Multiple keys from the same organization do not add capacity. Official reference: https://console.groq.com/docs/rate-limits

`load_groq_settings` is the small provider configuration abstraction. One credential is active. An administrator may optionally put `GROQ_REPLACEMENT_API_KEY` in the private backend environment and explicitly select `GROQ_CREDENTIAL=replacement` for legitimate credential recovery, then restart the process. Nothing switches automatically on 429, failed authentication or any other response. Shared cooldown remains active across replacement. No keys reach React or logs; no account/key creation or paid fallback was added.

## Markdown and source mapping

The existing safe React Markdown renderer is unchanged: no raw HTML. Cleanup removes lone trailing prose backslashes while preserving fenced code, Windows paths, inline math, math blocks and paired LaTeX slashes. It does not globally unescape backslashes. Only a trailing Sources/References block composed of numeric source-list entries is removed as redundant with the drawer; narrative references remain.

Inline citation markers normalize to the actual retrieved evidence order; unsupported IDs are rejected or removed. Structured quiz source IDs remain validated and receive the same safe Markdown cleanup. The drawer continues to use the exact bounded passages supplied to generation. Citation validity is not a claim of factual correctness.

## Files changed in this phase

- `backend/chat_memory.py`: deterministic resolution, saved-query continuation, owner-scoped restore and turn ordering.
- `backend/chat_turns.py` (new): persistence, same-ID lease, failure and completion helpers.
- `backend/provider_cooldown.py` (new): persisted shared Groq cooldown.
- `backend/course_store.py`: additive chat metadata columns.
- `backend/app.py`: persisted attempts, retry/replay, original-context retry, UTC app-quota messages/configuration.
- `backend/phase4_graph.py`: resolved query, bounded MCP fallback and categorized generation errors.
- `backend/agent_harness.py`: structured categories/Retry-After and retryability.
- `backend/answer_quality.py`: conservative Markdown/source-list cleanup.
- `llm_service.py`: explicit provider errors, manual credential selection and cooldown.
- `frontend/src/pages/Workspace.jsx`: persisted failed-turn UI and safe retry action.
- `.env.example`: documented quota/credential settings; no actual secrets changed.
- `tests/test_phase76.py` (new): synthetic conversation/provider/storage regressions.

## Verification and limits

All automated provider responses are mocked; no real Groq tokens are used. Phase 7.6 route tests execute real graph node functions with mocked MCP transport using an immediate coroutine driver because the sandbox stalls on the real MCP/async path. A focused Harness category test substitutes only the deadline context manager; real async cancellation is not thereby verified. These tests are not browser or live-provider acceptance tests.

The full verification script was attempted without excluding broken tests. It collected 158 tests at that point, passed the five basic tests, then stalled at the existing MCP protocol test and returned exit 1 after its 120-second limit. Dependency compatibility, 18 frontend render/navigation checks, logout regression and production build passed in that run. Existing Motion directive and bundle-size warnings remain. The full Phase 4–7 async suite is pending, not green.

Expanded focused run: **115 passed in 45.54 seconds**. This included Phase 7.6, all Phase 7 tests, Phase 6 unit tests, mocked Supabase auth, and explicitly selected synchronous Phase 4/4.3/5 regressions (formatting/citations, Harness limits/retries, quota idempotency and evaluation). This is a diagnostic subset, not a replacement for the blocked full suite. An earlier focused run passed 91 tests before the final additions. Existing regression test files were not edited in this phase to force green results. The older conversation regression's expectation of generation for a context-free pronoun request should be reviewed locally: the new required behavior asks for clarification instead of inventing a topic.

Final confirmation after all code edits: **25 Phase 7.6 tests passed in 29.77 seconds**. Python compilation and Git whitespace checks also passed; Git emitted line-ending warnings only.

## Local commands

From the project root, run synthetic verification:

```powershell
$env:KNOWLEDGEPILOT_STORAGE_PATH = Join-Path $env:TEMP ('kp76-tests-' + [guid]::NewGuid().ToString('N'))
& .\backend\.venv\Scripts\python.exe -m pytest tests/test_phase76.py tests/test_phase7.py tests/test_phase6.py backend/tests/test_supabase_auth.py -q
# Full suite, including actual MCP/async tests (no timeout imposed here):
& .\backend\.venv\Scripts\python.exe -m pytest tests backend/tests -v --tb=short
Remove-Item Env:KNOWLEDGEPILOT_STORAGE_PATH
```

Start the normal backend using existing data/settings:

```powershell
& .\backend\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

Second terminal:

```powershell
Set-Location frontend
node test-phase7.mjs
node --test test-auth.mjs
npm run build
npm run dev
```

For manual acceptance, repeat the exact five Job Design messages, refresh/reopen the conversation, New Chat, course switching, Sources drawer and retry after mocked/recoverable failure. Check that one failed question and at most one recovered answer appear. Verify student B cannot access A's course/session; inspect a provider-429 cooldown and the separate daily app-limit message. Confirm actual Lecture 13 retrieval and live provider availability separately. Restart the backend after configuration changes. Do not use existing student records for automated tests.

No deployment, data deletion, Supabase reset, database/environment recreation, RL training, new dependency, paid service, billing activation, key exposure, commit or push was performed.
