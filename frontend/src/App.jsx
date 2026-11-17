import { useEffect, useState } from 'react';
import { AnimatePresence, motion, MotionConfig } from 'motion/react';
import Landing from './pages/Landing.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Workspace from './pages/Workspace.jsx';
import AuthPage from './pages/AuthPage.jsx';
import Environments from './pages/Environments.jsx';
import Research from './pages/Research.jsx';
import { parseRoute, routeFor, visiblePage } from './services/routes.js';
import { authConfigured, getSession, onAuthChange, signOut } from './services/auth.js';

export default function App() {
  const [route,setRoute] = useState(()=>parseRoute(window.location.hash));
  const [user,setUser] = useState(null);
  const [loading,setLoading] = useState(authConfigured);
  const [progress,setProgress] = useState(0);
  function navigate(page,id='',replace=false) {
    const path=routeFor(page,id);
    if (replace) { window.history.replaceState(null,'',`#${path}`); setRoute(parseRoute(`#${path}`)); }
    else window.location.hash=path;
    window.scrollTo(0,0);
  }
  useEffect(()=>{
    const change=()=>setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange',change);
    return ()=>window.removeEventListener('hashchange',change);
  },[]);
  useEffect(()=>{
    if (!authConfigured) return;
    let active=true;
    const restore=next=>{
      if (!active) return;
      setUser(next);setLoading(false);
      const current=parseRoute(window.location.hash);
      if (next && ['home','auth'].includes(current.page)) navigate('selector','',true);
    };
    getSession().then(session=>restore(session?.user || null)).catch(()=>{if(active)setLoading(false);});
    const unsubscribe=onAuthChange(restore);
    return ()=>{active=false;unsubscribe();};
  },[]);
  useEffect(()=>{
    const update=()=>setProgress(window.scrollY/(document.documentElement.scrollHeight-innerHeight || 1)*100);
    window.addEventListener('scroll',update,{passive:true});return ()=>window.removeEventListener('scroll',update);
  },[]);
  async function logout(){await signOut();setUser(null);navigate('home','',true);}
  const guardedNavigate=(page,id='',replace=false)=>{
    if(parseRoute('#'+routeFor(page,id)).protected && !user) navigate('auth','',replace);
    else navigate(page,id,replace);
  };
  const shared={navigate:guardedNavigate,user,onLogout:logout,selectedCourseId:route.courseId || '',selectedTopicId:route.topicId || ''};
  const page=visiblePage(route,user,loading);
  return <MotionConfig reducedMotion="user"><div className="scroll-progress" style={{width:`${progress}%`}}/><AnimatePresence mode="wait"><motion.div key={`${user?.id || 'anonymous'}:${page}:${route.courseId || route.topicId || ''}`} initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} transition={{duration:.2}}>
    {page==='loading'?<div className="auth-loading" role="status">Restoring your private workspace.</div>:page==='home'?<Landing {...shared}/>:page==='auth'?<AuthPage {...shared}/>:page==='selector'?<Environments {...shared}/>:page==='dashboard'?<Dashboard {...shared}/>:page==='workspace'?<Workspace {...shared}/>:page==='research'?<Research {...shared}/>:<main className="environment-page"><h1>Page not found</h1><p>Choose an environment to continue.</p><button className="button-primary" onClick={()=>navigate(user?'selector':'home')}>Back to Workspace</button></main>}
  </motion.div></AnimatePresence></MotionConfig>;
}
