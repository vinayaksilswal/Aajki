"""Server-rendered sentiment admin portal (Python). Returns a full HTML page."""
from __future__ import annotations

import html
from datetime import datetime


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _pct(x) -> str:
    return f"{round((x or 0) * 100)}%"


def _mood_color(m) -> str:
    return "#1f9d55" if m > 0.15 else "#d14343" if m < -0.15 else "#9a7b00"


def _signed(x) -> str:
    x = x or 0
    return f"{'+' if x > 0 else ''}{x:.2f}"


def _gauge(value, label) -> str:
    left = ((value + 1) / 2) * 100
    return (
        f'<div class="gauge"><div class="gauge-track">'
        f'<div class="gauge-mark" style="left:{left}%"></div><div class="gauge-center"></div></div>'
        f'<div class="gauge-row"><span>negative</span>'
        f'<strong style="color:{_mood_color(value)}">{_signed(value)} {_esc(label)}</strong>'
        f'<span>positive</span></div></div>'
    )


def _dist_bar(d) -> str:
    total = (d["positive"] + d["neutral"] + d["negative"]) or 1
    def seg(n, c):
        return f'<div style="width:{(n / total) * 100}%;background:{c}"></div>'
    return (
        f'<div class="distbar">{seg(d["positive"], "#1f9d55")}{seg(d["neutral"], "#c9a227")}{seg(d["negative"], "#d14343")}</div>'
        f'<div class="distlegend"><span><i style="background:#1f9d55"></i>{d["positive"]} positive</span>'
        f'<span><i style="background:#c9a227"></i>{d["neutral"]} neutral</span>'
        f'<span><i style="background:#d14343"></i>{d["negative"]} negative</span></div>'
    )


def _cat_rows(categories) -> str:
    rows = []
    for c in categories:
        opt = _signed(c["optimism"]) if c["optimism"] == c["optimism"] else "—"
        rows.append(
            f'<tr><td><strong>{_esc(c["category"])}</strong></td><td>{c["count"]}</td>'
            f'<td style="color:{_mood_color(c["mood"])}">{_signed(c["mood"])}</td>'
            f'<td>{opt}</td><td>{_pct(c["consensus"])}</td>'
            f'<td>{c["total_votes"]:,}</td>'
            f'<td><span class="pill pos">{c["positive"]}</span>'
            f'<span class="pill neu">{c["neutral"]}</span>'
            f'<span class="pill neg">{c["negative"]}</span></td></tr>'
        )
    return "".join(rows)


def _poll_list(items, which) -> str:
    if not items:
        return '<p class="muted">No data.</p>'
    out = []
    for r in items:
        if which == "divisive":
            detail = f'consensus {_pct(r["crowd"]["consensus"])}'
        elif which == "engaged":
            detail = f'{r["engagement"]:,} engagement'
        else:
            detail = f'mood {_signed(r["mood"])}'
        out.append(
            f'<li><span class="dot" style="background:{_mood_color(r["mood"])}"></span>'
            f'<span class="pq">{_esc(r["question"])}</span>'
            f'<span class="meta">{_esc(r["category"])} · {detail} · {r["crowd"]["total_votes"]} votes</span></li>'
        )
    return "".join(out)


def render_admin(model) -> str:
    gen = _esc(datetime.fromisoformat(model["generated_at"]).strftime("%Y-%m-%d %H:%M"))
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Aajki · Sentiment Admin</title>
<style>
  :root {{ --bg:#0f1115; --card:#171a21; --line:#262b35; --text:#e8eaed; --muted:#8b93a1; --accent:#ffd54a; }}
  *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}}
  .wrap{{max-width:1100px;margin:0 auto;padding:28px 20px 60px}}
  header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:8px}}
  h1{{font-size:1.4rem;margin:0;letter-spacing:-.02em}}
  .sub{{color:var(--muted);font-size:.85rem;margin:2px 0 22px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px;margin-bottom:22px}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}}
  .card h3{{margin:0 0 6px;font-size:.78rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}}
  .big{{font-size:2rem;font-weight:800;letter-spacing:-.02em}}
  .gauge{{margin-top:8px}}
  .gauge-track{{position:relative;height:10px;border-radius:999px;background:linear-gradient(90deg,#d14343,#c9a227,#1f9d55)}}
  .gauge-mark{{position:absolute;top:-3px;width:16px;height:16px;border-radius:50%;background:#fff;border:2px solid #0f1115;transform:translateX(-50%)}}
  .gauge-center{{position:absolute;left:50%;top:-4px;height:18px;width:2px;background:rgba(255,255,255,.4);transform:translateX(-50%)}}
  .gauge-row{{display:flex;justify-content:space-between;font-size:.72rem;color:var(--muted);margin-top:8px}}
  .distbar{{display:flex;height:14px;border-radius:999px;overflow:hidden;margin-top:6px}}
  .distlegend{{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;font-size:.78rem;color:var(--muted)}}
  .distlegend i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}}
  table{{width:100%;border-collapse:collapse;font-size:.86rem}}
  th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line)}}
  th{{color:var(--muted);font-size:.74rem;text-transform:uppercase;letter-spacing:.06em}}
  .pill{{display:inline-block;min-width:22px;text-align:center;border-radius:6px;padding:1px 6px;font-size:.74rem;font-weight:700;margin-right:3px}}
  .pill.pos{{background:rgba(31,157,85,.18);color:#5fd398}}.pill.neu{{background:rgba(201,162,39,.18);color:#e3c45a}}.pill.neg{{background:rgba(209,67,67,.18);color:#f08a8a}}
  .cols{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  @media(max-width:720px){{.cols{{grid-template-columns:1fr}}}}
  ul.polls{{list-style:none;margin:0;padding:0}}
  ul.polls li{{display:grid;grid-template-columns:auto 1fr;gap:8px;align-items:start;padding:9px 0;border-bottom:1px solid var(--line)}}
  ul.polls .dot{{width:9px;height:9px;border-radius:50%;margin-top:6px}}
  ul.polls .pq{{font-size:.9rem;line-height:1.35}}
  ul.polls .meta{{grid-column:2;color:var(--muted);font-size:.74rem}}
  .muted{{color:var(--muted)}} a{{color:var(--accent)}}
  .foot{{margin-top:28px;color:var(--muted);font-size:.78rem}}
  .tag{{display:inline-block;background:#222733;border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:.72rem;color:var(--muted)}}
</style></head>
<body><div class="wrap">
  <header><div><h1>Aajki · Public Sentiment</h1></div>
  <div class="tag">backend-computed · {model["total_polls"]} polls · {model["total_votes"]:,} votes</div></header>
  <div class="sub">Generated {gen} · <a href="/api/admin/sentiment">JSON</a> · auto-refreshes every 2 min</div>
  <div class="grid">
    <div class="card"><h3>Overall mood</h3><div class="big" style="color:{_mood_color(model["overall_mood"])}">{_signed(model["overall_mood"])}</div>{_gauge(model["overall_mood"], "upbeat" if model["overall_mood"] > 0.15 else "tense" if model["overall_mood"] < -0.15 else "mixed")}</div>
    <div class="card"><h3>Crowd optimism (yes/no polls)</h3><div class="big" style="color:{_mood_color(model["overall_optimism"])}">{_signed(model["overall_optimism"])}</div>{_gauge(model["overall_optimism"], "net yes-lean")}</div>
    <div class="card"><h3>Mood distribution</h3>{_dist_bar(model["distribution"])}</div>
  </div>
  <div class="card" style="margin-bottom:22px"><h3>By category</h3>
    <table><thead><tr><th>Category</th><th>Polls</th><th>Mood</th><th>Optimism</th><th>Consensus</th><th>Votes</th><th>Breakdown</th></tr></thead>
    <tbody>{_cat_rows(model["categories"])}</tbody></table></div>
  <div class="cols">
    <div class="card"><h3>Most positive framing</h3><ul class="polls">{_poll_list(model["most_positive"], "mood")}</ul></div>
    <div class="card"><h3>Most negative framing</h3><ul class="polls">{_poll_list(model["most_negative"], "mood")}</ul></div>
    <div class="card"><h3>Most divisive (split crowd)</h3><ul class="polls">{_poll_list(model["most_divisive"], "divisive")}</ul></div>
    <div class="card"><h3>Most engaged</h3><ul class="polls">{_poll_list(model["most_engaged"], "engaged")}</ul></div>
  </div>
  <div class="foot">Sentiment is derived from poll wording and vote splits, computed server-side from this backend's own data.</div>
</div><script>setTimeout(()=>location.reload(),120000)</script></body></html>"""
