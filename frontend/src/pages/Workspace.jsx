import { useEffect, useLayoutEffect, useState, useRef } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ArrowLeft, ArrowUp, ChevronDown, FileText, LogOut, Plus, Sparkles, Trash2, Upload } from 'lucide-react';
import { createChat, getChats, askQuestion, generateInfographic, deleteDocument, getCourseChat, getCourseDocuments, getCourses, uploadDocument } from '../services/api.js';

import ResponsiveSidebar, { NavigationToggle } from '../components/ResponsiveSidebar.jsx';
import InfographicCard from '../components/InfographicCard.jsx';
import MarkdownAnswer from '../components/MarkdownAnswer.jsx';
import ReferencesDrawer from '../components/ReferencesDrawer.jsx';

export const DEFAULT_INFOGRAPHIC_PROMPT = 'Create an educational infographic overview of the main concepts in these course documents.';

export function displayMessages(rows) {
  return rows.map(message => ({
    ...message,
    role: message.role === 'generated' ? 'assistant' : message.role,
  }));
}

export function infographicPrompt(text) {
  const clean = String(text || '').trim();
  if (!clean) return DEFAULT_INFOGRAPHIC_PROMPT;
  return /\b(infographic|info-graphic|visually|visual summary|diagram|poster|mind map)\b/i.test(clean)
    ? clean : `Make an infographic about: ${clean}`;
}

export default function Workspace({ navigate, selectedCourseId, user, onLogout }) {
  const [courses, setCourses] = useState([]);
  const [courseId, setCourseId] = useState(selectedCourseId);
  const [documents, setDocuments] = useState([]);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [activeSources, setActiveSources] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [loadingChat, setLoadingChat] = useState(false);
  const scrollRegion = useRef(null);
  const followLatest = useRef(true);
  const positions = useRef(new Map());
  const [showLatest, setShowLatest] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  function jumpToLatest() {
    const node=scrollRegion.current;
    if(node) node.scrollTo({top:node.scrollHeight,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
    followLatest.current=true; setShowLatest(false);
  }
  function trackScroll() {
    const node=scrollRegion.current;
    const near=node.scrollHeight-node.scrollTop-node.clientHeight<100;
    followLatest.current=near; setShowLatest(!near);
    if(sessionId) positions.current.set(sessionId,node.scrollTop);
  }
  const pendingTurn = useRef(null);

  const [error, setError] = useState('');
  const [loadingCourses, setLoadingCourses] = useState(true);
  const [sessionId, setSessionId] = useState('');
  useLayoutEffect(() => {
    if (loadingChat) return;
    const node=scrollRegion.current;
    if(node && followLatest.current) node.scrollTop=node.scrollHeight;
  }, [messages, busy, loadingChat]);
  useLayoutEffect(() => {
    if (loadingChat) return;
    const node=scrollRegion.current, saved=positions.current.get(sessionId);
    if(node) node.scrollTop=saved ?? node.scrollHeight;
    followLatest.current=saved===undefined || node.scrollHeight-node.scrollTop-node.clientHeight<100;
    setShowLatest(!followLatest.current);
  }, [sessionId, loadingChat]);
  useEffect(() => {
    const viewport=window.visualViewport;
    const update=()=>document.documentElement.style.setProperty('--app-height',`${viewport?.height || window.innerHeight}px`);
    update(); viewport?.addEventListener('resize',update);
    return ()=>{viewport?.removeEventListener('resize',update);document.documentElement.style.removeProperty('--app-height');};
  }, []);


  useEffect(() => {
    getCourses().then(result => {
      setCourses(result.courses);
      const selected = result.courses.find(course => course.course_id === selectedCourseId);
      setCourseId(selected?.course_id || result.courses[0]?.course_id || '');
      setError('');
    }).catch(reason => setError(reason.message)).finally(() => setLoadingCourses(false));
  }, [selectedCourseId]);

  useEffect(() => {
    let active = true;
    setMessages([]); setDocuments([]); setSessions([]); setSessionId(''); setActiveSources(null);
    pendingTurn.current = null;
    if (!courseId) { setLoadingChat(false); return; }
    setLoadingChat(true); setError('');
    Promise.all([getCourseDocuments(courseId), getChats(courseId), getCourseChat(courseId)])
      .then(([docs, chats, chat]) => {
        if (!active) return;
        setDocuments(docs.documents); setSessions(chats.sessions);
        setMessages(displayMessages(chat.messages)); setSessionId(chat.session_id || '');
      }).catch(reason => { if (active) setError(reason.message); })
      .finally(() => { if (active) setLoadingChat(false); });
    return () => { active = false; };
  }, [courseId]);

  async function openChat(id) {
    if (busy || loadingChat) return;
    setLoadingChat(true); setActiveSources(null); setError('');
    pendingTurn.current = null;
    try {
      const chat = await getCourseChat(courseId, id);
      setSessionId(chat.session_id); setMessages(displayMessages(chat.messages));
    } catch (reason) { setError(reason.message); }
    finally { setLoadingChat(false); }
  }

  async function newChat() {
    if (!courseId || busy || loadingChat) return;
    setLoadingChat(true); setError('');
    try {
      const chat = await createChat(courseId);
      setSessionId(chat.session_id); setMessages([]); setActiveSources(null);
      pendingTurn.current = null;
      setSessions(current => [{ ...chat, title: 'New chat' }, ...current]);
    } catch (reason) { setError(reason.message); }
    finally { setLoadingChat(false); }
  }

  async function addFiles(fileList) {
    if (!courseId) { setError('Create or select a course before adding a PDF.'); return; }
    const files = Array.from(fileList).filter(file => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'));
    if (!files.length) { setError('Choose a PDF file.'); return; }
    setError(''); setUploading(true);
    for (const file of files) {
      try {
        const result = await uploadDocument(courseId, file);
        setDocuments(current => current.some(item => item.document_id === result.document.document_id)
          ? current : [...current, result.document]);
      } catch (reason) { setError(`${file.name}: ${reason.message}`); }
    }
    setUploading(false);
  }

  async function removeDocument(document) {
    if (!window.confirm(`Delete “${document.filename}” and its indexed vectors? This cannot be undone.`)) return;
    try {
      await deleteDocument(document.document_id);
      setDocuments(current => current.filter(item => item.document_id !== document.document_id));
      setError('');
    } catch (reason) { setError(reason.message); }
  }

  async function ask(text = question, retryId = '', retryAt = 0, forceInfographic = false) {
    const cleanQuestion = (forceInfographic ? infographicPrompt(text) : String(text || '').trim());
    if (!cleanQuestion || busy || loadingChat || !courseId || !documents.length) return;
    if (retryAt > Date.now() / 1000) { setError(`Please wait ${Math.ceil(retryAt - Date.now()/1000)} seconds before retrying.`); return; }
    if (!retryId) setMessages(current => [...current, { role: 'student', text: cleanQuestion }]);
    followLatest.current = true;
    setQuestion(''); setError(''); setBusy(true);
    try {
      let activeSession = sessionId;
      if (!activeSession) {
        activeSession = (await createChat(courseId)).session_id;
        setSessionId(activeSession);
        setSessions(current => [{ session_id: activeSession, title: 'New chat' }, ...current]);
      }
      const previous = pendingTurn.current;
      const requestId = retryId || (previous?.text === cleanQuestion && previous?.session === activeSession
        ? previous.id : crypto.randomUUID());
      pendingTurn.current = { text: cleanQuestion, session: activeSession, id: requestId };
      const result = forceInfographic
        ? await generateInfographic(courseId, cleanQuestion, activeSession, requestId)
        : await askQuestion(courseId, cleanQuestion, activeSession, requestId);
      if (result.mode === 'generated') pendingTurn.current = null;
      getChats(courseId).then(chats => setSessions(chats.sessions)).catch(() => {});
      if (result.session_id) setSessionId(result.session_id);
      const chat = await getCourseChat(courseId, activeSession);
      setMessages(displayMessages(chat.messages));
    } catch (reason) {
      setError(reason.message);
      // Restore the server's saved turn; never delete the user's question on failure.
      const pending = pendingTurn.current;
      if (pending?.session) {
        try {
          const chat = await getCourseChat(courseId, pending.session);
          const restored = displayMessages(chat.messages);
          setMessages(restored.some(message => message.request_id === pending.id) ? restored : [...restored,
            {role:'student', text:cleanQuestion, error:reason.message, retryable:true, request_id:pending.id}]);
        }
        catch { setMessages(current => current.map(message => message.role === 'student' && message.text === cleanQuestion
          ? {...message, error: reason.message, retryable: true, request_id: pending.id} : message)); }
      } else setQuestion(cleanQuestion);
    } finally { setBusy(false); }
  }

  function selectCourse(id) { if (busy || loadingChat || uploading) return; setCourseId(id); navigate('workspace', id); }

  return <main className="workspace-shell"><ResponsiveSidebar className="workspace-side" label="Course navigation" open={navigationOpen} onClose={()=>setNavigationOpen(false)}>
    <button className="brand" onClick={() => navigate('selector')}><span className="brand-mark"><Sparkles size={15}/></span> knowledgepilot<span className="brand-ai">AI</span></button>
    <button className="back-link" onClick={() => navigate('dashboard')}><ArrowLeft size={16}/> All courses</button>
    <div className="side-label">SELECT COURSE</div>
    <label className="course-select-wrap"><select aria-label="Selected course" className="course-select" value={courseId} onChange={event => selectCourse(event.target.value)} disabled={!courses.length || busy || loadingChat || uploading}><option value="">Choose a course</option>{courses.map(course => <option key={course.course_id} value={course.course_id}>{course.name}</option>)}</select><ChevronDown size={14}/></label>
    <div className="side-label side-gap">COURSE DOCUMENTS <span>{documents.length}</span></div>
    <label className={`upload-small ${uploading || !courseId ? 'disabled' : ''}`}><Plus size={15}/>{uploading ? 'Indexing PDF…' : 'Add PDF'}<input className="visually-hidden" aria-label="Upload course PDFs" type="file" accept="application/pdf" multiple disabled={uploading || !courseId} onChange={event => addFiles(event.target.files)}/></label>
    {documents.map(document => <div className="file-nav" key={document.document_id}><FileText size={15}/><span title={document.filename}>{document.filename}</span><small>{document.page_count}p</small><button aria-label={`Delete ${document.filename}`} onClick={() => removeDocument(document)}><Trash2 size={13}/></button></div>)}
    {!documents.length && !loadingCourses && courseId && <p className="empty-materials">This course has no PDFs yet.</p>}
    <div className="workspace-side-bottom"><div className="demo-pill">PRIVATE ACCOUNT</div><small>{user?.email || 'Signed-in student'}<br/>Your study chats are saved.</small><button className="account-logout" onClick={onLogout}><LogOut size={14}/> Sign out</button></div>
  </ResponsiveSidebar>
  <section className="chat-area"><header className="chat-header"><NavigationToggle label="Open course navigation" onClick={()=>setNavigationOpen(true)}/><button className="back-link" onClick={() => navigate('selector')}>Back to Workspace</button><div><span className="eyebrow">{courses.find(course => course.course_id === courseId)?.name || 'COURSE STUDY'}</span><h1>Study workspace</h1></div><button className="chat-signout" onClick={onLogout} aria-label="Sign out"><LogOut size={15}/></button></header>
    <div className="conversation-toolbar">
      <label>Course<select value={courseId} disabled={busy || uploading || loadingChat} onChange={event => selectCourse(event.target.value)}><option value="">Choose course</option>{courses.map(course => <option key={course.course_id} value={course.course_id}>{course.name}</option>)}</select></label>
      <label>Conversation<select value={sessionId} disabled={busy || loadingChat} onChange={event => openChat(event.target.value)}><option value="" disabled>Choose conversation</option>{sessions.map(chat => <option value={chat.session_id} key={chat.session_id}>{chat.title}</option>)}</select></label>
      <button className="button-outline" disabled={!courseId || busy || loadingChat} onClick={newChat}><Plus size={16}/> New chat</button>
    </div>
    {loadingChat && <p className="chat-loading" role="status">Loading conversation...</p>}
    <div className="chat-scroll" ref={scrollRegion} onScroll={trackScroll} tabIndex={0} role="region" aria-label="Conversation messages"><div className="chat-inner"><div className="chat-date">{messages.length >= 200 ? "LATEST 200 MESSAGES" : "COURSE DOCUMENT Q&A"} <span>·</span> PERSISTENT INDEX</div>
      {!messages.length ? <div className="chat-empty"><motion.div className="empty-spark" initial={{ opacity: 0, scale: .8 }} animate={{ opacity: 1, scale: 1 }}><Sparkles size={23}/></motion.div><h2>{loadingCourses ? 'Loading courses…' : !courseId ? 'Create a course to begin.' : !documents.length ? 'This course has no documents.' : 'What are you curious about?'}</h2><p>{documents.length ? 'Answers search only documents in the selected course.' : 'Add a PDF to this course to create its private local search index.'}</p>
        {documents.length > 0 && <div className="suggestions"><button onClick={() => ask('Summarize the main ideas in these course documents.')}>Summarize the main ideas <ArrowUp size={14}/></button><button onClick={() => ask('Explain a key idea from these course documents.')}>Explain a key idea <ArrowUp size={14}/></button><button onClick={() => ask('', '', 0, true)}>Generate an infographic <Sparkles size={14}/></button></div>}
        <label className={`drop-zone ${uploading || !courseId ? 'disabled' : ''}`} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); addFiles(event.dataTransfer.files); }}><Upload size={17}/><span>{uploading ? 'Extracting text and indexing…' : <>Drop a PDF here or <u>browse files</u></>}</span><small>PDF · Stored in this local course</small><input className="visually-hidden" aria-label="Upload course PDFs" type="file" accept="application/pdf" multiple disabled={uploading || !courseId} onChange={event => addFiles(event.target.files)}/></label></div>
      : <div className="messages"><AnimatePresence initial={false}>{messages.map((message, index) => <motion.div className={`message ${message.role === 'student' ? 'student' : 'demo'}${message.role === 'infographic' ? ' infographic-message' : ''}`} key={index} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
        {message.role === 'assistant' && <div className="demo-response"><Sparkles size={14}/> GROUNDED AI ANSWER</div>}
        {message.role === 'infographic' && <div className="demo-response infographic-label"><Sparkles size={14}/> GROUNDED INFOGRAPHIC</div>}
        {message.role === 'retrieval_only' && <div className="demo-response error-label">RETRIEVAL ONLY · AI UNAVAILABLE</div>}
        {message.role === 'error' && <div className="demo-response error-label">REQUEST FAILED</div>}
        {message.role === 'infographic'
          ? <InfographicCard infographic={message.infographic} sources={message.sources || []} courseName={courses.find(course => course.course_id === courseId)?.name || ''} onOpenSources={setActiveSources}/>
          : message.role === 'assistant' ? <MarkdownAnswer text={message.text}/> : <p>{message.text}</p>}
        {message.role !== 'infographic' && message.sources?.length > 0 && <button className="sources-button" onClick={event => {event.currentTarget.focus();setActiveSources(message.sources);}} aria-haspopup="dialog"><FileText size={15}/> Sources ({message.sources.length})</button>}
        {message.error && <div className="api-error" role="status"><span>{message.error}</span>{message.retry_after > 0 && <small> Wait at least {message.retry_after} seconds.</small>}{message.retryable && message.request_id && <button disabled={busy || loadingChat} onClick={() => ask(message.text, message.request_id, message.retry_at)}>Retry this question</button>}</div>}
      </motion.div>)}</AnimatePresence>{busy && <motion.div role="status" className="typing" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><i/><i/><i/><span>Searching this course and generating an answer</span></motion.div>}</div>}
    <div aria-hidden="true"/></div></div>
    {error && <div className="api-error" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
    {showLatest && <button className="jump-latest" onClick={jumpToLatest}>Jump to latest <ChevronDown size={15}/></button>}
    <div className="composer-wrap"><div className="composer"><textarea aria-label="Study question" rows="2" placeholder="Ask about documents in this course…" value={question} disabled={busy || loadingChat || !documents.length} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); ask(); } }}/><div className="composer-controls"><label className="attach-button" aria-label="Attach PDF"><Upload size={16}/><input className="visually-hidden" aria-label="Upload course PDFs" type="file" accept="application/pdf" multiple disabled={uploading || !courseId} onChange={event => addFiles(event.target.files)}/></label><div className="composer-actions"><button type="button" className="infographic-button" disabled={busy || loadingChat || !documents.length} onClick={() => ask(question, '', 0, true)}><Sparkles size={15}/> Generate Infographic</button><motion.button className="send-button" aria-label="Send question" disabled={busy || loadingChat || !documents.length} whileHover={{ scale: 1.08 }} whileTap={{ scale: .92 }} onClick={() => ask()}><ArrowUp size={17}/></motion.button></div></div></div><small>Retrieval and citations are limited to this course</small></div>
  </section>
  {activeSources && <ReferencesDrawer sources={activeSources} onClose={() => setActiveSources(null)}/>}
  </main>;
}
