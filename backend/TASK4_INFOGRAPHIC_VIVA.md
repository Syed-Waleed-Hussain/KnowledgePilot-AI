# Task 4 viva: Grounded educational infographics

## What the feature does

A signed-in student can ask the Learning Environment for a visual study aid in
two ways:

1. Type an explicit request such as `Make an infographic about Job Design`,
   `Explain KV Cache visually` or `Compare job rotation and job enlargement`.
2. Press the visible **Generate Infographic** button beside the composer.

The request reuses the existing course/document ownership checks, the existing
LangGraph retrieval graph, the MCP document-search tool, and the existing daily
student and Harness limits. The answer is built only from retrieved course PDF
passages and is saved in the existing conversation history, so a refresh
restores the same card.

## Request flow

```text
React (typed prompt or button)
  -> POST /chat/ask            (explicit infographic wording)
   or POST /chat/infographic   (button / forced mode)
  -> FastAPI ownership + quota checks (unchanged)
  -> LangGraph prepare -> retrieve (MCP) -> generate
       answer_callback = create_infographic_answer
  -> validate schema + source IDs
  -> save chat_messages role='infographic' (structured JSON + sources)
  -> React renders InfographicCard (text only, no generated HTML)
```

`/chat/ask` detects explicit visual intent with `detect_infographic_intent`.
`/chat/infographic` forces infographic mode even if the wording does not repeat
the word "infographic". Both routes call the same `_answer_question` handler,
so there is no second chatbot or second retrieval system.

## Structured output

The model may return only one JSON object:

```json
{
  "title": "...",
  "layout": "overview | process | comparison",
  "introduction": "...",
  "sections": [{ "heading": "...", "body": "...", "icon": "...",
                 "definition": "...", "example": "..." }],
  "steps": [{ "title": "...", "detail": "...", "icon": "..." }],
  "columns": [{ "title": "...", "points": ["..."] }],
  "similarities": ["..."],
  "differences": ["..."],
  "takeaways": ["..."],
  "source_ids": [1, 2]
}
```

`backend/infographic.py` rebuilds the object from allow-listed fields instead
of trusting the model. It enforces counts, text lengths, allowed layouts and
allowed icon names. `source_ids` must be 1-based numbers that exist in the
passages retrieved for that request. Invalid JSON, a wrong layout, a missing
section or an out-of-range source is rejected with category
`invalid_infographic`; nothing is saved as a successful infographic and the
frontend offers a retry.

Text is cleaned of HTML tags, script/style blocks, control characters and
`on*=`/`javascript:` patterns. The React renderer uses ordinary text nodes and
Lucide icons. It never uses `dangerouslySetInnerHTML` and never executes
model-generated HTML, CSS or JavaScript.

## Layouts

- **Overview** - grounded introduction, 3-6 colourful concept cards with icon,
  definition and example when supported, then key takeaways.
- **Process** - grounded introduction, 3-6 numbered steps joined by arrows,
  optional key-concept cards, then key takeaways.
- **Comparison** - grounded introduction, 2-4 comparison columns with short
  points, similarities, differences, optional key-concept cards, then key
  takeaways.

All layouts show a verified-source list using the filenames and page numbers
that were actually retrieved. No public PDF URL is exposed.

## Persistence and ownership

No new table or migration was added. An infographic is a row in the existing
`chat_messages` table with role `infographic`; its `content` is the validated
JSON and `sources_json` is the retrieved source list. `load_history` adds a
parsed `infographic` field only for that role, and malformed legacy text stays
inert. The frontend normalizes the restored object again before rendering.
Cross-student isolation is the same as normal chat: session, course and user
are all checked by the backend.

## Exports

- **Download PDF** reuses the dependency-free A4 writer from Task 3
  (`frontend/src/services/researchPdf.js`). The PDF includes KnowledgePilot
  branding, the infographic title and layout, concept cards, process arrows,
  comparison columns, similarities/differences, takeaways, verified references
  and `Page X of Y` numbers.
- **Copy summary** copies a plain-text version of the same visible content,
  including references.
- **PNG export is intentionally not implemented.** It is the only omitted
  optional export, which keeps the task at PKR 0 with no canvas/image
  dependency. The documented fallback is Download PDF.

## Validation results actually executed

```powershell
# Backend: new Task 4 tests
backend\.venv\Scripts\python.exe -m pytest tests\test_infographic.py -q
# 12 passed

# Backend: full suite (Tasks 1-4 together)
backend\.venv\Scripts\python.exe -m pytest tests -q
# 175 passed in 161.76s

# Frontend: new Task 4 render/normalization/PDF tests
cd frontend
node test-infographic.mjs
# 12 focused infographic checks passed

# Frontend: Task 1-3 regressions
node test-research-output.mjs      # 10 passed
node test-research-notes.mjs       # 10 passed
node test-phase7.mjs               # 18 passed
node test-auth.mjs                 # 1 passed
node test-research-pdf.mjs         # 16 passed

# Production build
npm run build                      # built successfully
```

Groq, MCP transport, embeddings and academic providers are mocked. No live
Groq tokens, paid image API, remote image URL, subscription, GPU or new hosted
service is used. The in-app browser was not used for authenticated end-to-end
click testing; the tests above are automated rendering, route, service and PDF
checks, not proof of live browser interaction.

## Honest limitations

- Model output is validated for structure and source numbering, but citation
  validity is not factual proof; the student must still check the cited page.
- A very large topic may be rejected so the card stays readable.
- PNG export is omitted as described above.
- The development environment is a local prototype; deployment hardening is a
  separate concern.
- Existing uncommitted work was preserved. Nothing was committed or pushed.
