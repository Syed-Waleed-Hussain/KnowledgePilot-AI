import { useEffect, useState } from 'react';
import { AnimatePresence, motion, MotionConfig } from 'motion/react';
import { ArrowRight, BookOpen, Brain, ChevronDown, FileText, GraduationCap, Layers3, Menu, MessageCircle, Plus, Sparkles, Upload, X } from 'lucide-react';
import Landing from './pages/Landing.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Workspace from './pages/Workspace.jsx';
import AuthPage from './pages/AuthPage.jsx';
import { authConfigured, getSession, onAuthChange, signOut } from './services/auth.js';

export default function App() {
  const [page, setPage] = useState('home');
  const [selectedCourseId, setSelectedCourseId] = useState('');
  const [progress, setProgress] = useState(0);
  const [user, setUser] = useState(null);
  const [sessionLoading, setSessionLoading] = useState(authConfigured);
  useEffect(() => {
    if (!authConfigured) return;
    getSession().then(session => { setUser(session?.user || null); setSessionLoading(false); })
      .catch(() => setSessionLoading(false));
    return onAuthChange(nextUser => {
      setUser(nextUser); setSessionLoading(false);
      if (nextUser) setPage(current => current === 'auth' ? 'dashboard' : current);
      else setPage(current => current === 'dashboard' || current === 'workspace' ? 'home' : current);
    });
  }, []);
  useEffect(() => {
    const update = () => setProgress(window.scrollY / (document.documentElement.scrollHeight - innerHeight || 1) * 100);
    window.addEventListener('scroll', update, { passive: true }); return () => window.removeEventListener('scroll', update);
  }, [page]);
  function navigate(next, courseId = '') {
    const protectedPage = next === 'dashboard' || next === 'workspace';
    setSelectedCourseId(courseId); setPage(protectedPage && !user ? 'auth' : next); window.scrollTo(0, 0);
  }
  async function logout() { await signOut(); setUser(null); setPage('home'); }
  const shared = { navigate, selectedCourseId, user, onLogout: logout };
  return <MotionConfig reducedMotion="user"><div className="scroll-progress" style={{ width: `${progress}%` }} />
    <AnimatePresence mode="wait"><motion.div key={page} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: .25 }}>
      {sessionLoading ? <div className="auth-loading" role="status">Restoring your private workspace…</div>
        : page === 'home' ? <Landing {...shared} /> : page === 'auth' ? <AuthPage {...shared} />
          : page === 'dashboard' && user ? <Dashboard {...shared} />
            : page === 'workspace' && user ? <Workspace {...shared} /> : <AuthPage {...shared} />}
    </motion.div></AnimatePresence>
  </MotionConfig>;
}
