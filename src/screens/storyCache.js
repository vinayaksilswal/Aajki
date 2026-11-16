// Stories have no per-id endpoint, so the daily list is the only source. We cache the
// last-loaded stories in memory so the Story detail screen can show one by id without
// refetching, and fall back to a fresh daily fetch when the cache is cold (e.g. deep link).
let cache = new Map();

export function cacheStories(stories) {
  for (const s of stories) cache.set(s.id, s);
}
export function getCachedStory(id) {
  return cache.get(id) || null;
}
