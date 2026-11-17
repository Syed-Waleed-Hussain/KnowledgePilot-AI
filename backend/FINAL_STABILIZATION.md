# University demonstration stabilization

No deployment, credentials change, data migration/deletion, framework, UI redesign, commit or push.

## Reproduced causes

1. **Research:** arXiv received `all:"Digital Learning for Special Need Childrens"` or the entire healthcare title as a single exact phrase. This is much more restrictive than an academic keyword search. Positive and empty parsed feeds were both cached for one hour. Provider exceptions were already excluded from the cache; the defect was reusing valid-but-overrestrictive empty searches, not evidence that HTTP failures had been cached. arXiv failure also stopped discovery before the optional second provider could run. The UI presented partial failures alongside a plain zero-results count.
2. **Exam preparation:** the exact sentence is not classified as a structured quiz by the existing evaluator. It contains `these`, so with previous Job Design context its retrieval query was rewritten toward Job Design. The app separately retrieved both PDFs only for comparison-plus-quiz requests, leaving ordinary study plans dependent on a pooled search. An uncited synthetic plan reproduced the generic validation rejection; the same plan with valid evidence citations passed without quiz/table headings. The historical screenshot's exact missing/invalid citation condition and Semantic Scholar HTTP status cannot be reconstructed without its original execution trace. They are not claimed as observed.
3. **Errors:** the Harness discarded validation diagnostics and retrieved passages when replacing the output with a generic failure. Workspace displayed the internal category prefix before the message. Research did not distinguish all-providers-down from a successful empty search clearly enough.

## Minimal changes

- Normalize obvious wording (`special need childrens`, `health care`, `agentic AI`) in search requests only; preserve topic titles and saved libraries.
- Use encoded arXiv keyword AND queries, relevance sorting, and at most one limited alternate query for the reported topic patterns after a valid empty feed. Wait for pacing while retaining the existing provider lease; never alternate after a provider failure or HTTP 429.
- Use a new cache namespace for changed query semantics. Successful papers cache for one hour; genuine empty feeds for one minute. Exceptions are not cached. No manual cache or student-record deletion was performed.
- Report each selected provider as results/empty/unavailable/rate-limited. A failed primary does not hide a successful optional secondary. All-provider failure is explicit, not a successful zero-results search or successful search-history entry.
- Scope study-plan retrieval to the explicitly named PDFs, or the two indexed course PDFs for “these two lectures.” Retrieve up to three genuine excerpts per document through the same owner/course-scoped MCP callback. Broad study overviews use nonnegative similarity within those document filters; topical question thresholds are unchanged. More than two ambiguous PDFs require clarification.
- Keep study-plan generation as prose, with evidence from each available lecture and an explicit excerpt-coverage limitation. Do not inject quiz keywords into that generation prompt, since the existing LLM helper uses those keywords for structured-output selection.
- Preserve validation reasons (`missing_citations`, `unsupported_citations`, `missing_lecture_citations`, incomplete output, invalid quiz structure). Never fabricate missing citations or automatically spend another Groq call to repair them. Retain retrieved passages and actionable retry messages when validation fails.
- Reject unsupported standard/alternate numeric citation markers before formatting cleanup can hide them. Keep the existing safe Markdown renderer and source drawer.
- Hide developer category prefixes in Workspace. Keep existing saved-turn retry identity and quota protections.

Official query syntax reference: https://info.arxiv.org/help/api/user-manual.html

## Files changed in this stabilization

`backend/app.py`, `backend/phase4_graph.py`, `backend/phase5_evaluation.py`, `backend/agent_harness.py`, `backend/research_providers.py`, `backend/research_graph.py`, `backend/research_api.py`, `backend/answer_quality.py`, `llm_service.py`, `frontend/src/pages/Research.jsx`, `frontend/src/pages/Workspace.jsx`.

Added `tests/test_stabilization.py`, `scripts/verify_demo.ps1`, and this report. Existing uncommitted work was preserved.

## Checks and limits

- Initial focused run: **105 passed**, synthetic storage, mocked Groq/research responses. This covered initial stabilization cases plus Phase 7.6, Phase 7, Phase 6 unit and Supabase-auth tests.
- Frontend render/navigation: **18 passed**; logout race: **1 passed**; production build passed. Existing Motion directive and bundle-size warnings remain.
- Python compilation and Git whitespace checks passed; line-ending warnings remain.
- Final `scripts/verify_demo.ps1`: **exit 0**, **109 backend tests passed in 131.28 seconds**, **18 frontend checks passed**, **1 logout regression passed**, production build passed. This includes the real LLM helper with a mocked SDK response to prove the study-plan prompt does not select structured quiz output. Build bundle: 586.16 kB, 183.17 kB gzip; existing warnings remain.
- One real arXiv request was attempted: `all:agentic AND all:healthcare`, at most two results, ten-second network timeout. It failed DNS resolution (`getaddrinfo failed`, errno 11001), before any HTTP response. No live papers or provider HTTP success are claimed. It was not repeatedly attempted. Reading official web documentation is not an API-connectivity test.
- No real Groq tokens were used. Historical screenshot outputs were not replayed against the student's actual records.
- The real MCP/async suite was previously blocked at its protocol test in this sandbox and was not repeatedly relaunched. New route tests use actual graph-node logic with mocked transport and an immediate coroutine driver; deadline diagnostics use a mocked timeout context. These do not establish real MCP transport, cancellation or authenticated browser acceptance.
- Live login, uploads, actual Lecture 13/15 coverage and provider availability still require the student's local acceptance run. A free provider can be unavailable or return genuinely zero matching papers, particularly for education topics outside arXiv's strongest coverage. Results are never invented to make a demo appear successful.

## Three local commands

From the project root, backend terminal (explicitly keep RL off):

```powershell
$env:RL_MODE = 'off'
& .\backend\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

Frontend terminal:

```powershell
npm --prefix frontend run dev
```

Verification terminal:

```powershell
& .\scripts\verify_demo.ps1
```

The verification script creates unique temporary storage, restores the terminal's prior storage/RL settings afterward, fails on a failed check, and makes no live provider calls. It deliberately reports focused verification rather than claiming the blocked full async suite passed. It uses the existing environment and installed dependencies.

## Five-minute demonstration

Before class, run the verification script, then manually check sign-in, actual lecture retrieval and provider availability on the student's network. Keep an already verified, genuinely discovered paper saved for an honest fallback if the provider is unavailable; distinguish saved/cached metadata from a fresh search.

| Time | Demonstration |
| --- | --- |
| 0:00–1:00 | Sign in → Main Workspace → Learning. Open the demonstration course. Show the two lecture PDFs, upload one small PDF if needed, and ask a short question. |
| 1:00–2:00 | Ask “Define Job Design,” then “in detail please.” Open Sources and show the actual excerpt/page. |
| 2:00–3:00 | Ask “make a quiz for this topic.” Refresh/reopen the same chat to show persistence. |
| 3:00–4:00 | Ask “Please tell me how I can prepare for the exam of Lecture 13 and Lecture 15.” Show evidence from both PDFs and the excerpt-coverage note. |
| 4:00–5:00 | Back to Workspace → Research. Discover papers for an academic query, inspect an actual provider link and save one. If the provider fails, show its explicit status and the previously saved genuine paper; do not claim a live search succeeded. |

All work stayed at PKR 0. Authorization, owner scoping, quotas, LangGraph/MCP, saved conversations and the two environments remain in place. Actual student records were not used as automated test fixtures.
