// Thin client for the Aajki backend. In dev, requests go to /api/* which Vite proxies
// to https://app.getkalki.com/* (see vite.config.js). Auth token, when present, is sent
// as `Authorization: Bearer <token>` — matching the real app.

const TOKEN_KEY = 'aajki_token';

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || null; } catch { return null; }
}
export function setToken(t) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

// Core request helper. Returns parsed JSON; throws an Error carrying the backend's
// error envelope ({code, http_status, message, ...}) on non-2xx.
export async function apiFetch(path, { method = 'GET', body, auth = true, headers = {} } = {}) {
  const h = { 'x-kalki-client': 'web', ...headers };
  const token = getToken();
  if (auth && token) h['Authorization'] = `Bearer ${token}`;
  if (body !== undefined) h['Content-Type'] = 'application/json';

  // All Aajki calls go through our own backend proxy (/api/aajki), so the app works on
  // Vercel where the browser can't reach app.getkalki.com directly (no CORS).
  const res = await fetch(`/api/aajki${path}`, {
    method,
    headers: h,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }

  if (!res.ok) {
    const err = new Error((data && data.message) || `Request failed (${res.status})`);
    err.status = res.status;
    err.payload = data;
    throw err;
  }
  return data;
}

// --- Public reads used by the clone's screens ---
export const api = {
  appConfig: () => apiFetch('/v2/app-config', { auth: false }),
  home: () => apiFetch('/v2/polls/home', { auth: false }),
  feed: (category, cursor) => {
    const q = new URLSearchParams();
    if (category) q.set('category', category);
    if (cursor) q.set('cursor', cursor);
    const qs = q.toString();
    return apiFetch(`/v2/polls/feed${qs ? `?${qs}` : ''}`, { auth: false });
  },
  topics: () => apiFetch('/v2/polls/topics', { auth: false }),
  topic: (id) => apiFetch(`/v2/polls/topics/${id}`, { auth: false }),
  poll: (id) => apiFetch(`/v2/polls/${id}`, { auth: false }),
  pollComments: (id) => apiFetch(`/v2/polls/${id}/comments`, { auth: false }),
  storiesDaily: (cursor) => apiFetch(`/v2/stories/daily${cursor ? `?cursor=${cursor}` : ''}`, { auth: false }),
  leaderboards: () => apiFetch('/v2/leaderboards', { auth: false }),
  board: (id) => apiFetch(`/v2/leaderboards/${id}`, { auth: false }),

  // --- Auth (these hit the real backend; OTP sends a real SMS) ---
  otpSend: (phone) => apiFetch('/v2/auth/otp/send', { method: 'POST', auth: false, body: { phone } }),
  otpVerify: (phone, code) => apiFetch('/v2/auth/otp/verify', { method: 'POST', auth: false, body: { phone, code } }),

  // --- Authenticated reads ---
  me: () => apiFetch('/v2/me'),
  wallet: (cursor) => apiFetch(`/v2/me/wallet${cursor ? `?cursor=${cursor}` : ''}`),
};

// The feed is a single "trending" feed (the server ignores ?category), so category
// browsing is sourced from that category's topics and their polls. Returns a poll list.
export async function categoryPolls(category) {
  const { items = [] } = await api.topics();
  const topics = items.filter((t) => (t.category || '').toLowerCase() === category.toLowerCase()).slice(0, 6);
  const seen = new Set();
  const polls = [];
  const details = await Promise.all(topics.map((t) => api.topic(t.id).catch(() => null)));
  for (const d of details) {
    for (const p of d?.polls || []) {
      if (p && p.id && !seen.has(p.id)) { seen.add(p.id); polls.push(p); }
    }
  }
  // Topics can mix categories, so keep only polls whose own category matches. If that
  // leaves nothing (sparse category data), fall back to everything the topics returned.
  const strict = polls.filter((p) => (p.category || '').toLowerCase() === category.toLowerCase());
  return strict.length ? strict : polls;
}

// Distinct real categories from the topics list, for the filter chips.
export async function listCategories() {
  const { items = [] } = await api.topics();
  return [...new Set(items.map((t) => t.category).filter(Boolean))];
}
