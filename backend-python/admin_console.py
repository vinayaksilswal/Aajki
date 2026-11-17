"""Enterprise-style admin console: server-rendered management pages (dashboard, questions,
topics, comments, audience). All data comes from the DB via store.py.
"""
from __future__ import annotations

import html
import math
from datetime import datetime

NAV = [
    ("dashboard", "Dashboard", "◧"),
    ("questions", "Questions", "▣"),
    ("news", "News", "📰"),
    ("topics", "Topics", "◆"),
    ("comments", "Comments", "✎"),
    ("audience", "Audience", "◉"),
    ("sentiment", "Sentiment", "◴"),
]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _fmt(dt) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M")
    return esc(dt)


def layout(active: str, body: str, stats: dict | None = None) -> str:
    nav = "".join(
        f'<a class="nav{" active" if key == active else ""}" href="/admin/{key}"><span>{ico}</span>{label}</a>'
        for key, label, ico in NAV)
    badge = ""
    if stats:
        badge = (f'<div class="statline">{stats["polls"]} polls · {stats["open_polls"]} open · '
                 f'{stats["users"]} users · {stats["votes"]} votes · {stats["comments"]} comments</div>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/><title>Aajki Admin</title>
<style>
 :root{{--bg:#0f1115;--panel:#171a21;--line:#262b35;--text:#e8eaed;--muted:#8b93a1;--accent:#ffd54a;--accent-ink:#1a1400;--green:#1f9d55;--red:#d14343}}
 *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;display:flex;min-height:100vh}}
 aside{{width:210px;flex:none;background:#12141a;border-right:1px solid var(--line);padding:18px 12px;position:sticky;top:0;height:100vh}}
 .brand{{display:flex;align-items:center;gap:8px;font-weight:800;font-size:1.1rem;padding:4px 8px 16px}}
 .brand .dot{{width:24px;height:24px;border-radius:7px;background:var(--accent);color:var(--accent-ink);display:grid;place-items:center;font-weight:900}}
 a.nav{{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:9px;color:var(--muted);text-decoration:none;font-weight:600;font-size:.9rem;margin-bottom:2px}}
 a.nav span{{width:18px;text-align:center}}
 a.nav:hover{{background:#1b1f27;color:var(--text)}} a.nav.active{{background:var(--accent);color:var(--accent-ink)}}
 main{{flex:1;padding:24px 28px 60px;max-width:1100px}}
 h1{{margin:0 0 2px;font-size:1.3rem}} .statline{{color:var(--muted);font-size:.82rem;margin-bottom:20px}}
 .card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px}}
 .card h2{{margin:0 0 12px;font-size:1rem}}
 table{{width:100%;border-collapse:collapse;font-size:.86rem}} th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
 th{{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}}
 input,select,textarea{{width:100%;background:#0f131a;border:1px solid var(--line);border-radius:9px;padding:9px 11px;color:var(--text);font:inherit}}
 textarea{{min-height:70px;resize:vertical}} label{{display:block;font-size:.78rem;color:var(--muted);margin:10px 0 5px;font-weight:600}}
 .row{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .row3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}}
 .btn{{display:inline-block;background:var(--accent);color:var(--accent-ink);border:none;border-radius:9px;padding:9px 16px;font-weight:700;cursor:pointer;text-decoration:none;font-size:.88rem}}
 .btn.ghost{{background:transparent;border:1px solid var(--line);color:var(--text)}} .btn.danger{{background:var(--red);color:#fff}}
 .btn.sm{{padding:5px 10px;font-size:.78rem}}
 .pill{{display:inline-block;border-radius:999px;padding:2px 9px;font-size:.72rem;font-weight:700}}
 .pill.open{{background:rgba(31,157,85,.18);color:#5fd398}} .pill.closed{{background:rgba(209,67,67,.18);color:#f08a8a}}
 .pill.blk{{background:rgba(209,67,67,.18);color:#f08a8a}}
 .muted{{color:var(--muted)}} .inline{{display:inline}} .actions{{display:flex;gap:6px;flex-wrap:wrap}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}}
 .kpi{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}} .kpi .n{{font-size:1.7rem;font-weight:800}} .kpi .l{{color:var(--muted);font-size:.76rem;text-transform:uppercase;letter-spacing:.05em}}
 a{{color:var(--accent)}}
</style></head><body>
<aside><div class="brand"><span class="dot">A</span> Aajki</div>{nav}</aside>
<main>{body}</main></body></html>"""


def page_dashboard(stats, sentiment_model) -> str:
    kpis = "".join(f'<div class="kpi"><div class="n">{stats[k]}</div><div class="l">{lbl}</div></div>'
                   for k, lbl in [("polls", "Questions"), ("open_polls", "Open"), ("users", "Audience"),
                                  ("votes", "Votes"), ("comments", "Comments"), ("blocked", "Blocked")])
    mood = sentiment_model["overall_mood"]
    body = (f'<h1>Dashboard</h1><div class="statline">Live overview of your app</div>'
            f'<div class="kpis">{kpis}</div>'
            f'<div class="card"><h2>Public mood</h2>'
            f'<div style="font-size:2rem;font-weight:800;color:{"#1f9d55" if mood>0.15 else "#d14343" if mood<-0.15 else "#9a7b00"}">{"+" if mood>0 else ""}{mood:.2f}</div>'
            f'<p class="muted">Across {sentiment_model["total_polls"]} questions · {sentiment_model["total_votes"]:,} votes. '
            f'Full breakdown on the <a href="/admin/sentiment">Sentiment</a> page.</p></div>'
            f'<div class="card"><h2>Quick actions</h2><div class="actions">'
            f'<a class="btn" href="/admin/questions#new">+ New question</a>'
            f'<a class="btn ghost" href="/admin/topics">Manage topics</a>'
            f'<a class="btn ghost" href="/admin/audience">View audience</a></div></div>')
    return layout("dashboard", body, stats)


def _options_text(options) -> str:
    return "\n".join(o.get("label", "") for o in options)


def _question_form(action, topics, poll=None) -> str:
    poll = poll or {}
    cats = ["politics", "movies", "cricket", "tech", "money"]
    cur_cat = poll.get("category", "politics")
    cat_opts = "".join(f'<option{" selected" if c==cur_cat else ""}>{c}</option>' for c in cats)
    topt = '<option value="">— none —</option>' + "".join(
        f'<option value="{esc(t["id"])}"{" selected" if t["id"]==poll.get("topic_id") else ""}>{esc(t["title"])}</option>'
        for t in topics)
    kind = poll.get("display_kind", "binary")
    opts_text = _options_text(poll.get("options", [])) if poll.get("display_kind") == "multi" else ""
    return f"""<form method="post" action="{action}">
      <label>Question</label><textarea name="question" required>{esc(poll.get("question",""))}</textarea>
      <div class="row">
        <div><label>Category</label><select name="category">{cat_opts}</select></div>
        <div><label>Topic</label><select name="topic_id">{topt}</select></div>
      </div>
      <div class="row3">
        <div><label>Type</label><select name="display_kind" onchange="document.getElementById('mo').style.display=this.value=='multi'?'block':'none'">
          <option value="binary"{" selected" if kind=="binary" else ""}>Yes / No</option>
          <option value="multi"{" selected" if kind=="multi" else ""}>Multiple choice</option></select></div>
        <div><label>Reward coins</label><input name="reward_coins" type="number" value="{poll.get("reward_coins",5)}"/></div>
        <div><label>Image URL (optional)</label><input name="image_url" value="{esc(poll.get("image_url",""))}"/></div>
      </div>
      <div id="mo" style="display:{'block' if kind=='multi' else 'none'}"><label>Options (one per line, for multiple choice)</label>
        <textarea name="options_text">{esc(opts_text)}</textarea></div>
      <label><input type="checkbox" name="trending" value="1" style="width:auto"{" checked" if poll.get("trending") else ""}/> Trending</label>
      <label><input type="checkbox" name="is_prediction" value="1" style="width:auto"{" checked" if poll.get("is_prediction") else ""}/> Prediction</label>
      <div style="margin-top:14px"><button class="btn" type="submit">{"Save changes" if poll else "Create question"}</button></div>
    </form>"""


def page_questions(polls, topics, stats) -> str:
    rows = ""
    for p in polls:
        rows += (f'<tr><td><strong>{esc(p["question"])}</strong><div class="muted" style="font-size:.76rem">{esc(p["id"])}</div></td>'
                 f'<td>{esc(p["category"])}</td><td>{p["total_votes"]}</td><td>{p["comment_count"]}</td>'
                 f'<td><span class="pill {p["status"]}">{p["status"]}</span></td>'
                 f'<td><div class="actions">'
                 f'<a class="btn ghost sm" href="/admin/questions/{esc(p["id"])}">Edit</a>'
                 f'<form class="inline" method="post" action="/admin/questions/{esc(p["id"])}/status"><input type="hidden" name="status" value="{"closed" if p["status"]=="open" else "open"}"><button class="btn ghost sm">{"Close" if p["status"]=="open" else "Open"}</button></form>'
                 f'<form class="inline" method="post" action="/admin/questions/{esc(p["id"])}/delete" onsubmit="return confirm(\'Delete this question?\')"><button class="btn danger sm">Delete</button></form>'
                 f'</div></td></tr>')
    body = (f'<h1>Questions</h1><div class="statline">{len(polls)} total</div>'
            f'<div class="card" id="new"><h2>New question</h2>{_question_form("/admin/questions/new", topics)}</div>'
            f'<div class="card"><h2>All questions</h2><table><thead><tr><th>Question</th><th>Category</th><th>Votes</th><th>Comments</th><th>Status</th><th>Actions</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')
    return layout("questions", body, stats)


def page_edit_question(poll, topics, stats) -> str:
    body = (f'<h1>Edit question</h1><div class="statline">{esc(poll["id"])}</div>'
            f'<div class="card">{_question_form("/admin/questions/"+poll["id"], topics, poll)}</div>'
            f'<a class="btn ghost" href="/admin/questions">← Back to questions</a>')
    return layout("questions", body, stats)


def page_topics(topics, stats) -> str:
    rows = "".join(
        f'<tr><td><strong>{esc(t["title"])}</strong></td><td>{esc(t["category"])}</td><td>{t["poll_count"]}</td>'
        f'<td><form class="inline" method="post" action="/admin/topics/{esc(t["id"])}/delete" onsubmit="return confirm(\'Delete topic? Its polls stay but become untagged.\')"><button class="btn danger sm">Delete</button></form></td></tr>'
        for t in topics)
    body = (f'<h1>Topics</h1><div class="statline">{len(topics)} topics</div>'
            f'<div class="card"><h2>New topic</h2><form method="post" action="/admin/topics/new">'
            f'<label>Title</label><input name="title" required/>'
            f'<div class="row"><div><label>Category</label><input name="category" value="politics"/></div>'
            f'<div><label>Short label</label><input name="short_label"/></div></div>'
            f'<label>Blurb</label><textarea name="blurb"></textarea>'
            f'<label>Image URL</label><input name="image_url"/>'
            f'<div style="margin-top:12px"><button class="btn">Create topic</button></div></form></div>'
            f'<div class="card"><h2>All topics</h2><table><thead><tr><th>Title</th><th>Category</th><th>Polls</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>')
    return layout("topics", body, stats)


def page_comments(comments, stats) -> str:
    rows = ""
    for c in comments:
        badge = ' <span class="pill blk">hidden</span>' if c["hidden"] else ''
        rows += (f'<tr><td>{esc(c["body"])}{badge}</td>'
                 f'<td>{esc(c["author_name"])}</td><td class="muted">{esc(c["poll_q"])}</td><td class="muted">{_fmt(c["created_at"])}</td>'
                 f'<td><div class="actions">'
                 f'<form class="inline" method="post" action="/admin/comments/{c["id"]}/hide"><input type="hidden" name="hidden" value="{0 if c["hidden"] else 1}"><button class="btn ghost sm">{"Unhide" if c["hidden"] else "Hide"}</button></form>'
                 f'<form class="inline" method="post" action="/admin/comments/{c["id"]}/delete" onsubmit="return confirm(\'Delete comment?\')"><button class="btn danger sm">Delete</button></form>'
                 f'</div></td></tr>')
    body = (f'<h1>Comments</h1><div class="statline">{len(comments)} recent</div>'
            f'<div class="card"><table><thead><tr><th>Comment</th><th>Author</th><th>On</th><th>When</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>')
    return layout("comments", body, stats)


def page_audience(users, stats) -> str:
    rows = ""
    for u in users:
        badge = '<span class="pill blk">blocked</span>' if u["blocked"] else ''
        rows += (f'<tr><td><strong>{esc(u["display_name"])}</strong> {badge}'
                 f'<div class="muted" style="font-size:.76rem">{esc(u["handle"] or u["id"])}</div></td>'
                 f'<td class="muted">{esc(u["phone"])}</td><td>{u["coins"]}</td><td>{u["votes"]}</td><td class="muted">{_fmt(u["created_at"])}</td>'
                 f'<td><form class="inline" method="post" action="/admin/audience/{esc(u["id"])}/block"><input type="hidden" name="blocked" value="{0 if u["blocked"] else 1}">'
                 f'<button class="btn {"ghost" if u["blocked"] else "danger"} sm">{"Unblock" if u["blocked"] else "Block"}</button></form></td></tr>')
    body = (f'<h1>Audience</h1><div class="statline">{len(users)} users · {stats["blocked"]} blocked</div>'
            f'<div class="card"><table><thead><tr><th>User</th><th>Phone</th><th>Coins</th><th>Votes</th><th>Joined</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>')
    return layout("audience", body, stats)


def _mood_color(m) -> str:
    return "#1f9d55" if m > 0.15 else "#d14343" if m < -0.15 else "#e3b32a"


def _signed(x) -> str:
    x = x or 0
    return f"{'+' if x > 0 else ''}{x:.2f}"


def speedometer(value: float, caption: str, lo: float = -1.0, hi: float = 1.0) -> str:
    """A semicircular speedometer gauge (inline SVG, self-contained)."""
    frac = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    cx, cy, r = 110.0, 110.0, 92.0
    ang = math.radians(180.0 * (1.0 - frac))           # 180°(lo, left) .. 0°(hi, right)
    nx, ny = cx + r * 0.80 * math.cos(ang), cy - r * 0.80 * math.sin(ang)
    lx, ly = cx - r, cy                                # arc start (left)
    rx, ry = cx + r, cy                                # arc end (right)
    col = _mood_color(value)
    # tick at the zero mark (centre)
    zx, zy = cx, cy - r
    return f"""<svg viewBox="0 0 220 136" width="100%" style="max-width:300px">
  <defs><linearGradient id="gm{abs(hash(caption))%9999}" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#d14343"/><stop offset="0.5" stop-color="#e3b32a"/><stop offset="1" stop-color="#1f9d55"/>
  </linearGradient></defs>
  <path d="M {lx} {ly} A {r} {r} 0 0 1 {rx} {ry}" fill="none" stroke="url(#gm{abs(hash(caption))%9999})" stroke-width="16" stroke-linecap="round"/>
  <line x1="{cx}" y1="{cy-r-4:.0f}" x2="{cx}" y2="{cy-r+14:.0f}" stroke="#0f1115" stroke-width="3"/>
  <line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{col}" stroke-width="4" stroke-linecap="round"/>
  <circle cx="{cx}" cy="{cy}" r="9" fill="{col}"/>
  <text x="{lx}" y="{cy+20:.0f}" fill="#8b93a1" font-size="11" text-anchor="middle">−1</text>
  <text x="{zx}" y="{zy-6:.0f}" fill="#8b93a1" font-size="11" text-anchor="middle">0</text>
  <text x="{rx}" y="{cy+20:.0f}" fill="#8b93a1" font-size="11" text-anchor="middle">+1</text>
  <text x="{cx}" y="{cy-16:.0f}" fill="{col}" font-size="30" font-weight="800" text-anchor="middle">{_signed(value)}</text>
  <text x="{cx}" y="{cy+6:.0f}" fill="#8b93a1" font-size="11" text-anchor="middle">{esc(caption)}</text>
</svg>"""


def _dist_bar(d) -> str:
    total = (d["positive"] + d["neutral"] + d["negative"]) or 1
    def seg(n, c, lbl):
        w = n / total * 100
        return f'<div style="width:{w:.1f}%;background:{c}" title="{lbl}: {n}"></div>'
    return (f'<div style="display:flex;height:16px;border-radius:999px;overflow:hidden;margin-top:6px">'
            f'{seg(d["positive"], "#1f9d55", "positive")}{seg(d["neutral"], "#e3b32a", "neutral")}{seg(d["negative"], "#d14343", "negative")}</div>'
            f'<div style="display:flex;gap:16px;margin-top:8px;font-size:.8rem;color:var(--muted)">'
            f'<span>● {d["positive"]} positive</span><span>● {d["neutral"]} neutral</span><span>● {d["negative"]} negative</span></div>')


def _cat_table(categories) -> str:
    rows = ""
    for c in categories:
        opt = _signed(c["optimism"]) if c["optimism"] == c["optimism"] else "—"
        rows += (f'<tr><td><strong>{esc(c["category"])}</strong></td><td>{c["count"]}</td>'
                 f'<td style="color:{_mood_color(c["mood"])}">{_signed(c["mood"])}</td><td>{opt}</td>'
                 f'<td>{round(c["consensus"]*100)}%</td><td>{c["total_votes"]:,}</td>'
                 f'<td><span class="pill open">{c["positive"]}</span> <span class="pill" style="background:rgba(201,162,39,.18);color:#e3c45a">{c["neutral"]}</span> <span class="pill closed">{c["negative"]}</span></td></tr>')
    return (f'<table><thead><tr><th>Category</th><th>Polls</th><th>Mood</th><th>Optimism</th>'
            f'<th>Consensus</th><th>Votes</th><th>Breakdown</th></tr></thead><tbody>{rows}</tbody></table>')


def _poll_list(items, kind) -> str:
    if not items:
        return '<p class="muted">No data.</p>'
    out = ""
    for r in items:
        if kind == "divisive":
            detail = f'consensus {round(r["crowd"]["consensus"]*100)}%'
        elif kind == "engaged":
            detail = f'{r["engagement"]:,} engagement'
        else:
            detail = f'mood {_signed(r["mood"])}'
        out += (f'<li style="display:flex;gap:9px;padding:9px 0;border-bottom:1px solid var(--line)">'
                f'<span style="width:9px;height:9px;border-radius:50%;background:{_mood_color(r["mood"])};margin-top:5px;flex:none"></span>'
                f'<span>{esc(r["question"])}<div class="muted" style="font-size:.74rem">{esc(r["category"])} · {detail} · {r["crowd"]["total_votes"]} votes</div></span></li>')
    return f'<ul style="list-style:none;margin:0;padding:0">{out}</ul>'


def page_sentiment(sentiment_model, stats) -> str:
    m = sentiment_model
    body = (
        f'<h1>Sentiment</h1><div class="statline">Public mood, computed server-side from {m["total_polls"]} questions · {m["total_votes"]:,} votes</div>'
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-bottom:18px">'
        f'<div class="card" style="text-align:center"><h2>Overall mood</h2>{speedometer(m["overall_mood"], "mood")}</div>'
        f'<div class="card" style="text-align:center"><h2>Crowd optimism</h2>{speedometer(m["overall_optimism"], "net yes-lean")}</div>'
        f'<div class="card"><h2>Mood distribution</h2>{_dist_bar(m["distribution"])}</div></div>'
        f'<div class="card"><h2>By category</h2>{_cat_table(m["categories"])}</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">'
        f'<div class="card"><h2>Most positive framing</h2>{_poll_list(m["most_positive"], "mood")}</div>'
        f'<div class="card"><h2>Most negative framing</h2>{_poll_list(m["most_negative"], "mood")}</div>'
        f'<div class="card"><h2>Most divisive</h2>{_poll_list(m["most_divisive"], "divisive")}</div>'
        f'<div class="card"><h2>Most engaged</h2>{_poll_list(m["most_engaged"], "engaged")}</div></div>'
    )
    return layout("sentiment", body, stats)


def page_news(news_by_cat: dict, imported: set, stats) -> str:
    sections = ""
    total = sum(len(v) for v in news_by_cat.values())
    for cat, items in news_by_cat.items():
        if not items:
            continue
        rows = ""
        for it in items:
            done = it["title"] in imported
            fields = (f'<input type="hidden" name="title" value="{esc(it["title"])}">'
                      f'<input type="hidden" name="category" value="{esc(cat)}">'
                      f'<input type="hidden" name="source" value="{esc(it["source"])}">'
                      f'<input type="hidden" name="link" value="{esc(it["link"])}">')
            action = ('<span class="pill open">✓ published</span>' if done else
                      f'<form class="inline" method="post" action="/admin/news/publish">{fields}<button class="btn sm">Publish</button></form>')
            rows += (f'<tr><td>{esc(it["title"])}<div class="muted" style="font-size:.74rem">{esc(it["source"])}</div></td>'
                     f'<td style="white-space:nowrap">{action}</td></tr>')
        sections += (f'<div class="card"><h2 style="text-transform:capitalize">{esc(cat)} '
                     f'<form class="inline" method="post" action="/admin/news/import" style="float:right">'
                     f'<input type="hidden" name="category" value="{esc(cat)}"><button class="btn ghost sm">Publish all new</button></form></h2>'
                     f'<table><tbody>{rows}</tbody></table></div>')
    body = (f'<h1>News</h1><div class="statline">Live headlines from Google News · {total} fetched · '
            f'publish any as a “Good news / Bad news” poll</div>'
            f'<div class="card"><form method="post" action="/admin/news/import"><input type="hidden" name="category" value="all">'
            f'<button class="btn">⚡ Auto-import latest from every category</button> '
            f'<span class="muted" style="margin-left:10px">Creates reaction polls from the newest headlines (skips duplicates).</span></form></div>'
            f'{sections or "<div class=card><p class=muted>No headlines fetched right now — Google News may be rate-limiting. Try again shortly.</p></div>"}')
    return layout("news", body, stats)
