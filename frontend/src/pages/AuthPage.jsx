import { useState } from 'react';
import { ArrowLeft, ArrowRight, LockKeyhole, Sparkles, Eye, EyeOff } from 'lucide-react';
import { authConfigured, signIn, signUp } from '../services/auth.js';

export default function AuthPage({ navigate }) {
  const [passwordVisible,setPasswordVisible]=useState(false);
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    if (!authConfigured || busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const session = mode === 'signup' ? await signUp(email.trim(), password) : await signIn(email.trim(), password);
      if (mode === 'signup' && !session.access_token) setMessage('Check your email to confirm your account, then sign in.');
      else setMessage(mode === 'signup' ? 'Account created. Your private workspace is ready.' : 'Signed in. Opening your workspace…');
    } catch (reason) { setError(reason.message); }
    setBusy(false);
  }

  return <main className="auth-screen">
    <a className="brand auth-brand" href="#home" onClick={event => { event.preventDefault(); navigate('home'); }}><span className="brand-mark"><Sparkles size={15}/></span> knowledgepilot<span className="brand-ai">AI</span></a>
    <section className="auth-card">
      <div className="auth-mark"><LockKeyhole size={20}/></div>
      <div className="eyebrow">YOUR PRIVATE STUDY SPACE</div>
      <h1>{mode === 'login' ? <>Welcome <em>back.</em></> : <>Create your <em>account.</em></>}</h1>
      <p>{mode === 'login' ? 'Sign in to continue with your courses and saved study chats.' : 'Use your email to create a personal course workspace.'}</p>
      {!authConfigured ? <div className="auth-notice" role="alert">Sign-in needs your Supabase project URL and public key. Copy <code>frontend/.env.example</code> to <code>frontend/.env.local</code>, add those same values to the existing project-root <code>.env</code>, and restart both local servers. Keep your Groq key and never use a service-role key in React.</div> : <form onSubmit={submit} aria-busy={busy}>
        <label htmlFor="auth-email">Email address</label><input name="email" id="auth-email" type="email" autoComplete="email" aria-invalid={Boolean(error)} aria-describedby={error?'auth-error':undefined} required value={email} onChange={event => setEmail(event.target.value)} placeholder="you@example.com"/>
        <label htmlFor="auth-password">Password</label><div className="password-field"><input name="password" id="auth-password" type={passwordVisible ? 'text' : 'password'} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} aria-invalid={Boolean(error)} aria-describedby={error?'auth-error':undefined} minLength="8" required value={password} onChange={event => setPassword(event.target.value)} placeholder="At least 8 characters"/><button type="button" aria-label={passwordVisible?'Hide password':'Show password'} aria-pressed={passwordVisible} onClick={()=>setPasswordVisible(!passwordVisible)}>{passwordVisible?<EyeOff size={18}/>:<Eye size={18}/>}</button></div>
        {error && <div id="auth-error" className="auth-error" role="alert">{error}</div>}{message && <div className="auth-message" role="status">{message}</div>}
        <button className="button-primary auth-submit" type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}<ArrowRight size={15}/></button>
      </form>}
      {authConfigured && <button className="auth-switch" onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(''); setMessage(''); }}>{mode === 'login' ? 'New here? Create an account' : 'Already registered? Sign in'}</button>}
      <button className="auth-back" onClick={() => navigate('home')}><ArrowLeft size={14}/> Back to KnowledgePilot</button>
      <small className="auth-local-note">Course documents and AI usage stay subject to the local prototype limits.</small>
    </section>
  </main>;
}
