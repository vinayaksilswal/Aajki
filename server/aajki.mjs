// Server-side Aajki client. Runs on the backend, so there is no CORS issue and we can
// aggregate across pages for the sentiment dashboard.
const UPSTREAM = process.env.AAJKI_API || 'https://app.getkalki.com';
const CLIENT = process.env.AAJKI_CLIENT || 'web';

async function get(path, { timeoutMs = 12000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${UPSTREAM}${path}`, {
      headers: { 'x-kalki-client': CLIENT, accept: 'application/json' },
      signal: ctrl.signal,
    });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = null; }
    if (!res.ok) { const e = new Error(`Upstream ${res.status} on ${path}`); e.status = res.status; e.body = data; throw e; }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

// Pull up to `maxPages` of the trending feed and return the flat poll list.
export async function fetchFeedPolls({ maxPages = 6 } = {}) {
  let cursor = null, pages = 0;
  const polls = [];
  do {
    const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : '';
    const page = await get(`/v2/polls/feed${q}`);
    for (const it of page.items || []) if (it.poll) polls.push(it.poll);
    cursor = page.next_cursor;
    pages++;
  } while (cursor && pages < maxPages);
  return polls;
}

export { UPSTREAM, CLIENT };
