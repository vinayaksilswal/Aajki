// Bharat Foreseez API client.
//
// - Base URL comes from VITE_API_BASE at build time; there is no offline or sample data.
// - Every request carries an X-Correlation-ID. Retries reuse it, so the server logs for one
//   user action group together and an error report can quote a single reference.
// - GETs time out, and transient failures (network, 429, 5xx) retry with jittered backoff.

const BASE = String(import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '');
const TIMEOUT_MS = 8000;
const RETRIES = 2;

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'NETWORK', correlationId = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
  }

  get retryable() {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }
}

function newCorrelationId() {
  if (globalThis.crypto && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replace(/-/g, '');
  }
  let id = '';
  for (let i = 0; i < 32; i++) id += Math.floor(Math.random() * 16).toString(16);
  return id;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function once(path, correlationId) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let res;
  try {
    res = await fetch(BASE + path, {
      headers: { Accept: 'application/json', 'X-Correlation-ID': correlationId },
      credentials: 'omit',
      signal: ctrl.signal,
    });
  } catch (e) {
    const message = e && e.name === 'AbortError'
      ? 'The server took too long to respond.'
      : 'Can’t reach the server. Check your connection.';
    throw new ApiError(message, { correlationId });
  } finally {
    clearTimeout(timer);
  }
  let body = null;
  try { body = await res.json(); } catch (_) { /* non-JSON error page */ }
  if (!res.ok) {
    const err = (body && body.error) || {};
    throw new ApiError(err.message || `Request failed (${res.status}).`, {
      status: res.status,
      code: err.code || `HTTP_${res.status}`,
      correlationId: err.correlation_id || res.headers.get('X-Correlation-ID') || correlationId,
    });
  }
  return body;
}

export async function apiGet(path) {
  if (!BASE) {
    throw new ApiError('This app isn’t connected to a server yet.', { code: 'NOT_CONFIGURED' });
  }
  const correlationId = newCorrelationId();
  for (let attempt = 0; ; attempt++) {
    try {
      return await once(path, correlationId);
    } catch (e) {
      if (!(e instanceof ApiError) || !e.retryable || attempt >= RETRIES) throw e;
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

export const api = {
  appConfig: () => apiGet('/v1/app-config'),
  questions: (params) => apiGet('/v1/questions' + query(params)),
  question: (id) => apiGet('/v1/questions/' + encodeURIComponent(id)),
  ticker: () => apiGet('/v1/ticker'),
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
