const API_URL = (import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://127.0.0.1:8001')).replace(/\/$/, '');
import { getSession } from './auth.js';

export async function request(path, options = {}) {
  if (!API_URL) throw new Error('The application API address is not configured. Contact the administrator.');
  const session = await getSession();
  const token = session?.access_token;
  if (!token) throw new Error('Sign in to access your private workspace.');
  const headers = new Headers(options.headers || {});
  headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = result.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.message || `Request failed (${response.status}).`);
  }
  return result;
}

export function getCourses() {
  return request('/courses');
}

export function createCourse(name) {
  return request('/courses', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export function renameCourse(courseId, name) {
  return request(`/courses/${courseId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export function deleteCourse(courseId) {
  return request(`/courses/${courseId}?confirmed=true`, { method: 'DELETE' });
}

export function getCourseDocuments(courseId) {
  return request(`/courses/${courseId}/documents`);
}

export function getCourseChat(courseId, sessionId = "") {
  return request(`/courses/${courseId}/chat${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`);
}

export function uploadDocument(courseId, file) {
  const body = new FormData();
  body.append('course_id', courseId);
  body.append('file', file);
  return request('/documents/upload', { method: 'POST', body });
}

export function deleteDocument(documentId) {
  return request(`/documents/${documentId}?confirmed=true`, { method: 'DELETE' });
}

export function askQuestion(courseId, question, sessionId = '', requestId = '') {
  return request('/chat/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, question, session_id: sessionId || null, request_id: requestId || null }),
  });
}

export function generateInfographic(courseId, question, sessionId = '', requestId = '') {
  return request('/chat/infographic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, question, session_id: sessionId || null, request_id: requestId || null }),
  });
}

export function getChats(courseId) { return request(`/courses/${courseId}/chats`); }
export function createChat(courseId) { return request(`/courses/${courseId}/chats`, { method: "POST" }); }
