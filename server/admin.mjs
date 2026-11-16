// Server-rendered sentiment admin portal. Returns a full HTML page. All sentiment logic
// is computed on the backend; the page is static HTML (no frontend app code involved).
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pct = (x) => `${Math.round((x || 0) * 100)}%`;
const moodColor = (m) => (m > 0.15 ? '#1f9d55' : m < -0.15 ? '#d14343' : '#9a7b00');
const signed = (x) => `${x > 0 ? '+' : ''}${(x ?? 0).toFixed(2)}`;

// A −1..1 gauge as a horizontal bar with a centre marker.
function gauge(value, label) {
  const left = ((value + 1) / 2) * 100;
  return `
    <div class="gauge">
      <div class="gauge-track"><div class="gauge-mark" style="left:${left}%"></div><div class="gauge-center"></div></div>
      <div class="gauge-row"><span>negative</span><strong style="color:${moodColor(value)}">${signed(value)} ${esc(label)}</strong><span>positive</span></div>
    </div>`;
}

function distBar(d) {
  const total = (d.positive + d.neutral + d.negative) || 1;
  const seg = (n, c) => `<div style="width:${(n / total) * 100}%;background:${c}"></div>`;
  return `<div class="distbar">${seg(d.positive, '#1f9d55')}${seg(d.neutral, '#c9a227')}${seg(d.negative, '#d14343')}</div>
    <div class="distlegend"><span><i style="background:#1f9d55"></i>${d.positive} positive</span>
    <span><i style="background:#c9a227"></i>${d.neutral} neutral</span><span><i style="background:#d14343"></i>${d.negative} negative</span></div>`;
}

function catRows(categories) {
  return categories.map((c) => `
    <tr>
      <td><strong>${esc(c.category)}</strong></td>
      <td>${c.count}</td>
      <td style="color:${moodColor(c.mood)}">${signed(c.mood)}</td>
      <td>${c.optimism != null && !Number.isNaN(c.optimism) ? signed(c.optimism) : '—'}</td>
      <td>${pct(c.consensus)}</td>
      <td>${c.total_votes.toLocaleString('en-IN')}</td>
      <td><span class="pill pos">${c.positive}</span><span class="pill neu">${c.neutral}</span><span class="pill neg">${c.negative}</span></td>
    </tr>`).join('');
}

function pollList(items, which) {
  if (!items.length) return '<p class="muted">No data.</p>';
  return items.map((r) => {
    const detail = which === 'divisive' ? `consensus ${pct(r.crowd.consensus)}`
      : which === 'engaged' ? `${r.engagement.toLocaleString('en-IN')} engagement`
      : `mood ${signed(r.mood)}`;
    return `<li>
      <span class="dot" style="background:${moodColor(r.mood)}"></span>
      <span class="pq">${esc(r.question)}</span>
      <span class="meta">${esc(r.category)} · ${detail} · ${r.crowd.total_votes} votes</span>
    </li>`;
  }).join('');
}

export function renderAdmin(model) {
  return `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Aajki · Sentiment Admin</title>
<style>
  :root { --bg:#0f1115; --card:#171a21; --line:#262b35; --text:#e8eaed; --muted:#8b93a1; --accent:#ffd54a; }
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
  .wrap{max-width:1100px;margin:0 auto;padding:28px 20px 60px}
  header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:8px}
  h1{font-size:1.4rem;margin:0;letter-spacing:-.02em}
  .sub{color:var(--muted);font-size:.85rem;margin:2px 0 22px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px;margin-bottom:22px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
  .card h3{margin:0 0 6px;font-size:.78rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
  .big{font-size:2rem;font-weight:800;letter-spacing:-.02em}
  .gauge{margin-top:8px}
  .gauge-track{position:relative;height:10px;border-radius:999px;background:linear-gradient(90deg,#d14343,#c9a227,#1f9d55)}
  .gauge-mark{position:absolute;top:-3px;width:16px;height:16px;border-radius:50%;background:#fff;border:2px solid #0f1115;transform:translateX(-50%)}
  .gauge-center{position:absolute;left:50%;top:-4px;height:18px;width:2px;background:rgba(255,255,255,.4);transform:translateX(-50%)}
  .gauge-row{display:flex;justify-content:space-between;font-size:.72rem;color:var(--muted);margin-top:8px}
  .distbar{display:flex;height:14px;border-radius:999px;overflow:hidden;margin-top:6px}
  .distlegend{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;font-size:.78rem;color:var(--muted)}
  .distlegend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}
  table{width:100%;border-collapse:collapse;font-size:.86rem}
  th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line)}
  th{color:var(--muted);font-size:.74rem;text-transform:uppercase;letter-spacing:.06em}
  .pill{display:inline-block;min-width:22px;text-align:center;border-radius:6px;padding:1px 6px;font-size:.74rem;font-weight:700;margin-right:3px}
  .pill.pos{background:rgba(31,157,85,.18);color:#5fd398}.pill.neu{background:rgba(201,162,39,.18);color:#e3c45a}.pill.neg{background:rgba(209,67,67,.18);color:#f08a8a}
  .cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  @media(max-width:720px){.cols{grid-template-columns:1fr}}
  ul.polls{list-style:none;margin:0;padding:0}
  ul.polls li{display:grid;grid-template-columns:auto 1fr;gap:8px;align-items:start;padding:9px 0;border-bottom:1px solid var(--line)}
  ul.polls .dot{width:9px;height:9px;border-radius:50%;margin-top:6px}
  ul.polls .pq{font-size:.9rem;line-height:1.35}
  ul.polls .meta{grid-column:2;color:var(--muted);font-size:.74rem}
  .muted{color:var(--muted)} a{color:var(--accent)}
  .foot{margin-top:28px;color:var(--muted);font-size:.78rem}
  .tag{display:inline-block;background:#222733;border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:.72rem;color:var(--muted)}
</style></head>
<body><div class="wrap">
  <header>
    <div><h1>Aajki · Public Sentiment</h1></div>
    <div class="tag">backend-computed · ${esc(model.total_polls)} polls · ${esc(model.total_votes.toLocaleString('en-IN'))} votes</div>
  </header>
  <div class="sub">Generated ${esc(new Date(model.generated_at).toLocaleString())} · <a href="/api/admin/sentiment">JSON</a> · auto-refreshes every 2 min</div>

  <div class="grid">
    <div class="card"><h3>Overall mood</h3><div class="big" style="color:${moodColor(model.overall_mood)}">${signed(model.overall_mood)}</div>${gauge(model.overall_mood, model.overall_mood > 0.15 ? 'upbeat' : model.overall_mood < -0.15 ? 'tense' : 'mixed')}</div>
    <div class="card"><h3>Crowd optimism (yes/no polls)</h3><div class="big" style="color:${moodColor(model.overall_optimism)}">${signed(model.overall_optimism)}</div>${gauge(model.overall_optimism, 'net yes-lean')}</div>
    <div class="card"><h3>Mood distribution</h3>${distBar(model.distribution)}</div>
  </div>

  <div class="card" style="margin-bottom:22px">
    <h3>By category</h3>
    <table><thead><tr><th>Category</th><th>Polls</th><th>Mood</th><th>Optimism</th><th>Consensus</th><th>Votes</th><th>Breakdown</th></tr></thead>
    <tbody>${catRows(model.categories)}</tbody></table>
  </div>

  <div class="cols">
    <div class="card"><h3>Most positive framing</h3><ul class="polls">${pollList(model.most_positive, 'mood')}</ul></div>
    <div class="card"><h3>Most negative framing</h3><ul class="polls">${pollList(model.most_negative, 'mood')}</ul></div>
    <div class="card"><h3>Most divisive (split crowd)</h3><ul class="polls">${pollList(model.most_divisive, 'divisive')}</ul></div>
    <div class="card"><h3>Most engaged</h3><ul class="polls">${pollList(model.most_engaged, 'engaged')}</ul></div>
  </div>

  <div class="foot">Sentiment is derived from poll wording (lexicon tone) and live vote splits (crowd leaning), computed server-side. Not an official Aajki metric.</div>
</div>
<script>setTimeout(()=>location.reload(),120000)</script>
</body></html>`;
}
