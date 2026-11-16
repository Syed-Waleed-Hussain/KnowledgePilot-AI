const projectUrl = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, '');
const publicKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const sessionStorageKey = 'knowledgepilot-auth-session';

export const authConfigured = Boolean(
  projectUrl?.startsWith('https://') && publicKey &&
  !projectUrl.includes('your-project-ref') && !publicKey.startsWith('your_'),
);

function savedSession() {
  try { return JSON.parse(sessionStorage.getItem(sessionStorageKey) || 'null'); }
  catch { return null; }
}

function saveSession(session) {
  if (session?.access_token) {
    session.expires_at = Math.floor(Date.now() / 1000) + Number(session.expires_in || 3600);
    sessionStorage.setItem(sessionStorageKey, JSON.stringify(session));
  } else sessionStorage.removeItem(sessionStorageKey);
  window.dispatchEvent(new CustomEvent('knowledgepilot-auth', { detail: session?.user || null }));
}

async function authRequest(path, body, token = '') {
  let response;
  try {
    response = await fetch(`${projectUrl}/auth/v1${path}`, {
      method: 'POST',
      headers: {
        apikey: publicKey,
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error('Could not connect to Supabase Auth. Check your project URL and internet connection.');
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.msg || result.message || result.error_description || 'Supabase could not complete the request.');
  return result;
}

export async function signUp(email, password) {
  const session = await authRequest('/signup', { email, password });
  if (session.access_token) saveSession(session);
  return session;
}

export async function signIn(email, password) {
  const session = await authRequest('/token?grant_type=password', { email, password });
  saveSession(session);
  return session;
}

let refreshRequest;
export async function getSession() {
  const session = savedSession();
  if (!session?.access_token) return null;
  if (session.expires_at > Math.floor(Date.now() / 1000) + 60) return session;
  if (!session.refresh_token) { saveSession(null); return null; }
  if (!refreshRequest) {
    refreshRequest = authRequest('/token?grant_type=refresh_token', { refresh_token: session.refresh_token })
      .then(updated => { saveSession(updated); return updated; })
      .catch(() => { saveSession(null); return null; })
      .finally(() => { refreshRequest = null; });
  }
  return refreshRequest;
}

export async function signOut() {
  const session = savedSession();
  try {
    if (session?.access_token) await authRequest('/logout', {}, session.access_token);
  } catch {
    // Clear the local session even if the provider cannot be reached.
  } finally { saveSession(null); }
}

export function onAuthChange(callback) {
  const listener = event => callback(event.detail);
  window.addEventListener('knowledgepilot-auth', listener);
  return () => window.removeEventListener('knowledgepilot-auth', listener);
}
