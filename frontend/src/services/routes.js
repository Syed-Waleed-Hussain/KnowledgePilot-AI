// Hash routes need no hosting rewrite and preserve browser Back/refresh.
export function parseRoute(hash = '') {
  const path = hash.replace(/^#/, '') || '/';
  const aliases = { home: '/', top: '/', how: '/', features: '/', auth: '/login', dashboard: '/learning', workspace: '/learning/course', '#home': '/' };
  const clean = aliases[path] || path;
  if (clean === '/') return { page: 'home', protected: false };
  if (clean === '/login') return { page: 'auth', protected: false };
  if (clean === '/workspace') return { page: 'selector', protected: true };
  if (clean === '/learning') return { page: 'dashboard', protected: true };
  if (clean === '/learning/course') return { page: 'workspace', courseId: '', protected: true };
  const course = clean.match(/^\/learning\/course\/([^/]+)$/);
  const research = clean.match(/^\/research(?:\/([^/]+))?$/);
  try {
    if (course) return { page: 'workspace', courseId: decodeURIComponent(course[1]), protected: true };
    if (research) return { page: 'research', topicId: research[1] ? decodeURIComponent(research[1]) : '', protected: true };
  } catch { /* Malformed URLs use the friendly fallback. */ }
  return { page: 'notfound', protected: false };
}
export function routeFor(page, id = '') {
  return ({ home: '/', top: '/', how: '/', features: '/', auth: '/login', selector: '/workspace', dashboard: '/learning',
    workspace: `/learning/course${id ? '/' + encodeURIComponent(id) : ''}`,
    research: `/research${id ? '/' + encodeURIComponent(id) : ''}` })[page] || '/missing';
}
export function visiblePage(route, user, loading = false) {
  if (loading) return 'loading';
  return route.protected && !user ? 'auth' : route.page;
}
