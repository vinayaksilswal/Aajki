// Sentiment engine — BACKEND ONLY. Never imported by the frontend bundle.
// Two independent signals per poll, combined into a topic/category "public mood":
//   1. Question tone  — lexicon scoring of the poll's wording (how the question is framed).
//   2. Crowd leaning  — how the actual votes split (optimism for binary, consensus vs division).
// No external NLP service: a compact lexicon keeps it deterministic and offline-safe (Vercel).

const POSITIVE = new Set([
  'win', 'wins', 'winning', 'won', 'best', 'great', 'good', 'strong', 'surge', 'surges', 'boost',
  'rise', 'rises', 'rising', 'grow', 'growth', 'gain', 'gains', 'success', 'successful', 'record',
  'top', 'lead', 'leads', 'leading', 'hit', 'hope', 'hopeful', 'confident', 'improve', 'improves',
  'support', 'love', 'happy', 'celebrate', 'reward', 'historic', 'breakthrough', 'deal', 'agree',
  'approve', 'safe', 'safer', 'rescue', 'recover', 'recovery', 'peace', 'trust', 'worth', 'bonus',
]);
const NEGATIVE = new Set([
  'lose', 'loses', 'losing', 'lost', 'worst', 'bad', 'weak', 'fall', 'falls', 'falling', 'drop',
  'drops', 'crash', 'crashes', 'crisis', 'fail', 'fails', 'failure', 'fear', 'fears', 'risk',
  'risks', 'risky', 'concern', 'concerned', 'worried', 'worry', 'threat', 'ban', 'banned', 'cut',
  'cuts', 'death', 'die', 'dies', 'dead', 'war', 'attack', 'fight', 'scandal', 'fraud', 'probe',
  'resign', 'resigns', 'delay', 'delayed', 'wrong', 'danger', 'dangerous', 'protest', 'strike',
  'crime', 'arrest', 'arrested', 'collapse', 'sue', 'sued', 'quit', 'block', 'blocked', 'hate',
]);
const NEGATORS = new Set(['not', 'no', 'never', "won't", 'wont', "can't", 'cant', 'without', 'fails']);

function tokens(text) {
  return String(text || '').toLowerCase().replace(/[^a-z0-9'\s-]/g, ' ').split(/\s+/).filter(Boolean);
}

// Question tone in [-1, 1]: lexicon hits, flipped by a preceding negator.
export function questionTone(text) {
  const t = tokens(text);
  let score = 0, hits = 0;
  for (let i = 0; i < t.length; i++) {
    let s = POSITIVE.has(t[i]) ? 1 : NEGATIVE.has(t[i]) ? -1 : 0;
    if (s !== 0) {
      if (i > 0 && NEGATORS.has(t[i - 1])) s = -s;
      score += s; hits++;
    }
  }
  if (!hits) return { score: 0, label: 'neutral', hits: 0 };
  const norm = Math.max(-1, Math.min(1, score / Math.sqrt(hits)));
  return { score: Number(norm.toFixed(3)), label: norm > 0.15 ? 'positive' : norm < -0.15 ? 'negative' : 'neutral', hits };
}

// Crowd leaning from the vote split.
//  - optimism: for binary yes/no, share voting "yes" (−1..1 centered at 0).
//  - consensus: 1 − normalized entropy (1 = unanimous, 0 = evenly divided).
export function crowdLeaning(poll) {
  const opts = poll.options || [];
  const total = poll.total_votes || opts.reduce((s, o) => s + (o.votes || o.pct || 0), 0) || 0;
  const weights = opts.map((o) => (o.votes != null ? o.votes : (o.pct != null ? o.pct : 0)));
  const sum = weights.reduce((a, b) => a + b, 0) || 1;
  const p = weights.map((w) => w / sum);

  let entropy = 0;
  for (const x of p) if (x > 0) entropy -= x * Math.log2(x);
  const maxEnt = opts.length > 1 ? Math.log2(opts.length) : 1;
  const consensus = Number((1 - entropy / maxEnt).toFixed(3));

  let optimism = null;
  const yes = opts.find((o) => o.id === 'yes');
  const no = opts.find((o) => o.id === 'no');
  if (yes && no) {
    const yShare = (yes.votes != null ? yes.votes : yes.pct || 0) / sum;
    optimism = Number((yShare * 2 - 1).toFixed(3));
  }
  const leader = opts.length ? opts.reduce((a, b) =>
    ((b.votes ?? b.pct ?? 0) > (a.votes ?? a.pct ?? 0) ? b : a)) : null;

  return { total_votes: total, consensus, optimism, divisive: consensus < 0.25,
    leader: leader ? { id: leader.id, label: leader.label, share: Number((((leader.votes ?? leader.pct ?? 0) / sum) || 0).toFixed(3)) } : null };
}

// Per-poll sentiment record.
export function analyzePoll(poll) {
  const tone = questionTone(poll.question);
  const crowd = crowdLeaning(poll);
  // Mood blends how it's framed with how the crowd leans (optimism when available).
  const moodParts = [tone.score];
  if (crowd.optimism != null) moodParts.push(crowd.optimism);
  const mood = Number((moodParts.reduce((a, b) => a + b, 0) / moodParts.length).toFixed(3));
  return {
    id: poll.id, question: poll.question, category: poll.category || poll.beat || 'other',
    image_url: poll.image_url || null,
    tone, crowd, mood,
    mood_label: mood > 0.15 ? 'positive' : mood < -0.15 ? 'negative' : 'neutral',
    engagement: (poll.total_votes || crowd.total_votes || 0) + (poll.comment_count || 0) * 3,
  };
}

// Aggregate a set of polls into a dashboard model.
export function analyzeSet(polls) {
  const records = (polls || []).filter((p) => p && p.question).map(analyzePoll);
  const byCat = new Map();
  for (const r of records) {
    if (!byCat.has(r.category)) byCat.set(r.category, []);
    byCat.get(r.category).push(r);
  }
  const avg = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

  const categories = [...byCat.entries()].map(([category, rs]) => ({
    category,
    count: rs.length,
    mood: Number(avg(rs.map((r) => r.mood)).toFixed(3)),
    optimism: Number(avg(rs.filter((r) => r.crowd.optimism != null).map((r) => r.crowd.optimism)).toFixed(3)),
    consensus: Number(avg(rs.map((r) => r.crowd.consensus)).toFixed(3)),
    total_votes: rs.reduce((a, r) => a + (r.crowd.total_votes || 0), 0),
    positive: rs.filter((r) => r.mood_label === 'positive').length,
    negative: rs.filter((r) => r.mood_label === 'negative').length,
    neutral: rs.filter((r) => r.mood_label === 'neutral').length,
  })).sort((a, b) => b.count - a.count);

  const sorted = [...records].sort((a, b) => b.mood - a.mood);
  const divisive = [...records].filter((r) => r.crowd.divisive).sort((a, b) => a.crowd.consensus - b.crowd.consensus);

  return {
    generated_at: new Date().toISOString(),
    total_polls: records.length,
    total_votes: records.reduce((a, r) => a + (r.crowd.total_votes || 0), 0),
    overall_mood: Number(avg(records.map((r) => r.mood)).toFixed(3)),
    overall_optimism: Number(avg(records.filter((r) => r.crowd.optimism != null).map((r) => r.crowd.optimism)).toFixed(3)),
    distribution: {
      positive: records.filter((r) => r.mood_label === 'positive').length,
      neutral: records.filter((r) => r.mood_label === 'neutral').length,
      negative: records.filter((r) => r.mood_label === 'negative').length,
    },
    categories,
    most_positive: sorted.slice(0, 5),
    most_negative: sorted.slice(-5).reverse(),
    most_divisive: divisive.slice(0, 5),
    most_engaged: [...records].sort((a, b) => b.engagement - a.engagement).slice(0, 5),
  };
}
