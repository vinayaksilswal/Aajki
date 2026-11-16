// Local vote store. Votes are kept per-device in localStorage so results reveal only
// after the user answers, and stay revealed on return. (Submitting the vote to Aajki's
// backend needs a signed-in session; this clone records the choice locally for testing.)
const KEY = 'aajki_votes';

function load() {
  try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch { return {}; }
}
export function getVote(pollId) { return load()[pollId] || null; }
export function setVote(pollId, optionId) {
  const all = load();
  all[pollId] = optionId;
  try { localStorage.setItem(KEY, JSON.stringify(all)); } catch { /* ignore */ }
}
