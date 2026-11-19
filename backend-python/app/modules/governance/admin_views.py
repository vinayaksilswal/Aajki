"""Server-rendered admin pages. Every dynamic value is HTML-escaped via esc()."""
from __future__ import annotations

import html
import math
from datetime import datetime, timedelta, timezone

from app.modules.forecasts.models import CATEGORIES

IST = timezone(timedelta(hours=5, minutes=30), "IST")

NAV = [
    ("dashboard", "Dashboard", "◧"),
    ("questions", "Questions", "▣"),
    ("news", "News", "≡"),
    ("topics", "Topics", "◆"),
    ("comments", "Comments", "✎"),
    ("audience", "Audience", "◉"),
    ("sentiment", "Sentiment", "◴"),
]

STATUS_PILL = {"draft": "muted", "scheduled": "info", "open": "ok", "paused": "warn",
               "closed": "muted", "settled": "info", "voided": "bad"}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def ist(dt) -> str:
    dt = _aware(dt)
    return dt.astimezone(IST).strftime("%d %b %Y, %H:%M IST") if dt else "—"


def to_local_input(dt) -> str:
    dt = _aware(dt)
    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M") if dt else ""


def parse_local_input(value: str | None):
    """`datetime-local` values are entered in IST; store UTC."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%dT%H:%M").replace(tzinfo=IST).astimezone(timezone.utc)
    except ValueError:
        return "invalid"


def layout(active: str, title: str, body: str, flash: str = "") -> str:
    nav = "".join(
        f'<a class="nav{" active" if key == active else ""}" href="/admin/{key}"><span>{ico}</span>{label}</a>'
        for key, label, ico in NAV)
    note = f'<div class="flash">{esc(flash)}</div>' if flash else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/><meta name="robots" content="noindex"/>
<title>{esc(title)} · Bharat Foreseez Admin</title>
<style>
 :root{{--bg:#0f1115;--panel:#171a21;--line:#262b35;--text:#e8eaed;--muted:#8b93a1;--accent:#e8873a;--accent-ink:#1a0d00;--ok:#5fd398;--bad:#f08a8a;--warn:#e3c45a;--info:#8ab4f8}}
 *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;display:flex;min-height:100vh}}
 aside{{width:216px;flex:none;background:#12141a;border-right:1px solid var(--line);padding:18px 12px;position:sticky;top:0;height:100vh}}
 .brand{{font-weight:800;font-size:1.02rem;padding:4px 8px 16px;line-height:1.2}} .brand small{{display:block;color:var(--muted);font-weight:600;font-size:.72rem;margin-top:2px}}
 .brand b{{color:var(--accent)}}
 a.nav{{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:9px;color:var(--muted);text-decoration:none;font-weight:600;font-size:.9rem;margin-bottom:2px}}
 a.nav span{{width:18px;text-align:center}} a.nav:hover{{background:#1b1f27;color:var(--text)}} a.nav.active{{background:var(--accent);color:var(--accent-ink)}}
 main{{flex:1;padding:24px 28px 60px;max-width:1180px;min-width:0}}
 h1{{margin:0 0 4px;font-size:1.3rem}} .sub{{color:var(--muted);font-size:.84rem;margin-bottom:18px}}
 .card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px}} .card h2{{margin:0 0 12px;font-size:1rem}}
 table{{width:100%;border-collapse:collapse;font-size:.86rem}} th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
 th{{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}}
 input,select,textarea{{width:100%;background:#0f131a;border:1px solid var(--line);border-radius:9px;padding:9px 11px;color:var(--text);font:inherit}}
 input[readonly],textarea[readonly],select[disabled]{{opacity:.6}}
 textarea{{min-height:70px;resize:vertical}} label{{display:block;font-size:.78rem;color:var(--muted);margin:12px 0 5px;font-weight:600}}
 .hint{{color:var(--muted);font-size:.74rem;margin-top:4px}} .err{{color:var(--bad);font-size:.78rem;margin-top:4px;font-weight:600}}
 .row{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .row3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}}
 .check{{display:flex;gap:8px;align-items:center;margin-top:12px;font-size:.86rem;color:var(--text)}} .check input{{width:auto}}
 .btn{{display:inline-block;background:var(--accent);color:var(--accent-ink);border:none;border-radius:9px;padding:9px 16px;font-weight:700;cursor:pointer;text-decoration:none;font-size:.88rem}}
 .btn.ghost{{background:transparent;border:1px solid var(--line);color:var(--text)}} .btn.danger{{background:#d14343;color:#fff}} .btn.sm{{padding:5px 10px;font-size:.78rem}}
 .pill{{display:inline-block;border-radius:999px;padding:2px 9px;font-size:.72rem;font-weight:700;background:#222833;color:var(--muted)}}
 .pill.ok{{background:rgba(31,157,85,.18);color:var(--ok)}} .pill.bad{{background:rgba(209,67,67,.18);color:var(--bad)}}
 .pill.warn{{background:rgba(201,162,39,.18);color:var(--warn)}} .pill.info{{background:rgba(66,133,244,.18);color:var(--info)}}
 .muted{{color:var(--muted)}} .inline{{display:inline}} .actions{{display:flex;gap:6px;flex-wrap:wrap}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}}
 .kpi{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}} .kpi .n{{font-size:1.7rem;font-weight:800}} .kpi .l{{color:var(--muted);font-size:.76rem;text-transform:uppercase;letter-spacing:.05em}}
 .flash{{background:rgba(232,135,58,.14);border:1px solid rgba(232,135,58,.4);border-radius:10px;padding:10px 14px;margin-bottom:16px;font-size:.88rem}}
 .banner{{background:rgba(66,133,244,.10);border:1px solid rgba(66,133,244,.35);border-radius:10px;padding:10px 14px;font-size:.84rem;margin-bottom:12px}}
 a{{color:var(--accent)}}
</style></head><body>
<aside><div class="brand">Bharat <b>Foreseez</b><small>Admin &amp; governance</small></div>{nav}</aside>
<main>{note}{body}</main></body></html>"""


def page_dashboard(k: dict, sentiment: dict) -> str:
    tiles = [("questions", "Questions"), ("open", "Open now"), ("drafts", "Drafts"),
             ("users", "Audience"), ("calls", "Calls"), ("comments", "Comments")]
    kpis = "".join(f'<div class="kpi"><div class="n">{k.get(key, 0):,}</div><div class="l">{lbl}</div></div>'
                   for key, lbl in tiles)
    mood = sentiment.get("overall_mood", 0) or 0
    body = (f'<h1>Dashboard</h1><div class="sub">Live overview</div><div class="kpis">{kpis}</div>'
            f'<div class="card"><h2>Mood signal <span class="muted" style="font-weight:400">(admin only)</span></h2>'
            f'<div style="font-size:2rem;font-weight:800;color:{_mood_color(mood)}">{_signed(mood)}</div>'
            f'<p class="muted">Across {sentiment.get("total_polls", 0)} published questions. '
            f'See <a href="/admin/sentiment">Sentiment</a>.</p></div>'
            f'<div class="card"><h2>Quick actions</h2><div class="actions">'
            f'<a class="btn" href="/admin/questions#new">+ New question</a>'
            f'<a class="btn ghost" href="/admin/news">Draft from news</a>'
            f'<a class="btn ghost" href="/admin/comments">Moderate comments</a></div></div>')
    return layout("dashboard", "Dashboard", body)


# ------------------------------------------------------------------ question form

def _field_err(errors: dict, name: str) -> str:
    return f'<div class="err">{esc(errors[name])}</div>' if name in errors else ""


def question_form(action: str, topics: list, v: dict, errors: dict, locked: bool) -> str:
    """`v` holds the values to show (from the record, or the admin's rejected submission)."""
    ro = " readonly" if locked else ""
    dis = " disabled" if locked else ""
    cat_opts = "".join(f'<option value="{key}"{" selected" if v.get("category") == key else ""}>{label}</option>'
                       for key, label in CATEGORIES.items())
    topic_opts = '<option value="">— none —</option>' + "".join(
        f'<option value="{esc(t.id)}"{" selected" if t.id == v.get("topic_id") else ""}>{esc(t.title)}</option>'
        for t in topics)
    lock_note = ('<div class="banner">Published: the question, outcomes, timing and resolution '
                 'terms are locked so everyone forecasts on the same terms. Void it and draft a new '
                 'one to change them.</div>') if locked else ""
    context = ""
    if v.get("source_headline"):
        link = v.get("source_link")
        source = (f' (<a href="{esc(link)}" target="_blank" rel="noopener noreferrer">source</a>)'
                  if link else "")
        context = (f'<div class="banner">Drafted from the headline: <em>{esc(v["source_headline"])}</em>'
                   f'{source}<br>Rewrite it as a question with a clear, checkable outcome.</div>')
    return f"""<form method="post" action="{esc(action)}">{lock_note}{context}
  <label for="f_title">Question</label>
  <textarea id="f_title" name="title" maxlength="200" required{ro}>{esc(v.get("title"))}</textarea>
  <div class="hint">A yes/no question with an outcome that an official source will confirm. Spec vocabulary: forecast, call, chance, points, reward.</div>{_field_err(errors, "title")}
  <div class="row">
    <div><label for="f_cat">Category</label><select id="f_cat" name="category"{dis}>{cat_opts}</select>{_field_err(errors, "category")}</div>
    <div><label for="f_topic">Topic (optional)</label><select id="f_topic" name="topic_id">{topic_opts}</select></div>
  </div>
  <div class="row">
    <div><label for="f_yes">"Yes" outcome label</label><input id="f_yes" name="outcome_yes" maxlength="40" value="{esc(v.get("outcome_yes", "Yes"))}"{ro}></div>
    <div><label for="f_no">"No" outcome label</label><input id="f_no" name="outcome_no" maxlength="40" value="{esc(v.get("outcome_no", "No"))}"{ro}></div>
  </div>{_field_err(errors, "outcomes")}
  <div class="row">
    <div><label for="f_open">Opens (IST)</label><input id="f_open" type="datetime-local" name="opens_at" value="{esc(v.get("opens_at_input"))}"{ro}><div class="hint">Leave empty to open when published.</div>{_field_err(errors, "opens_at")}</div>
    <div><label for="f_close">Closes (IST)</label><input id="f_close" type="datetime-local" name="closes_at" value="{esc(v.get("closes_at_input"))}"{ro}>{_field_err(errors, "closes_at")}</div>
  </div>
  <label for="f_src">Resolution source (official https link)</label>
  <input id="f_src" name="resolution_source_url" placeholder="https://results.eci.gov.in/" value="{esc(v.get("resolution_source_url"))}"{ro}>{_field_err(errors, "resolution_source_url")}
  <label for="f_rule">Resolution rule</label>
  <textarea id="f_rule" name="resolution_rule" placeholder="Resolves Yes if the official result published by … shows …"{ro}>{esc(v.get("resolution_rule"))}</textarea>{_field_err(errors, "resolution_rule")}
  <label for="f_desc">Context shown to users (optional)</label>
  <textarea id="f_desc" name="description" maxlength="600">{esc(v.get("description"))}</textarea>{_field_err(errors, "description")}
  <label for="f_img">Image URL (optional, https)</label>
  <input id="f_img" name="image_url" value="{esc(v.get("image_url"))}">{_field_err(errors, "image_url")}
  <label class="check"><input type="checkbox" name="election_sensitive" value="1"{" checked" if v.get("election_sensitive") else ""}> Election-sensitive (live chance can be withheld during a quiet period)</label>
  <label class="check"><input type="checkbox" name="trending" value="1"{" checked" if v.get("trending") else ""}> Feature in Trending</label>
  <div style="margin-top:16px"><button class="btn" type="submit">{esc(v.get("_submit", "Save draft"))}</button></div>
</form>"""


def _actions(row: dict) -> str:
    qid, st = esc(row["id"]), row["status"]
    buttons = {"draft": [("publish", "Publish", "")],
               "scheduled": [("unpublish", "Back to draft", "ghost"), ("void", "Void", "danger")],
               "open": [("pause", "Pause", "ghost"), ("void", "Void", "danger")],
               "paused": [("resume", "Resume", ""), ("void", "Void", "danger")],
               "closed": [("void", "Void", "danger")]}.get(st, [])
    out = f'<a class="btn ghost sm" href="/admin/questions/{qid}">{"Edit" if st == "draft" else "View"}</a>'
    for action, label, kind in buttons:
        confirm = ' onsubmit="return confirm(\'Void this question? Calls on it will be refunded once the ledger is live.\')"' if action == "void" else ""
        out += (f'<form class="inline" method="post" action="/admin/questions/{qid}/transition"{confirm}>'
                f'<input type="hidden" name="action" value="{action}"><button class="btn {kind} sm">{label}</button></form>')
    if st == "draft":
        out += (f'<form class="inline" method="post" action="/admin/questions/{qid}/delete" '
                f'onsubmit="return confirm(\'Delete this draft?\')"><button class="btn danger sm">Delete</button></form>')
    return f'<div class="actions">{out}</div>'


def page_questions(rows: list, topics: list, form_values: dict, errors: dict, flash: str = "") -> str:
    trs = "".join(
        f'<tr><td><strong>{esc(r["title"])}</strong>'
        f'{" <span class=pill>election</span>" if r["election_sensitive"] else ""}'
        f'<div class="muted" style="font-size:.74rem">{esc(r["id"])}</div></td>'
        f'<td>{esc(CATEGORIES.get(r["category"], r["category"]))}</td>'
        f'<td><span class="pill {STATUS_PILL.get(r["status"], "")}">{esc(r["status"])}</span></td>'
        f'<td class="muted">{ist(r["closes_at"])}</td><td>{r["participants"]:,}</td><td>{_actions(r)}</td></tr>'
        for r in rows) or '<tr><td colspan="6" class="muted">No questions yet.</td></tr>'
    body = (f'<h1>Questions</h1><div class="sub">{len(rows)} total. Drafts stay private until published; '
            f'publishing needs a closing time, an official resolution source and a rule.</div>'
            f'<div class="card"><h2>All questions</h2><table><thead><tr><th>Question</th><th>Category</th>'
            f'<th>Status</th><th>Closes</th><th>Calls</th><th></th></tr></thead><tbody>{trs}</tbody></table></div>'
            f'<div class="card" id="new"><h2>New question</h2>'
            f'{question_form("/admin/questions", topics, form_values, errors, locked=False)}</div>')
    return layout("questions", "Questions", body, flash)


def page_question(qid: str, status: str, topics: list, values: dict, errors: dict, flash: str = "") -> str:
    locked = status != "draft"
    actions = _actions({"id": qid, "status": status})
    body = (f'<h1>{"Edit draft" if not locked else "Question"}</h1>'
            f'<div class="sub">{esc(qid)} · <span class="pill {STATUS_PILL.get(status, "")}">{esc(status)}</span></div>'
            f'<div class="card">{actions}</div>'
            f'<div class="card">{question_form("/admin/questions/" + qid, topics, values, errors, locked)}</div>'
            f'<a class="btn ghost" href="/admin/questions">← All questions</a>')
    return layout("questions", "Question", body, flash)


# ------------------------------------------------------------------ news

def page_news(items: list, flash: str = "") -> str:
    trs = ""
    for it in items:
        status = (f'<a class="pill info" href="/admin/questions/{esc(it.question_id)}">drafted</a>'
                  if it.question_id else "")
        hidden = '<span class="pill bad">hidden</span>' if it.hidden else ""
        trs += (f'<tr><td>{esc(it.title)} {status} {hidden}<div class="muted" style="font-size:.74rem">'
                f'{esc(it.source)} · {ist(it.published_at or it.fetched_at)} · '
                f'<a href="{esc(it.link)}" target="_blank" rel="noopener noreferrer">open</a></div></td>'
                f'<td>{esc(CATEGORIES.get(it.category, it.category))}</td>'
                f'<td><div class="actions">'
                f'<form class="inline" method="post" action="/admin/news/{esc(it.id)}/draft"><button class="btn sm">{"Open draft" if it.question_id else "Draft question"}</button></form>'
                f'<form class="inline" method="post" action="/admin/news/{esc(it.id)}/hide"><input type="hidden" name="hidden" value="{0 if it.hidden else 1}">'
                f'<button class="btn ghost sm">{"Show in ticker" if it.hidden else "Hide from ticker"}</button></form>'
                f'</div></td></tr>')
    trs = trs or '<tr><td colspan="3" class="muted">No headlines yet. Refresh to fetch the latest.</td></tr>'
    body = (f'<h1>News</h1><div class="sub">Headlines feed the in-app context ticker. They are never '
            f'published as questions automatically: draft one, rewrite it as a checkable question, add '
            f'the resolution source, then publish.</div>'
            f'<div class="banner">Staging source: Google News RSS. Before public launch the spec requires '
            f'a licensed or editorial news source.</div>'
            f'<div class="card"><form method="post" action="/admin/news/refresh"><button class="btn">Refresh headlines</button>'
            f' <span class="muted" style="margin-left:8px">Also runs daily via the scheduled job.</span></form></div>'
            f'<div class="card"><table><thead><tr><th>Headline</th><th>Category</th><th></th></tr></thead>'
            f'<tbody>{trs}</tbody></table></div>')
    return layout("news", "News", body, flash)


# ------------------------------------------------------------------ topics / comments / audience

def page_topics(topics: list, counts: dict, flash: str = "") -> str:
    cat_opts = "".join(f'<option value="{k}">{v}</option>' for k, v in CATEGORIES.items())
    trs = "".join(
        f'<tr><td><strong>{esc(t.title)}</strong></td><td>{esc(CATEGORIES.get(t.category, t.category))}</td>'
        f'<td>{counts.get(t.id, 0)}</td><td><form class="inline" method="post" action="/admin/topics/{esc(t.id)}/delete" '
        f'onsubmit="return confirm(\'Delete topic? Its questions stay, untagged.\')"><button class="btn danger sm">Delete</button></form></td></tr>'
        for t in topics) or '<tr><td colspan="4" class="muted">No topics.</td></tr>'
    body = (f'<h1>Topics</h1><div class="sub">{len(topics)} topics</div>'
            f'<div class="card"><h2>New topic</h2><form method="post" action="/admin/topics">'
            f'<label for="t_title">Title</label><input id="t_title" name="title" required maxlength="200">'
            f'<div class="row"><div><label for="t_cat">Category</label><select id="t_cat" name="category">{cat_opts}</select></div>'
            f'<div><label for="t_short">Short label</label><input id="t_short" name="short_label" maxlength="120"></div></div>'
            f'<label for="t_blurb">Blurb</label><textarea id="t_blurb" name="blurb"></textarea>'
            f'<div style="margin-top:12px"><button class="btn">Create topic</button></div></form></div>'
            f'<div class="card"><table><thead><tr><th>Title</th><th>Category</th><th>Questions</th><th></th></tr></thead><tbody>{trs}</tbody></table></div>')
    return layout("topics", "Topics", body, flash)


def page_comments(comments: list, flash: str = "") -> str:
    trs = ""
    for c in comments:
        badge = ' <span class="pill bad">hidden</span>' if c["hidden"] else ""
        trs += (f'<tr><td>{esc(c["body"])}{badge}</td><td>{esc(c["author_name"])}</td>'
                f'<td class="muted">{esc((c["question_title"] or "")[:70])}</td><td class="muted">{ist(c["created_at"])}</td>'
                f'<td><div class="actions">'
                f'<form class="inline" method="post" action="/admin/comments/{c["id"]}/hide"><input type="hidden" name="hidden" value="{0 if c["hidden"] else 1}"><button class="btn ghost sm">{"Restore" if c["hidden"] else "Hide"}</button></form>'
                f'<form class="inline" method="post" action="/admin/comments/{c["id"]}/delete" onsubmit="return confirm(\'Delete comment?\')"><button class="btn danger sm">Delete</button></form>'
                f'</div></td></tr>')
    trs = trs or '<tr><td colspan="5" class="muted">No comments.</td></tr>'
    body = (f'<h1>Comments</h1><div class="sub">{len(comments)} most recent. The reason-coded moderation queue arrives with the debate module.</div>'
            f'<div class="card"><table><thead><tr><th>Comment</th><th>Author</th><th>On</th><th>When</th><th></th></tr></thead><tbody>{trs}</tbody></table></div>')
    return layout("comments", "Comments", body, flash)


def page_audience(users: list, k: dict, flash: str = "") -> str:
    trs = "".join(
        f'<tr><td><strong>{esc(u["display_name"])}</strong> {"<span class=pill bad>blocked</span>" if u["blocked"] else ""}'
        f'<div class="muted" style="font-size:.74rem">{esc(u["handle"] or u["id"])}</div></td>'
        f'<td class="muted">{esc(u["phone"])}</td><td>{u["calls"]:,}</td><td class="muted">{ist(u["created_at"])}</td>'
        f'<td><form class="inline" method="post" action="/admin/audience/{esc(u["id"])}/block"><input type="hidden" name="blocked" value="{0 if u["blocked"] else 1}">'
        f'<button class="btn {"ghost" if u["blocked"] else "danger"} sm">{"Unblock" if u["blocked"] else "Block"}</button></form></td></tr>'
        for u in users) or '<tr><td colspan="5" class="muted">No users yet.</td></tr>'
    body = (f'<h1>Audience</h1><div class="sub">{k.get("users", 0)} users · {k.get("blocked", 0)} blocked · phone numbers are masked</div>'
            f'<div class="card"><table><thead><tr><th>User</th><th>Phone</th><th>Calls</th><th>Joined</th><th></th></tr></thead><tbody>{trs}</tbody></table></div>')
    return layout("audience", "Audience", body, flash)


# ------------------------------------------------------------------ sentiment (admin signal)

def _mood_color(m) -> str:
    return "#1f9d55" if m > 0.15 else "#d14343" if m < -0.15 else "#e3b32a"


def _signed(x) -> str:
    x = x or 0
    return f"{'+' if x > 0 else ''}{x:.2f}"


def speedometer(value: float, caption: str, gid: str) -> str:
    frac = max(0.0, min(1.0, (value + 1.0) / 2.0))
    cx, cy, r = 110.0, 110.0, 92.0
    ang = math.radians(180.0 * (1.0 - frac))
    nx, ny = cx + r * 0.80 * math.cos(ang), cy - r * 0.80 * math.sin(ang)
    col = _mood_color(value)
    return f"""<svg viewBox="0 0 220 136" width="100%" style="max-width:300px" role="img" aria-label="{esc(caption)} {_signed(value)}">
  <defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#d14343"/><stop offset="0.5" stop-color="#e3b32a"/><stop offset="1" stop-color="#1f9d55"/></linearGradient></defs>
  <path d="M {cx - r} {cy} A {r} {r} 0 0 1 {cx + r} {cy}" fill="none" stroke="url(#{gid})" stroke-width="16" stroke-linecap="round"/>
  <line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{col}" stroke-width="4" stroke-linecap="round"/>
  <circle cx="{cx}" cy="{cy}" r="9" fill="{col}"/>
  <text x="{cx}" y="{cy - 16:.0f}" fill="{col}" font-size="30" font-weight="800" text-anchor="middle">{_signed(value)}</text>
  <text x="{cx}" y="{cy + 6:.0f}" fill="#8b93a1" font-size="11" text-anchor="middle">{esc(caption)}</text>
</svg>"""


def page_sentiment(m: dict) -> str:
    rows = "".join(
        f'<tr><td><strong>{esc(CATEGORIES.get(c["category"], c["category"]))}</strong></td><td>{c["count"]}</td>'
        f'<td style="color:{_mood_color(c["mood"])}">{_signed(c["mood"])}</td><td>{round(c["consensus"] * 100)}%</td>'
        f'<td>{c["total_votes"]:,}</td></tr>'
        for c in m.get("categories", [])) or '<tr><td colspan="5" class="muted">No published questions yet.</td></tr>'
    body = (f'<h1>Sentiment</h1><div class="sub">Admin-only signal from question wording and call split · '
            f'{m.get("total_polls", 0)} questions · {m.get("total_votes", 0):,} calls. The public, anonymised '
            f'dashboard (minimum group of 50) is part of a later milestone.</div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-bottom:18px">'
            f'<div class="card" style="text-align:center"><h2>Overall mood</h2>{speedometer(m.get("overall_mood", 0) or 0, "mood", "g1")}</div>'
            f'<div class="card" style="text-align:center"><h2>Crowd lean</h2>{speedometer(m.get("overall_optimism", 0) or 0, "net yes-lean", "g2")}</div></div>'
            f'<div class="card"><h2>By category</h2><table><thead><tr><th>Category</th><th>Questions</th><th>Mood</th>'
            f'<th>Consensus</th><th>Calls</th></tr></thead><tbody>{rows}</tbody></table></div>')
    return layout("sentiment", "Sentiment", body)
