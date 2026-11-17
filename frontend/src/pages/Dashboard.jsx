import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { ArrowRight, BookOpen, FileText, LogOut, Plus, Sparkles, Trash2 } from 'lucide-react';
import ResponsiveSidebar, { NavigationToggle } from '../components/ResponsiveSidebar.jsx';
import Modal from '../components/Modal.jsx';
import { createCourse, deleteCourse, getCourses, renameCourse } from '../services/api.js';

export default function Dashboard({ navigate, user, onLogout }) {
  const [navigationOpen,setNavigationOpen]=useState(false);
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [courseName, setCourseName] = useState('');
  const [editingCourse, setEditingCourse] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);

  async function refreshCourses() {
    setLoading(true);
    try { setCourses((await getCourses()).courses); setError(''); }
    catch (reason) { setError(reason.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { refreshCourses(); }, []);

  async function saveCourse(event) {
    event.preventDefault();
    const cleanName = courseName.trim();
    if (!cleanName) return;
    try {
      if (editingCourse) await renameCourse(editingCourse.course_id, cleanName);
      else await createCourse(cleanName);
      setCourseName(''); setEditingCourse(null); setModalOpen(false); setError(''); await refreshCourses();
    } catch (reason) { setError(reason.message); }
  }

  async function removeCourse(course) {
    if (!window.confirm(`Delete “${course.name}” and all of its PDFs? This cannot be undone.`)) return;
    try { await deleteCourse(course.course_id); await refreshCourses(); }
    catch (reason) { setError(reason.message); }
  }

  function openEditor(course = null) {
    setEditingCourse(course); setCourseName(course?.name || ''); setModalOpen(true); setError('');
  }

  return <main className="app-shell"><ResponsiveSidebar className="sidebar" label="Learning navigation" open={navigationOpen} onClose={()=>setNavigationOpen(false)}>
    <button className="brand" onClick={() => navigate('selector')}><span className="brand-mark"><Sparkles size={15}/></span> knowledgepilot<span className="brand-ai">AI</span></button>
    <div className="side-label">YOUR SPACE</div><button className="side-item active"><BookOpen size={17}/> My courses</button>
    <button className="side-item" onClick={() => courses.length && navigate('workspace', courses[0].course_id)}><Sparkles size={17}/> Study workspace</button>
    <div className="side-label side-gap">COURSES <span>{courses.length}</span></div>
    {courses.map(course => <button className="course-nav" key={course.course_id} onClick={() => navigate('workspace', course.course_id)}><span className="course-dot lavender"/>{course.name}</button>)}
    <div className="sidebar-bottom"><div className="demo-pill">PRIVATE ACCOUNT</div><div className="profile"><div className="avatar">{(user?.email || 'S')[0].toUpperCase()}</div><span><b>{user?.email || 'Student account'}</b><small>Private study workspace</small></span></div><button className="account-logout" onClick={onLogout}><LogOut size={14}/> Sign out</button></div>
  </ResponsiveSidebar>
  <motion.div className="dashboard-main" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: .38 }}>
    <header className="dash-top"><NavigationToggle label="Open learning navigation" onClick={()=>setNavigationOpen(true)}/><button className="back-link" onClick={() => navigate('selector')}>Back to Workspace</button><span>My courses <span className="crumb">/ Overview</span></span><span className="dash-account">{user?.email}</span><button className="profile-mobile" onClick={onLogout} aria-label="Sign out"><LogOut size={15}/></button></header>
    <section className="welcome"><div><div className="eyebrow">YOUR PRIVATE STUDY LIBRARY</div><h1>Welcome to your <em>courses.</em></h1><p>Create a course, add PDFs, and ask questions grounded in its documents.</p></div><div className="welcome-glyph"><BookOpen size={25}/></div></section>
    <div className="stats-row"><div className="stat-box"><span><BookOpen size={16}/> Courses</span><b>{courses.length.toString().padStart(2, '0')}</b><small>Saved courses</small></div><div className="stat-box"><span><FileText size={16}/> Documents</span><b>{courses.reduce((total, course) => total + course.document_count, 0).toString().padStart(2, '0')}</b><small>Indexed PDFs</small></div><div className="stat-box"><span><Sparkles size={16}/> Storage</span><b>Private</b><small>Your course materials</small></div></div>
    <div className="content-title"><div><h2>Your courses</h2><p>Choose a course to open its documents and study chat.</p><small className="limit-note">Your materials stay organized by course.</small></div><button className="button-outline" onClick={() => openEditor()}><Plus size={16}/> Create course</button></div>
    {error && <div className="api-error" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
    {loading ? <div className="course-empty">Loading saved courses…</div> : courses.length ? <div className="course-grid">{courses.map((course, index) => <motion.article className="course-card lavender" key={course.course_id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .06 }} whileHover={{ y: -3 }}>
      <button className="course-open" onClick={() => navigate('workspace', course.course_id)} aria-label={`Open ${course.name}`}><div className="course-card-top"><span className="course-code">SAVED COURSE</span><ArrowRight size={17}/></div><div className="course-emblem"><BookOpen size={20}/></div><h3>{course.name}</h3><p>{course.document_count} indexed PDF{course.document_count === 1 ? '' : 's'}</p></button>
      <div className="course-actions"><button onClick={() => openEditor(course)}>Rename</button><button onClick={() => removeCourse(course)} aria-label={`Delete ${course.name}`}><Trash2 size={14}/> Delete</button></div>
    </motion.article>)}</div> : <div className="course-empty"><div className="feature-icon"><BookOpen size={19}/></div><h3>No courses yet</h3><p>Create your first course to keep its documents and study questions together.</p><button className="button-primary" onClick={() => openEditor()}>Create a course <ArrowRight size={15}/></button></div>}
  </motion.div>
  <nav className="mobile-nav" aria-label="Learning navigation"><button className="selected"><BookOpen size={18}/>Courses</button><button onClick={() => courses.length && navigate('workspace', courses[0].course_id)}><Sparkles size={18}/>Study</button><button onClick={() => navigate('selector')}><ArrowRight size={18}/>Workspace</button></nav>
  {modalOpen && <Modal labelledBy="course-modal-title" onClose={()=>setModalOpen(false)}><form className="course-modal" onSubmit={saveCourse}><div className="eyebrow">COURSE DETAILS</div><h2 id="course-modal-title">{editingCourse ? 'Rename course' : 'Create a course'}</h2><label htmlFor="course-name">Course name</label><input id="course-name" autoFocus maxLength="100" value={courseName} onChange={event => setCourseName(event.target.value)} placeholder="e.g. Linear Algebra"/>{error && <p className="modal-error" role="alert">{error}</p>}<div className="modal-actions"><button type="button" className="button-outline" onClick={() => { setEditingCourse(null); setCourseName(''); setModalOpen(false); }}>Cancel</button><button className="button-primary" type="submit">{editingCourse ? 'Save name' : 'Create course'}</button></div></form></Modal>}
  </main>;
}
