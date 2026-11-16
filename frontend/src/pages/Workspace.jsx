import { useEffect, useState, useRef } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ArrowLeft, ArrowUp, ChevronDown, FileText, LogOut, Plus, Sparkles, Trash2, Upload } from 'lucide-react';
import { createChat, getChats, askQuestion, deleteDocument, getCourseChat, getCourseDocuments, getCourses, uploadDocument } from '../services/api.js';

import MarkdownAnswer from '../components/MarkdownAnswer.jsx';
import ReferencesDrawer from '../components/ReferencesDrawer.jsx';

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
  const bottom = useRef(null);
  const pendingTurn = useRef(null);
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }); }, [messages, busy]);
  const displayMessages = rows => rows.map(message => ({ ...message, role: message.role === 'generated' ? 'assistant' : message.role }));
  const [error, setError] = useState('');
  const [loadingCourses, setLoadingCourses] = useState(true);
  const [sessionId, setSessionId] = useState('');

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

  async function ask(text = question) {
    const cleanQuestion = text.trim();
    if (!cleanQuestion || busy || loadingChat || !courseId || !documents.length) return;
    setMessages(current => [...current, { role: 'student', text: cleanQuestion }]);
    setQuestion(''); setError(''); setBusy(true);
    try {
      let activeSession = sessionId;
      if (!activeSession) {
        activeSession = (await createChat(courseId)).session_id;
        setSessionId(activeSession);
        setSessions(current => [{ session_id: activeSession, title: 'New chat' }, ...current]);
      }
      const previous = pendingTurn.current;
      const requestId = previous?.text === cleanQuestion && previous?.session === activeSession
        ? previous.id : crypto.randomUUID();
      pendingTurn.current = { text: cleanQuestion, session: activeSession, id: requestId };
      const result = await askQuestion(courseId, cleanQuestion, activeSession, requestId);
      pendingTurn.current = null;
      getChats(courseId).then(chats => setSessions(chats.sessions)).catch(() => {});
      if (result.session_id) setSessionId(result.session_id);
      setMessages(current => [...current, {
        role: result.mode === 'generated' ? 'assistant' : 'retrieval_only',
        text: result.answer || result.error,
        sources: result.sources,
      }]);
    } catch (reason) {
      setError(reason.message);
      setMessages(current => current.slice(0, -1));
      setQuestion(cleanQuestion);
    } finally { setBusy(false); }
  }

  function selectCourse(id) { if (busy || loadingChat || uploading) return; setCourseId(id); navigate('workspace', id); }

  return <main className="workspace-shell"><aside className="workspace-side">
    <a className="brand" onClick={() => navigate('home')}><span className="brand-mark"><Sparkles size={15}/></span> knowledgepilot<span className="brand-ai">AI</span></a>
    <button className="back-link" onClick={() => navigate('dashboard')}><ArrowLeft size={16}/> All courses</button>
    <div className="side-label">SELECT COURSE</div>
    <label className="course-select-wrap"><select className="course-select" value={courseId} onChange={event => selectCourse(event.target.value)} disabled={!courses.length || busy || loadingChat || uploading}><option value="">Choose a course</option>{courses.map(course => <option key={course.course_id} value={course.course_id}>{course.name}</option>)}</select><ChevronDown size={14}/></label>
    <div className="side-label side-gap">COURSE DOCUMENTS <span>{documents.length}</span></div>
    <label className={`upload-small ${uploading || !courseId ? 'disabled' : ''}`}><Plus size={15}/>{uploading ? 'Indexing PDF…' : 'Add PDF'}<input type="file" accept="application/pdf" multiple hidden disabled={uploading || !courseId} onChange={event => addFiles(event.target.files)}/></label>
    {documents.map(document => <div className="file-nav" key={document.document_id}><FileText size={15}/><span title={document.filename}>{document.filename}</span><small>{document.page_count}p</small><button aria-label={`Delete ${document.filename}`} onClick={() => removeDocument(document)}><Trash2 size={13}/></button></div>)}
    {!documents.length && !loadingCourses && courseId && <p className="empty-materials">This course has no PDFs yet.</p>}
    <div className="workspace-side-bottom"><div className="demo-pill">PRIVATE ACCOUNT</div><small>{user?.email || 'Signed-in student'}<br/>Your study chats are saved.</small><button className="account-logout" onClick={onLogout}><LogOut size={14}/> Sign out</button></div>
  </aside>
  <section className="chat-area"><header className="chat-header"><button className="back-mobile" onClick={() => navigate('dashboard')}><ArrowLeft size={18}/></button><div><span className="eyebrow">{courses.find(course => course.course_id === courseId)?.name || 'COURSE STUDY'}</span><h1>Study workspace</h1></div><button className="chat-signout" onClick={onLogout} aria-label="Sign out"><LogOut size={15}/></button></header>
    <div className="conversation-toolbar">
      <label>Course<select value={courseId} disabled={busy || uploading || loadingChat} onChange={event => selectCourse(event.target.value)}><option value="">Choose course</option>{courses.map(course => <option key={course.course_id} value={course.course_id}>{course.name}</option>)}</select></label>
      <label>Conversation<select value={sessionId} disabled={busy || loadingChat} onChange={event => openChat(event.target.value)}><option value="" disabled>Choose conversation</option>{sessions.map(chat => <option value={chat.session_id} key={chat.session_id}>{chat.title}</option>)}</select></label>
      <button className="button-outline" disabled={!courseId || busy || loadingChat} onClick={newChat}><Plus size={16}/> New chat</button>
    </div>
    {loadingChat && <p className="chat-loading" role="status">Loading conversation...</p>}
    <div className="chat-scroll"><div className="chat-inner"><div className="chat-date">{messages.length >= 200 ? "LATEST 200 MESSAGES" : "COURSE DOCUMENT Q&A"} <span>·</span> PERSISTENT INDEX</div>
      {!messages.length ? <div className="chat-empty"><motion.div className="empty-spark" initial={{ opacity: 0, scale: .8 }} animate={{ opacity: 1, scale: 1 }}><Sparkles size={23}/></motion.div><h2>{loadingCourses ? 'Loading courses…' : !courseId ? 'Create a course to begin.' : !documents.length ? 'This course has no documents.' : 'What are you curious about?'}</h2><p>{documents.length ? 'Answers search only documents in the selected course.' : 'Add a PDF to this course to create its private local search index.'}</p>
        {documents.length > 0 && <div className="suggestions"><button onClick={() => ask('Summarize the main ideas in these course documents.')}>Summarize the main ideas <ArrowUp size={14}/></button><button onClick={() => ask('Explain a key idea from these course documents.')}>Explain a key idea <ArrowUp size={14}/></button></div>}
        <label className={`drop-zone ${uploading || !courseId ? 'disabled' : ''}`} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); addFiles(event.dataTransfer.files); }}><Upload size={17}/><span>{uploading ? 'Extracting text and indexing…' : <>Drop a PDF here or <u>browse files</u></>}</span><small>PDF · Stored in this local course</small><input type="file" accept="application/pdf" multiple hidden disabled={uploading || !courseId} onChange={event => addFiles(event.target.files)}/></label></div>
      : <div className="messages"><AnimatePresence initial={false}>{messages.map((message, index) => <motion.div className={`message ${message.role === 'student' ? 'student' : 'demo'}`} key={index} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
        {message.role === 'assistant' && <div className="demo-response"><Sparkles size={14}/> GROUNDED AI ANSWER</div>}{message.role === 'retrieval_only' && <div className="demo-response error-label">RETRIEVAL ONLY · AI UNAVAILABLE</div>}{message.role === 'error' && <div className="demo-response error-label">REQUEST FAILED</div>}{message.role === 'assistant' ? <MarkdownAnswer text={message.text}/> : <p>{message.text}</p>}
        {message.sources?.length > 0 && <button className="sources-button" onClick={() => setActiveSources(message.sources)} aria-haspopup="dialog"><FileText size={15}/> Sources ({message.sources.length})</button>}
      </motion.div>)}</AnimatePresence>{busy && <motion.div className="typing" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><i/><i/><i/><span>Searching this course and generating an answer</span></motion.div>}</div>}
    <div ref={bottom}/></div></div>
    {error && <div className="api-error" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
    <div className="composer-wrap"><div className="composer"><textarea aria-label="Study question" rows="1" placeholder="Ask about documents in this course…" value={question} disabled={busy || loadingChat || !documents.length} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); ask(); } }}/><div className="composer-controls"><label className="attach-button" aria-label="Attach PDF"><Upload size={16}/><input type="file" accept="application/pdf" multiple hidden disabled={uploading || !courseId} onChange={event => addFiles(event.target.files)}/></label><motion.button className="send-button" aria-label="Send question" disabled={busy || loadingChat || !documents.length} whileHover={{ scale: 1.08 }} whileTap={{ scale: .92 }} onClick={() => ask()}><ArrowUp size={17}/></motion.button></div></div><small>Retrieval and citations are limited to this course</small></div>
  </section>
  {activeSources && <ReferencesDrawer sources={activeSources} onClose={() => setActiveSources(null)}/>}
  </main>;
}
