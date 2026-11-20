// Load test for the Phase 1 targets (spec s.4): designed for 50 calls/s, tested to 150 calls/s,
// read p95 under 200 ms, write p95 under 400 ms.
//
// Run against STAGING only, never production (it creates device accounts and calls):
//   k6 run -e API=https://staging-api.example.in -e QUESTION=q_... loadtest/calls.k6.js
// QUESTION must be an open question on that staging database. Each virtual user creates one
// device account and makes one call per question, so seed several open questions for long runs
// (pass them comma-separated). Raise the server's signup rate limit for the test, or run the
// generators from several addresses.
import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const API = __ENV.API;
const QUESTIONS = (__ENV.QUESTION || '').split(',').filter(Boolean);
const readTime = new Trend('read_ms', true);
const writeTime = new Trend('write_ms', true);

export const options = {
  scenarios: {
    reads: { executor: 'constant-arrival-rate', rate: 300, timeUnit: '1s', duration: '3m',
             preAllocatedVUs: 100, exec: 'reads' },
    calls: { executor: 'ramping-arrival-rate', startRate: 10, timeUnit: '1s', preAllocatedVUs: 400,
             stages: [{ target: 50, duration: '1m' }, { target: 150, duration: '1m' }, { target: 150, duration: '1m' }],
             exec: 'calls' },
  },
  thresholds: {
    read_ms: ['p(95)<200'],
    write_ms: ['p(95)<400'],
    http_req_failed: ['rate<0.01'],
  },
};

export function reads() {
  const r = http.get(`${API}/v1/questions?status=open&limit=50`);
  readTime.add(r.timings.duration);
  check(r, { 'feed 200': (x) => x.status === 200 });
}

let token = null;
let next = 0;

export function calls() {
  if (!token) {
    const s = http.post(`${API}/v1/session`, '{}', { headers: { 'Content-Type': 'application/json' } });
    token = s.status === 201 ? s.json('token') : null;
    if (!token) return;
  }
  if (next >= QUESTIONS.length) return;
  const qid = QUESTIONS[next++];
  const r = http.post(`${API}/v1/questions/${qid}/calls`,
    JSON.stringify({ outcome_key: Math.random() < 0.5 ? 'yes' : 'no', points: 10 }),
    { headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`,
                 'Idempotency-Key': `${__VU}-${__ITER}-${qid}`.padEnd(8, '0') } });
  writeTime.add(r.timings.duration);
  check(r, { 'call accepted': (x) => x.status === 201 || x.status === 200 });
}
