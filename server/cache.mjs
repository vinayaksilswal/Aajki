// Tiny in-memory TTL cache. On serverless this lives per warm instance, which is enough
// to avoid re-aggregating the feed on every admin refresh.
const store = new Map();

export async function cached(key, ttlMs, producer) {
  const hit = store.get(key);
  const now = Date.now();
  if (hit && now - hit.at < ttlMs) return hit.value;
  const value = await producer();
  store.set(key, { value, at: now });
  return value;
}
