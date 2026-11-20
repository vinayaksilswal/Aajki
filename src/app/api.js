// Bharat Foreseez API client.
//
// - Base URL comes from VITE_API_BASE at build time; there is no offline or sample data.
// - Every request carries an X-Correlation-ID. Retries reuse it, so the server logs for one
//   user action group together and an error report can quote a single reference.
// - Only requests that are safe to repeat are retried: reads, and writes that carry an
//   Idempotency-Key (the server returns the first result instead of acting twice).
// - The app session is a bearer token kept on this device. Until phone sign-in ships, the
//   server issues a pseudonymous device account the first time the app opens.

const BASE = String(import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '');
const TIMEOUT_MS = 8000;
const RETRIES = 2;
const TOKEN_KEY = 'bf-session';

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'NETWORK', correlationId = null, details = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
    this.details = details;
  }

  get retryable() {
    // 429s are limits the user should see (daily call cap, posting limits), not retried.
    return this.status === 0 || this.status >= 500;
  }
}

export function newId() {
  if (globalThis.crypto && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replace(/-/g, '');
  }
  let id = '';
  for (let i = 0; i < 32; i++) id += Math.floor(Math.random() * 16).toString(16);
  return id;
}

let token = null;
try { token = localStorage.getItem(TOKEN_KEY); } catch (_) { /* storage blocked */ }

function saveToken(t) {
  token = t;
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch (_) {}
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function once(method, path, { body, idempotencyKey, auth, correlationId }) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  const headers = { Accept: 'application/json', 'X-Correlation-ID': correlationId };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  if (auth && token) headers.Authorization = 'Bearer ' + token;
  let res;
  try {
    res = await fetch(BASE + path, {
      method, headers, credentials: 'omit', signal: ctrl.signal,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    const message = e && e.name === 'AbortError'
      ? 'The server took too long to respond.'
      : 'Can’t reach the server. Check your connection.';
    throw new ApiError(message, { correlationId });
  } finally {
    clearTimeout(timer);
  }
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty or non-JSON body */ }
  if (!res.ok) {
    const err = (data && data.error) || {};
    throw new ApiError(err.message || `Request failed (${res.status}).`, {
      status: res.status,
      code: err.code || `HTTP_${res.status}`,
      correlationId: err.correlation_id || res.headers.get('X-Correlation-ID') || correlationId,
      details: err.details || null,
    });
  }
  return data;
}

let sessionPromise = null;

/** Make sure this device has an app session (creates a device account the first time). */
export function ensureSession() {
  if (token) return Promise.resolve();
  if (!sessionPromise) {
    let invite = null;
    try { invite = new URLSearchParams(location.search).get('invite'); } catch (_) {}
    sessionPromise = request('POST', '/v1/session', { body: invite ? { invite_code: invite.slice(0, 16) } : {}, auth: false })
      .then((r) => saveToken(r.token))
      .finally(() => { sessionPromise = null; });
  }
  return sessionPromise;
}

export async function request(method, path, { body, idempotencyKey, auth = true } = {}) {
  if (!BASE) {
    throw new ApiError('This app isn’t connected to a server yet.', { code: 'NOT_CONFIGURED' });
  }
  if (auth) await ensureSession();
  const safe = method === 'GET' || !!idempotencyKey;
  const correlationId = newId();
  let renewed = false;
  for (let attempt = 0; ; attempt++) {
    try {
      return await once(method, path, { body, idempotencyKey, auth, correlationId });
    } catch (e) {
      if (auth && e instanceof ApiError && e.status === 401 && !renewed) {
        // The session ended (expired, or the account was closed): start a fresh one once.
        renewed = true;
        saveToken(null);
        await ensureSession();
        continue;
      }
      if (!safe || !(e instanceof ApiError) || !e.retryable || attempt >= RETRIES) throw e;
      await sleep(400 * 2 ** attempt + Math.random() * 200);
    }
  }
}

function query(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '') p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

const get = (path, auth = false) => request('GET', path, { auth });
const enc = encodeURIComponent;

export const api = {
  // Public reads (no session needed).
  appConfig: (region) => get('/v1/app-config' + query({ region })),
  questions: (params) => get('/v1/questions' + query(params)),
  question: (id) => get('/v1/questions/' + enc(id)),
  ticker: () => get('/v1/ticker'),
  sentiment: () => get('/v1/sentiment'),
  // Account.
  me: () => get('/v1/me', true),
  updateMe: (patch) => request('PATCH', '/v1/me', { body: patch }),
  ledger: (cursor) => get('/v1/me/ledger' + query({ cursor, limit: 30 }), true),
  myCalls: () => get('/v1/me/calls', true),
  selfExclude: (days) => request('POST', '/v1/me/self-exclusion', { body: { days } }),
  exportData: () => get('/v1/me/export', true),
  deleteAccount: () => request('DELETE', '/v1/me', { body: { confirm: 'DELETE' } }),
  blocks: () => get('/v1/me/blocks', true),
  unblock: (userId) => request('DELETE', '/v1/me/blocks/' + enc(userId)),
  // Calls and results.
  call: (qid, outcomeKey, points, key) =>
    request('POST', '/v1/questions/' + enc(qid) + '/calls', { body: { outcome_key: outcomeKey, points }, idempotencyKey: key }),
  dispute: (qid, reason, evidenceUrl) =>
    request('POST', '/v1/questions/' + enc(qid) + '/disputes', { body: { reason, evidence_url: evidenceUrl || null } }),
  // Debate.
  comments: (qid, before) => get('/v1/questions/' + enc(qid) + '/comments' + query({ before }), true),
  postComment: (qid, body, parentId) =>
    request('POST', '/v1/questions/' + enc(qid) + '/comments', { body: { body, parent_id: parentId || null } }),
  deleteComment: (id) => request('DELETE', '/v1/comments/' + id),
  reportComment: (id, reason) => request('POST', '/v1/comments/' + id + '/report', { body: { reason } }),
  blockAuthor: (id) => request('POST', '/v1/comments/' + id + '/block-author'),
  // Engagement and standing.
  checkin: () => request('POST', '/v1/me/checkin'),
  quizToday: () => get('/v1/quiz/today', true),
  answerQuiz: (quizId, key) => request('POST', '/v1/quiz/' + enc(quizId) + '/answer', { body: { answer_key: key } }),
  leaderboard: (period) => get('/v1/leaderboards' + query({ period }), true),
  // Grievances.
  grievances: () => get('/v1/me/grievances', true),
  raiseGrievance: (g) => request('POST', '/v1/grievances', { body: g }),
};

// All open questions. The open feed is small, so filtering and search then run instantly
// on the device instead of a request per keystroke. Capped as a safety bound.
export async function allOpenQuestions(maxPages = 10) {
  const items = [];
  let cursor = null;
  for (let i = 0; i < maxPages; i++) {
    const page = await api.questions({ status: 'open', limit: 50, cursor });
    items.push(...page.items);
    cursor = page.next_cursor;
    if (!cursor) break;
  }
  return items;
}
