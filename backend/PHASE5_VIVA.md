# Phase 5 viva guide

## The flow

Student Question → Harness Checks → LangGraph → MCP Tool → Groq → Output Validation → Final Answer.

FastAPI first verifies the Supabase token, course owner and chat owner. The harness receives that verified identity, never an identity chosen by the model. The existing graph still prepares the question, retrieves evidence and generates the answer. Failed output is not saved as a successful chat answer.

## Concepts in simple English

1. **Agent Harness:** small controls around an agent run: permissions, limits, safe failures and output checks.
2. **LangGraph:** decides the order of workflow nodes. Our harness controls what those nodes may spend and whether their output passes checks. It is not a second graph.
3. **Tool execution budget:** the maximum number of tool attempts a request may make. Failed attempts count too. Discovery is not a tool execution.
4. **Context window:** the text the model can consider in one completion: instructions, question, history and evidence.
5. **Token budget:** a limit on pieces of text processed by a model. This project uses character caps rather than downloading a tokenizer. Characters divided by three is only an estimate, not an exact token limit, especially for non-English text. Instructions and serialization add overhead.
6. **Allowlist:** an explicit list of permitted operations. Only the implemented `search_course_documents` MCP tool is allowed. No shell, arbitrary URL, SQL or file tools are added.
7. **Retry:** one additional attempt after a safe temporary failure. Only read-only retrieval and model generation may retry. Each attempt consumes its own execution budget. Quota reservation and chat writes are never automatically repeated by the harness.
8. **Why never retry authorization errors?** Repeating a denied operation cannot grant permission and can increase information leakage and resource use. Missing accounts, foreign courses and invalid access are rejected before retrieval.
9. **Execution trace:** short records of steps, duration, status, call counts and error category. Traces contain no prompts, document text, account IDs, tokens or keys. They remain request-scoped in memory and the local API response; there is no external tracing service or growing log file.
10. **Citation validation:** checks that numeric references such as [1] point to passages actually supplied to this completion. It does not establish factual correctness or prove that a statement follows from a passage.
11. **Benchmark:** a repeatable collection of scenarios with expected outcomes. Synthetic fixtures avoid real students' documents.
12. **Deterministic evaluation:** ordinary Python checks produce the same result for the same output. Our checks cover evidence, numeric citation ranges, quiz fields/count and combined task sections. They use no judge LLM.
13. **Future reinforcement learning:** these measurements could help design a reward and compare policies later. Citation checks alone would be an inadequate factual-accuracy reward. This phase trains nothing and implements no RL.

## Files and functions

- `agent_harness.py`: `AgentRunContext` tracks request, verified identity, course, chat, elapsed time, status, tool/model attempts and safe trace events. `authorize` checks the allowlist and account/course ownership; the MCP server still independently enforces identity and course ownership. There is no document-ID tool; existing retrieval restricts documents through owner/course vector filters. `model` and `tool` permit at most one transient retry across a run. `run_graph` wraps the existing compiled graph and checks output before persistence.
- `bounded_context`: retains up to eight recent messages (4,000 characters), six passages (2,000 characters each), and an 18,000-character content envelope including the latest question and metadata allowance. The complete question is retained; FastAPI already caps it at 2,000 characters. Evidence gets priority, then recent history. Existing Phase 3C SQLite memory stays unchanged. System instructions remain separate from untrusted evidence/history in `llm_service.py`.
- `phase5_evaluation.py`: `evaluate_answer` checks evidence availability, numeric citation IDs, rendered quiz structure and combined comparison/quiz headings. It requires citations for successful grounded output. It records whether factual accuracy was evaluated (always false).
- `evaluate_phase5.py`: ten synthetic scenarios and a console table. Answers are mocked, not obtained from Groq. Temporary SQLite databases are separate from the application data. There is no live evaluation mode.
- `tests/test_phase5.py`: budget, permission, context, retry, timeout and output checks plus the offline scenario runner.
- `phase4_graph.py`: existing nodes call request-scoped controls when the API supplies a context. Legacy graph callers keep the original interface. Harness failures do not enter the legacy direct-retrieval fallback.
- `app.py` and `course_store.py`: integrate the wrapper, expose safe reliability/evaluation summaries and add a small quota-reservation table in the existing SQLite database. The same request key reserves daily quota once, including retries after failed output. A changed question using an already reserved key is rejected. Existing successful-answer replay remains intact. No second memory database is created.
- `llm_service.py`: rejects unsupported numeric citations before legacy formatting can remove them. Existing quiz JSON validation is reused.
- MCP test files: accept either the generic denial or its SDK-added `Error executing tool search_course_documents:` prefix, while retaining protocol error, no-leak and no-retrieval assertions.

## Defaults and configuration

Environment variables (no changes to `.env` are required):

| Variable | Default |
|---|---:|
| HARNESS_MAX_TOOLS | 5 |
| HARNESS_MAX_MODELS | 2 |
| HARNESS_SECONDS | 30 |
| HARNESS_MAX_RETRIES | 1 |
| HARNESS_HISTORY_MESSAGES | 8 |
| HARNESS_HISTORY_CHARS | 4000 |
| HARNESS_PASSAGE_COUNT | 6 |
| HARNESS_PASSAGE_CHARS | 2000 |
| HARNESS_CONTEXT_CHARS | 18000 |

Retries are capped at one even if configured higher. Provider 429 responses are never automatically retried: the UI receives a safe wait message. Provider attempts are separate from the daily per-question quota. A combined comparison and quiz normally needs both model slots, so there may be no room for recovery if one completion fails.

The orchestration deadline is cooperative. `asyncio.timeout` can cancel awaited orchestration, and boundary checks prevent new work after expiry. It cannot terminate an already-running synchronous SDK call or its worker thread. Groq retains its existing 30-second client timeout and disabled SDK retries. A discarded late completion is not saved as a successful answer.

## Validation commands (PowerShell, project root)

```powershell
& .\backend\.venv\Scripts\python.exe -m pytest tests/test_phase4.py::test_mcp_client_discovers_tool_executes_it_and_rejects_other_student tests/test_phase43.py::test_mcp_identity_boundary -q
& .\backend\.venv\Scripts\python.exe -m pytest tests backend/tests -q
& .\backend\.venv\Scripts\python.exe -m backend.evaluate_phase5
Push-Location frontend
npm run build
Pop-Location
& .\backend\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
# In another PowerShell window:
Invoke-RestMethod http://127.0.0.1:8001/health
```

Use the backend virtual environment: the root environment in this workspace lacks MCP and LangGraph. The sandbox could not complete a trivial asyncio subprocess; full async regressions and scenario scores must be verified locally. No scores are invented.

## Limits of this phase

- Citation validity is not semantic entailment or factual accuracy. Citation syntax validation covers numeric bracket references, not arbitrary prose references.
- The existing Groq quiz prompt generates five questions. Requests for other counts fail deterministic validation rather than silently being treated as completed.
- Completed-request replay remains the existing behavior. Concurrent identical requests can still duplicate provider work; the reservation table prevents duplicate daily quota charges, not concurrent completion calls. Reservation keys are retained in SQLite and may need a future retention policy.
- A provider failure after AI execution begins still consumes one daily question under the existing policy. Pre-AI authorization, no-evidence, and insufficient-budget rejections do not reserve quota.
- No frontend redesign was needed. Existing safe error rendering remains; the API additionally supplies reliability metrics.
- No deployment, paid package, paid judge, paid tracing, API call in evaluation, subscription or credit card was introduced. Development stays PKR 0; Groq's free allowance remains limited.

## Observed sandbox results

- Harness synchronous unit subset: **10 passed, 8 deselected** (5.67 seconds). Deselection here isolates synchronous checks; the complete suite remains available and is not marked skipped.
- Phase 4 deterministic/output subset: **15 passed, 10 deselected** (5.42 seconds).
- React production build: **passed**, with dependency directive and bundle-size warnings.
- Python source compilation: **passed**; Git whitespace check: **passed**.
- MCP prerequisite tests and full regressions were attempted but stalled in async execution and were interrupted. A standalone asyncio sleep also exceeded its 8-second subprocess deadline.
- Offline synthetic runner exceeded a 40-second deadline; no benchmark score is reported.
- FastAPI import/health smoke exceeded a 40-second deadline with isolated temporary storage; server startup was not verified.
- The root virtual environment attempt failed collection because MCP/LangGraph were absent. All subsequent Python commands used the existing backend environment; no installation was performed.
