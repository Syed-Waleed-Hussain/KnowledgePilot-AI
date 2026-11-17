import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('logout prevents an in-flight refresh from restoring access', async () => {
  const values = new Map();
  globalThis.sessionStorage = { getItem: k => values.get(k), setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k) };
  globalThis.window = { dispatchEvent() {} };
  globalThis.CustomEvent = class { constructor(type, options) { this.detail = options.detail; } };
  let resolveRefresh;
  globalThis.fetch = async url => {
    if (url.includes('refresh_token')) return new Promise(resolve => { resolveRefresh = resolve; });
    return { ok: true, json: async () => ({}) };
  };
  let source = await readFile(new URL('./src/services/auth.js', import.meta.url), 'utf8');
  source = source.replaceAll('import.meta.env', '({VITE_SUPABASE_URL:"https://auth.example.test",VITE_SUPABASE_ANON_KEY:"public-test"})');
  const auth = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  values.set('knowledgepilot-auth-session', JSON.stringify({access_token:'old',refresh_token:'refresh',expires_at:0}));
  const refreshing = auth.getSession();
  await auth.signOut();
  resolveRefresh({ok:true,json:async()=>({access_token:'new',user:{id:'alice'}})});
  assert.equal(await refreshing, null);
  assert.equal(await auth.getSession(), null);
  assert.equal(values.has('knowledgepilot-auth-session'), false);
});
