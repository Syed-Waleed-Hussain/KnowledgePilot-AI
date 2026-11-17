# Phase 4.2 verification notes

## Confirmed execution blocker
A minimal `asyncio.run(asyncio.sleep(0))` was run with an eight-second faulthandler timeout. It failed before the coroutine ran. The actual stack was:

```
socket.accept
socket._fallback_socketpair
asyncio.proactor_events._make_self_pipe
asyncio.windows_events.ProactorEventLoop.__init__
asyncio.runners.Runner._lazy_init
```

This establishes a Windows sandbox loopback socket-pair blocker before MCP initialization. It does not establish an MCP SDK deadlock. Do not replace the protocol with a direct function call or disable event-loop internals to work around it.

## Async tests
The route is async and returns a coroutine when called directly. Existing tests attempted to serialize that coroutine. The direct route test adapter now awaits it through asyncio.run, and conversation tests do the same. These tests still require a functioning event loop; their previous seven failures cannot yet be reported as passing here.

Async means a function can pause while waiting. Await waits for its result while allowing other work on the loop.

## MCP and graph
A real MCP call initializes a client/server session, discovers tools, sends tool arguments and receives a protocol response. The installed implementation uses MCP 2.3.0 with in-process transport and legacy initialization. The compiled LangGraph has prepare, retrieve and generate nodes connected in order. Compilation is not proof of successful execution. No completed execution trace is available from this repair run.

## Quiz root cause
The existing Markdown normalizer recognizes answer labels only at the beginning of plain lines. Bold inline Answer and Explanation labels remain in question text, while placeholder sections are added later. Structured question generation and validation are still required; do not claim this defect is repaired.

## Security
The API obtains identity from Supabase verification and checks course/session ownership. Retrieval filters by user and course. MCP also checks course ownership. End-to-end protocol isolation still requires a completed test.

## Remaining work
Structured quiz validation, combined comparison and quiz nodes, real protocol tests, completed regression run, HTTP startup, React verification and one bounded live provider request remain outstanding. Phase 4.2 is incomplete.

## Phase 4.3 changes and local verification

New quiz responses are requested as JSON using ordinary prompt instructions, without assuming provider JSON mode support. The validator requires five distinct questions, four distinct nonempty options A-D, one valid answer, one explanation and valid current source IDs. Invalid responses return an actionable error. There are no automatic provider retries. Valid JSON preserves escaped backslashes; Markdown output does not rewrite equations. Only explicit simple arithmetic is checked.

The legacy formatter recognizes bold inline labels before parsing and preserves valid answer/explanation fields instead of replacing them with old placeholders.

Combined requests resolve two documents by filenames in the current request or recent student messages. A course containing exactly two PDFs is unambiguous. Otherwise the API asks for filenames. Retrieval searches each document separately with user/course/document filters. The graph calls comparison generation and quiz generation separately and records each real operation. The comparison explicitly limits coverage to retrieved excerpts. Both calls share one user-request quota reservation; at most two model calls occur, without retries.

The two operations are simple functions inside the generate node, not separate autonomous agents. MCP uses official in-process protocol transport with explicit legacy initialization and a 15-second read timeout. This is not direct Python tool dispatch. The current test provides a 30-second async timeout for session lifecycle and graph execution; a blocked event-loop constructor itself cannot be interrupted by that timeout.

Run from the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_phase43.py -q -s
.\backend\.venv\Scripts\python.exe -m pytest tests/test_phase4.py backend/tests tests/test_basic.py -q
```

The first command should report eight passed and print a genuine metadata-only trace from its completed real MCP/graph test. No trace is recorded here because the sandbox cannot execute asyncio. The second command reruns existing regression and Phase 4 checks. Student reported 21 backend regression tests passed before these changes; rerun after this change.

Current sandbox result: seven Phase 4.3 pure tests passed; eight existing focused output/auth/ownership tests passed. Runtime MCP and graph tests remain locally required. The integration test uses a temporary SQLite ownership database and synthetic evidence returned by an injected retrieval callback. It exercises real MCP and graph execution, but does not independently verify Chroma embeddings or PDF extraction; existing backend tests cover those separately.

No completed trace is claimed. Phase 4.3 remains pending local runtime results.

## Phase 4.4 authorization repair

User-provided local results before this repair: Phase 4.3 eight passed with a completed real MCP/graph trace; the other suite had 41 passed and one failed.

Root cause: the failing test expected a Python exception. MCP 2.3.0 returns tool execution failures as CallToolResult with is_error=True (wire alias isError). Its ToolError class explicitly documents this behavior. Unexpected ValueError is wrapped as UnexpectedToolError and logged with a traceback. Expected authorization failures now raise ToolError with one generic message, avoiding a traceback and disclosing neither private course existence nor content.

Each MCP server now requires trusted_user_id, bound from the route's verified user through graph state. The tool rejects a mismatching user argument before searching. The browser and LLM do not establish this identity. MCP remains local/in-process and is not an independently authenticated public service.

The repaired test checks the actual protocol result, isError, safe message, absence of private evidence, and that search ran only for the authorized call. A new temporary-database test covers both owners' successful access, cross-course requests, spoofed identity, missing courses, no retrieval on denials, and absence of private filenames/passages/document IDs/paths in full serialized error results.

Current repair-run synchronous checks: 15 passed, 10 deselected. Async tests were intentionally not rerun in the known incompatible sandbox. No new successful runtime result is claimed.

Run locally in order:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_phase4.py::test_mcp_client_discovers_tool_executes_it_and_rejects_other_student -q -s
.\backend\.venv\Scripts\python.exe -m pytest tests/test_phase43.py tests/test_phase4.py backend/tests tests/test_basic.py -q
```

Expected collected total after the added identity test is 51 tests, all passing. This is an expectation, not an observed result. Phase 4 closure awaits these local results.

Viva: MCP returns a failed tool result rather than necessarily raising a Python exception. We check that failure flag, verify no private content is returned, and bind the server to the authenticated student so changing a user ID cannot impersonate another account.
