# KnowledgePilot AI frontend — viva notes

## The basics

- **React** is a JavaScript library for building interfaces from reusable pieces.
- **Vite** runs the local development server and packages the website for production.
- A **component** is a function that returns part of the page, such as `Landing` or `Workspace`.
- **Props** are values passed from a parent component. Here, `navigate` lets each page request a screen change.
- **State** is information that can change while the page is open. The workspace uses state for messages, selected file names, and loading.
- **CSS** controls colors, spacing, layout, and responsive behavior. CSS variables in `:root` keep the palette consistent.

## How the interface works

- `App.jsx` chooses between landing, dashboard, and workspace with a small `page` state value. It passes the selected course ID to the workspace.
- `styles.css` contains the visual system and media queries for tablet and phone layouts. Hover rules use CSS transforms and transitions to lift cards and give buttons quick feedback.
- **Motion for React** animates parts of the page using simple properties such as opacity and vertical position. It is used for page changes, the landing introduction, dashboard cards, chat bubbles, and the source panel.
- A **scroll-triggered animation** starts when an element enters the visible area. The feature section uses `whileInView`, so its cards reveal as the visitor scrolls down.
- A **scroll-linked animation** changes with scroll position. The thin bar at the top tracks how far the landing page has been scrolled.
- **Mouse interaction effects** add a faint highlight around the pointer in the hero artwork. The pointer location is stored in CSS variables, so React does not redraw the page on each mouse move.
- The page uses CSS **transforms** such as `translateY` and `scale` for small movements. These avoid rearranging nearby content.
- The `prefers-reduced-motion` CSS rule shortens or removes decorative movement for people who ask their device to reduce motion.
- CSS also provides a lightweight typing indicator. Reduced-motion settings shorten or disable movement.
- Lucide React supplies consistent line icons.

## Backend connection

The Dashboard and Study Workspace use `services/api.js` to call the local FastAPI server. Supabase Auth signs students in. React sends its access token with each API request; FastAPI verifies it and filters SQLite records and Chroma vectors with the verified user ID and selected course ID. Uploaded documents, course records, vectors, and saved chat messages remain on this computer. The Groq key stays in Python. If the API cannot be reached, the page shows an error instead of a simulated answer.
# Authentication notes for Phase 3B

- The sign-in page sends email and password to Supabase Auth's documented HTTP endpoints. Supabase checks the password and returns a signed access token; KnowledgePilot does not store password hashes.
- The token is kept in tab session storage and sent to FastAPI in the `Authorization` header. The public Supabase key only identifies the project; it is not a secret.
- FastAPI asks Supabase to verify the token and gets the identity from the provider's response. It uses that verified ID for every course, document, vector, and chat-history query.
- Authentication means proving who signed in. Authorization means checking whether that account owns the requested course or document.
- A browser check is not enough: someone can edit a request, so the backend checks ownership every time.
- SQLite stores the verified account ID next to course/document metadata. Chroma vector records include the same owner and course IDs, which the retrieval filter uses.
- The current Auth session is tab-based. If it expires, the browser uses the refresh token with Supabase; the student can sign in again on a later visit to access saved local data.
- Rate limits and upload quotas are enforced on the backend. They help keep this prototype within limited free provider and machine resources.
- The frontend calls Supabase's standard Auth HTTP API directly because npm downloads were blocked in this environment. Password handling and token issuance still belong to Supabase; FastAPI verifies each token independently.


## Phase 3C: readable conversations and references

- New Chat creates a distinct saved session. The conversation selector reopens a course's saved chats. Changing courses clears the old view and loads only the selected course. Loading states prevent sending into a conversation while it changes. The page scrolls to the latest message.
- The backend uses recent conversation history to understand references like 'it'. RAG still supplies the factual PDF evidence. Each session is checked against the verified user and course.
- `MarkdownAnswer.jsx` uses react-markdown for bold, italic, headings, lists, links and code. remark-gfm adds table support. Raw HTML is skipped, images are disabled, and URL protocols are restricted to HTTP/HTTPS, mailto and local anchors. We never use dangerouslySetInnerHTML. See https://github.com/remarkjs/react-markdown for the maintained renderer's security guidance.
- Each answer owns its saved sources. Its compact Sources button opens `ReferencesDrawer.jsx` with that answer's filename, page and passage, numbered in the same order as the evidence sent to Groq.
- The references panel uses a native dialog for focus trapping. X, Escape and a backdrop click close it; focus returns to the original Sources button. It fits a phone's width and never exposes a public PDF URL.
- Supporting text is at least 13px; controls and navigation are generally 14px; answer text and inputs are 16px. Markdown code/tables scroll inside their container. Headings and the original palette remain. MotionConfig respects reduced-motion preferences.
- React state stores the active session and messages. A retry reuses its request ID, and the backend returns an already-saved answer instead of saving duplicate messages.
- `node tests/markdown-check.mjs` tests the actual renderer with React server rendering, including HTML/script and unsafe-link rejection. This is an automated rendering test, not browser or mobile interaction testing.

Keep history bounded to reduce free-provider usage: only recent messages reach Groq. Opening a long conversation loads its latest 200 messages; older rows stay in SQLite. Visual verification and keyboard/touch checks still require a reachable local browser. Start the backend once on port 8001 and the frontend with the README commands; never stop an unknown process just because the port is occupied.

Executed Phase 3C frontend checks: production build passed; the Markdown server-rendering test passed. Vite reports nonfatal upstream use-client directive warnings and a main-chunk size warning. The browser tool timed out reaching localhost, so drawer clicks/Escape/focus restoration, mobile layout, overflow and visual animation checks remain manual verification items. A successful build is not proof of those interactions.
