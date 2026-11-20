"""Server-rendered admin pages. Every dynamic value is HTML-escaped via esc()."""
from __future__ import annotations

import html
import math
from datetime import datetime, timedelta

from app.clock import IST, aware
from app.modules.forecasts.models import CATEGORIES
from app.regions import STATES

# (key, label, icon, permission needed to see it)
NAV = [
    ("dashboard", "Dashboard", "◧", "dashboard.read"),
    ("questions", "Questions", "▣", "questions.read"),
    ("settlements", "Settlement", "⚖", "questions.read"),
    ("disputes", "Disputes", "⚑", "disputes.review"),
    ("news", "News", "≡", "news.write"),
    ("topics", "Topics", "◆", "topics.write"),
    ("quiz", "Daily quiz", "?", "quiz.write"),
    ("moderation", "Moderation", "✎", "moderation.act"),
    ("users", "Users", "◉", "users.read"),
    ("grievances", "Grievances", "✉", "grievances.handle"),
    ("policy", "Regions & flags", "⚙", "policy.manage"),
    ("economy", "Points economy", "◎", "economy.manage"),
    ("badges", "Ranks & badges", "★", "economy.manage"),
    ("ops", "Operations", "↗", "ops.read"),
    ("sentiment", "Sentiment", "◴", "dashboard.read"),
    ("admins", "Admin accounts", "⚿", "admins.manage"),
    ("audit", "Audit log", "☰", "audit.read"),
]

STATUS_PILL = {"draft": "muted", "scheduled": "info", "open": "ok", "paused": "warn",
               "closed": "muted", "settled": "info", "voided": "bad", "proposed": "warn",
               "approved": "ok", "rejected": "bad", "superseded": "muted", "upheld": "ok",
               "dismissed": "muted", "in_progress": "info", "resolved": "ok", "visible": "ok",
               "held": "warn", "removed": "bad", "deleted": "muted", "active": "info",
               "correct": "ok", "incorrect": "muted", "refunded": "muted"}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def ist(dt) -> str:
    dt = aware(dt)
    return dt.astimezone(IST).strftime("%d %b %Y, %H:%M IST") if dt else "—"


def to_local_input(dt) -> str:
    dt = aware(dt)
    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M") if dt else ""


def parse_local_input(value: str | None):
    """`datetime-local` values are entered in IST; store UTC."""
    from datetime import timezone
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%dT%H:%M").replace(tzinfo=IST).astimezone(timezone.utc)
    except ValueError:
        return "invalid"


def pill(status: str) -> str:
    return f'<span class="pill {STATUS_PILL.get(status, "")}">{esc(status.replace("_", " "))}</span>'


def post_button(action: str, label: str, kind: str = "", hidden: dict | None = None,
                confirm: str | None = None) -> str:
    fields = "".join(f'<input type="hidden" name="{esc(k)}" value="{esc(v)}">' for k, v in (hidden or {}).items())
    onsubmit = f' onsubmit="return confirm(\'{esc(confirm)}\')"' if confirm else ""
    return (f'<form class="inline" method="post" action="{esc(action)}"{onsubmit}>{fields}'
            f'<button class="btn {kind} sm">{esc(label)}</button></form>')


def table(headers: list[str], rows: list[str], empty: str = "Nothing here yet.") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(rows) or f'<tr><td colspan="{len(headers)}" class="muted">{esc(empty)}</td></tr>'
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def kpis(items: list[tuple[str, object, str]]) -> str:
    """(label, value, tone) tiles; tone '' | 'warn' | 'bad'."""
    tiles = "".join(f'<div class="kpi {t}"><div class="n">{esc(f"{v:,}" if isinstance(v, int) else v)}</div>'
                    f'<div class="l">{esc(lbl)}</div></div>' for lbl, v, t in items)
    return f'<div class="kpis">{tiles}</div>'


def err(errors: dict, name: str) -> str:
    return f'<div class="err">{esc(errors[name])}</div>' if errors and name in errors else ""


def options(choices: dict, selected) -> str:
    return "".join(f'<option value="{esc(k)}"{" selected" if k == selected else ""}>{esc(v)}</option>'
                   for k, v in choices.items())


CSS = """
 :root{--bg:#0f1115;--panel:#171a21;--line:#262b35;--text:#e8eaed;--muted:#8b93a1;--accent:#e8873a;--accent-ink:#1a0d00;--ok:#5fd398;--bad:#f08a8a;--warn:#e3c45a;--info:#8ab4f8}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;display:flex;min-height:100vh}
 aside{width:220px;flex:none;background:#12141a;border-right:1px solid var(--line);padding:18px 12px;position:sticky;top:0;height:100vh;overflow-y:auto}
 .brand{font-weight:800;font-size:1.02rem;padding:4px 8px 12px;line-height:1.2} .brand small{display:block;color:var(--muted);font-weight:600;font-size:.72rem;margin-top:2px} .brand b{color:var(--accent)}
 .who{font-size:.74rem;color:var(--muted);padding:0 8px 12px;border-bottom:1px solid var(--line);margin-bottom:10px} .who b{color:var(--text);display:block}
 a.nav{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:9px;color:var(--muted);text-decoration:none;font-weight:600;font-size:.86rem;margin-bottom:2px}
 a.nav span{width:18px;text-align:center} a.nav:hover{background:#1b1f27;color:var(--text)} a.nav.active{background:var(--accent);color:var(--accent-ink)}
 main{flex:1;padding:24px 28px 60px;max-width:1200px;min-width:0}
 h1{margin:0 0 4px;font-size:1.3rem} .sub{color:var(--muted);font-size:.84rem;margin-bottom:18px}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px} .card h2{margin:0 0 12px;font-size:1rem}
 .scroll{overflow-x:auto} table{width:100%;border-collapse:collapse;font-size:.85rem} th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
 th{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.06em}
 input,select,textarea{width:100%;background:#0f131a;border:1px solid var(--line);border-radius:9px;padding:9px 11px;color:var(--text);font:inherit}
 input[readonly],textarea[readonly],select[disabled]{opacity:.6} select[multiple]{min-height:140px}
 textarea{min-height:70px;resize:vertical} label{display:block;font-size:.78rem;color:var(--muted);margin:12px 0 5px;font-weight:600}
 .hint{color:var(--muted);font-size:.74rem;margin-top:4px} .err{color:var(--bad);font-size:.78rem;margin-top:4px;font-weight:600}
 .row{display:grid;grid-template-columns:1fr 1fr;gap:14px} .row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
 .check{display:flex;gap:8px;align-items:center;margin-top:12px;font-size:.86rem;color:var(--text)} .check input{width:auto}
 .btn{display:inline-block;background:var(--accent);color:var(--accent-ink);border:none;border-radius:9px;padding:9px 16px;font-weight:700;cursor:pointer;text-decoration:none;font-size:.88rem}
 .btn.ghost{background:transparent;border:1px solid var(--line);color:var(--text)} .btn.danger{background:#d14343;color:#fff} .btn.sm{padding:5px 10px;font-size:.78rem}
 .pill{display:inline-block;border-radius:999px;padding:2px 9px;font-size:.72rem;font-weight:700;background:#222833;color:var(--muted);white-space:nowrap}
 .pill.ok{background:rgba(31,157,85,.18);color:var(--ok)} .pill.bad{background:rgba(209,67,67,.18);color:var(--bad)}
 .pill.warn{background:rgba(201,162,39,.18);color:var(--warn)} .pill.info{background:rgba(66,133,244,.18);color:var(--info)}
 .muted{color:var(--muted)} .inline{display:inline} .actions{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
 .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:18px}
 .kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px} .kpi .n{font-size:1.6rem;font-weight:800} .kpi .l{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.05em}
 .kpi.warn .n{color:var(--warn)} .kpi.bad .n{color:var(--bad)}
 .flash{background:rgba(232,135,58,.14);border:1px solid rgba(232,135,58,.4);border-radius:10px;padding:10px 14px;margin-bottom:16px;font-size:.88rem}
 .banner{background:rgba(66,133,244,.10);border:1px solid rgba(66,133,244,.35);border-radius:10px;padding:10px 14px;font-size:.84rem;margin-bottom:12px}
 .bars{display:flex;align-items:flex-end;gap:4px;height:90px} .bars div{flex:1;background:var(--accent);border-radius:3px 3px 0 0;min-height:2px;position:relative}
 .bars div span{position:absolute;bottom:100%;left:0;right:0;text-align:center;font-size:.62rem;color:var(--muted)}
 .bar-labels{display:flex;gap:4px;font-size:.6rem;color:var(--muted)} .bar-labels span{flex:1;text-align:center}
 a{color:var(--accent)} code{background:#0f131a;padding:2px 6px;border-radius:6px}
 .center{max-width:420px;margin:8vh auto;width:100%} body.plain{display:block}
 @media (max-width:800px){body{display:block} aside{position:static;width:auto;height:auto} .row,.row3{grid-template-columns:1fr}}
"""


def layout(ctx, active: str, title: str, body: str, flash: str = "") -> str:
    nav = "".join(
        f'<a class="nav{" active" if key == active else ""}" href="/admin/{key}"><span>{ico}</span>{label}</a>'
        for key, label, ico, perm in NAV if ctx.can(perm))
    note = f'<div class="flash">{esc(flash)}</div>' if flash else ""
    from app.modules.governance.auth import ROLES
    roles = ", ".join(ROLES.get(r, r) for r in ctx.roles)
    who = (f'<div class="who"><b>{esc(ctx.admin.name)}</b>{esc(roles)}<br>'
           f'<form class="inline" method="post" action="/admin/logout"><button class="btn ghost sm" style="margin-top:6px">Sign out</button></form></div>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/><meta name="robots" content="noindex"/>
<title>{esc(title)} · Bharat Foreseez Admin</title><style>{CSS}</style></head><body>
<aside><div class="brand">Bharat <b>Foreseez</b><small>Admin &amp; governance</small></div>{who}{nav}</aside>
<main>{note}{body}</main></body></html>"""


def plain(title: str, body: str, flash: str = "") -> str:
    note = f'<div class="flash">{esc(flash)}</div>' if flash else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/><meta name="robots" content="noindex"/>
<title>{esc(title)} · Bharat Foreseez Admin</title><style>{CSS}</style></head><body class="plain">
<div class="center"><div class="brand" style="font-size:1.2rem">Bharat <b>Foreseez</b><small>Admin &amp; governance</small></div>
{note}<div class="card">{body}</div></div></body></html>"""


# ------------------------------------------------------------------ sign-in pages

def page_login(flash: str = "", bootstrap: bool = False) -> str:
    hint = ('<div class="banner">No admin accounts exist yet. Sign in with the bootstrap login '
            '(ADMIN_USER / ADMIN_PASSWORD) to create the first Super Admin.</div>') if bootstrap else ""
    return plain("Sign in", f"""<h1>Sign in</h1>{hint}<form method="post" action="/admin/login">
<label for="l_email">Username</label><input id="l_email" name="email" autocomplete="username" required>
<label for="l_pw">Password</label><input id="l_pw" type="password" name="password" autocomplete="current-password" required>
<div style="margin-top:16px"><button class="btn">Continue</button></div></form>""", flash)


def page_totp(flash: str = "") -> str:
    return plain("Two-factor sign-in", f"""<h1>Two-factor sign-in</h1>
<p class="muted">Enter the 6-digit code from your authenticator app.</p>
<form method="post" action="/admin/2fa"><label for="t_code">Code</label>
<input id="t_code" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required autofocus>
<div style="margin-top:16px"><button class="btn">Verify</button></div></form>
<form method="post" action="/admin/logout" style="margin-top:10px"><button class="btn ghost sm">Cancel</button></form>""", flash)


def page_totp_setup(secret: str, qr_svg_data: str, flash: str = "") -> str:
    return plain("Set up two-factor sign-in", f"""<h1>Set up two-factor sign-in</h1>
<p class="muted">Two-factor sign-in is required for every admin. Scan this with Google Authenticator,
Microsoft Authenticator or a similar app, then enter the code it shows.</p>
<div style="background:#fff;border-radius:10px;padding:10px;width:max-content;margin:10px 0"><img alt="QR code" src="{esc(qr_svg_data)}" width="200" height="200"></div>
<p class="hint">Can't scan? Enter this key manually: <code>{esc(secret)}</code></p>
<form method="post" action="/admin/2fa/setup"><label for="s_code">Code from the app</label>
<input id="s_code" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" required>
<div style="margin-top:16px"><button class="btn">Turn on two-factor sign-in</button></div></form>""", flash)


def page_password(ctx, forced: bool, errors: dict, flash: str = "") -> str:
    body = (f'<h1>Change password</h1><div class="sub">{"Set a new password before continuing." if forced else ""}</div>'
            f'<div class="card"><form method="post" action="/admin/password">'
            f'<label for="p_cur">Current password</label><input id="p_cur" type="password" name="current" required autocomplete="current-password">{err(errors, "current")}'
            f'<label for="p_new">New password</label><input id="p_new" type="password" name="new" required autocomplete="new-password">'
            f'<div class="hint">At least 12 characters, with upper and lower case letters and a number.</div>{err(errors, "new")}'
            f'<div style="margin-top:16px"><button class="btn">Save</button></div></form></div>')
    return layout(ctx, "", "Password", body, flash)


# ------------------------------------------------------------------ dashboard

def page_dashboard(ctx, k: dict, mood: float, total_polls: int) -> str:
    tiles = [("Questions", k.get("questions", 0), ""), ("Open now", k.get("open", 0), ""),
             ("Drafts", k.get("drafts", 0), ""),
             ("Awaiting result", k.get("awaiting_result", 0), "warn" if k.get("awaiting_result") else ""),
             ("Results to approve", k.get("pending_settlements", 0), "warn" if k.get("pending_settlements") else ""),
             ("Open disputes", k.get("open_disputes", 0), "warn" if k.get("open_disputes") else ""),
             ("Users", k.get("users", 0), ""), ("Active today", k.get("dau", 0), ""),
             ("Calls", k.get("calls", 0), ""),
             ("Reports open", k.get("reports_open", 0), "bad" if k.get("reports_overdue") else ""),
             ("Grievances open", k.get("grievances_open", 0), "bad" if k.get("grievances_unacknowledged") else "")]
    actions = []
    if ctx.can("questions.write"):
        actions += ['<a class="btn" href="/admin/questions#new">+ New question</a>',
                    '<a class="btn ghost" href="/admin/news">Draft from news</a>']
    if ctx.can("settlement.propose") or ctx.can("settlement.approve"):
        actions.append('<a class="btn ghost" href="/admin/settlements">Settlement queue</a>')
    if ctx.can("moderation.act"):
        actions.append('<a class="btn ghost" href="/admin/moderation">Moderation queue</a>')
    if ctx.can("grievances.handle"):
        actions.append('<a class="btn ghost" href="/admin/grievances">Grievances</a>')
    warn = ""
    if k.get("reports_overdue"):
        warn += f'<div class="flash">{k["reports_overdue"]} reported comment(s) are past the 24-hour handling target.</div>'
    if k.get("grievances_unacknowledged"):
        warn += f'<div class="flash">{k["grievances_unacknowledged"]} grievance(s) have not been acknowledged within 24 hours.</div>'
    body = (f'<h1>Dashboard</h1><div class="sub">Live overview</div>{warn}{kpis(tiles)}'
            f'<div class="card"><h2>Mood signal <span class="muted" style="font-weight:400">(admin only)</span></h2>'
            f'<div style="font-size:2rem;font-weight:800;color:{_mood_color(mood)}">{_signed(mood)}</div>'
            f'<p class="muted">Across {total_polls} published questions. See <a href="/admin/sentiment">Sentiment</a>.</p></div>'
            f'<div class="card"><h2>Quick actions</h2><div class="actions">{"".join(actions) or "<span class=muted>None for your role.</span>"}</div></div>')
    return layout(ctx, "dashboard", "Dashboard", body)


# ------------------------------------------------------------------ questions

def question_form(action: str, topics: list, v: dict, errors: dict, locked: bool, can_write: bool) -> str:
    ro = " readonly" if locked or not can_write else ""
    dis = " disabled" if locked or not can_write else ""
    soft = "" if can_write else " disabled"
    cat_opts = options(CATEGORIES, v.get("category"))
    topic_opts = '<option value="">— none —</option>' + "".join(
        f'<option value="{esc(t.id)}"{" selected" if t.id == v.get("topic_id") else ""}>{esc(t.title)}</option>' for t in topics)
    state_opts = '<option value="">National / not state-specific</option>' + options(
        dict(sorted(STATES.items(), key=lambda kv: kv[1])), v.get("election_state"))
    lock_note = ('<div class="banner">Published: the question, outcomes, timing and resolution terms are locked '
                 'so everyone forecasts on the same terms. Void it and draft a new one to change them.</div>') if locked else ""
    context = ""
    if v.get("source_headline"):
        link = v.get("source_link")
        source = f' (<a href="{esc(link)}" target="_blank" rel="noopener noreferrer">source</a>)' if link else ""
        context = (f'<div class="banner">Drafted from the headline: <em>{esc(v["source_headline"])}</em>{source}<br>'
                   f'Rewrite it as a question with a clear, checkable outcome.</div>')
    submit = f'<div style="margin-top:16px"><button class="btn" type="submit">{esc(v.get("_submit", "Save draft"))}</button></div>' if can_write else ""
    return f"""<form method="post" action="{esc(action)}">{lock_note}{context}
  <label for="f_title">Question</label>
  <textarea id="f_title" name="title" maxlength="200" required{ro}>{esc(v.get("title"))}</textarea>
  <div class="hint">A yes/no question with an outcome an official source will confirm. Vocabulary: forecast, call, chance, points, reward.</div>{err(errors, "title")}
  <div class="row">
    <div><label for="f_cat">Category</label><select id="f_cat" name="category"{dis}>{cat_opts}</select>{err(errors, "category")}</div>
    <div><label for="f_topic">Topic (optional)</label><select id="f_topic" name="topic_id"{soft}>{topic_opts}</select></div>
  </div>
  <div class="row">
    <div><label for="f_yes">"Yes" outcome label</label><input id="f_yes" name="outcome_yes" maxlength="40" value="{esc(v.get("outcome_yes", "Yes"))}"{ro}></div>
    <div><label for="f_no">"No" outcome label</label><input id="f_no" name="outcome_no" maxlength="40" value="{esc(v.get("outcome_no", "No"))}"{ro}></div>
  </div>{err(errors, "outcomes")}
  <div class="row">
    <div><label for="f_open">Opens (IST)</label><input id="f_open" type="datetime-local" name="opens_at" value="{esc(v.get("opens_at_input"))}"{ro}><div class="hint">Leave empty to open when published; a future time schedules it.</div>{err(errors, "opens_at")}</div>
    <div><label for="f_close">Closes (IST)</label><input id="f_close" type="datetime-local" name="closes_at" value="{esc(v.get("closes_at_input"))}"{ro}><div class="hint">No calls are accepted after this time.</div>{err(errors, "closes_at")}</div>
  </div>
  <label for="f_src">Resolution source (official https link)</label>
  <input id="f_src" name="resolution_source_url" placeholder="https://results.eci.gov.in/" value="{esc(v.get("resolution_source_url"))}"{ro}>{err(errors, "resolution_source_url")}
  <label for="f_rule">Resolution rule</label>
  <textarea id="f_rule" name="resolution_rule" placeholder="Resolves Yes if the official result published by … shows …"{ro}>{esc(v.get("resolution_rule"))}</textarea>
  <div class="hint">Shown to users before the question opens, with how points are calculated: a correct call receives points committed × total points ÷ points on the winning outcome.</div>{err(errors, "resolution_rule")}
  <label for="f_desc">Context shown to users (optional)</label>
  <textarea id="f_desc" name="description" maxlength="600"{soft}>{esc(v.get("description"))}</textarea>{err(errors, "description")}
  <label for="f_img">Image URL (optional, https)</label>
  <input id="f_img" name="image_url" value="{esc(v.get("image_url"))}"{soft}>{err(errors, "image_url")}
  <label class="check"><input type="checkbox" name="election_sensitive" value="1"{" checked" if v.get("election_sensitive") else ""}{soft}> Election-sensitive (live chance hidden while a quiet period covers its state)</label>
  <div class="row"><div><label for="f_state">Election state</label><select id="f_state" name="election_state"{soft}>{state_opts}</select></div><div></div></div>
  <label class="check"><input type="checkbox" name="trending" value="1"{" checked" if v.get("trending") else ""}{soft}> Feature in Trending</label>
  {submit}
</form>"""


def question_actions(qid: str, status: str, can_write: bool) -> str:
    if not can_write:
        return f'<a class="btn ghost sm" href="/admin/questions/{esc(qid)}">View</a>'
    buttons = {"draft": [("publish", "Publish", "")],
               "scheduled": [("unpublish", "Back to draft", "ghost"), ("void", "Void", "danger")],
               "open": [("pause", "Pause", "ghost"), ("void", "Void", "danger")],
               "paused": [("resume", "Resume", ""), ("void", "Void", "danger")],
               "closed": [("void", "Void", "danger")]}.get(status, [])
    out = f'<a class="btn ghost sm" href="/admin/questions/{esc(qid)}">{"Edit" if status == "draft" else "View"}</a>'
    for action, label, kind in buttons:
        out += post_button(f"/admin/questions/{qid}/transition", label, kind, {"action": action},
                           "Void this question? Every committed point is returned." if action == "void" else None)
    if status == "draft":
        out += post_button(f"/admin/questions/{qid}/delete", "Delete", "danger", None, "Delete this draft?")
    return f'<div class="actions">{out}</div>'


def page_questions(ctx, rows: list, topics: list, values: dict, errors: dict, flash: str = "") -> str:
    can_write = ctx.can("questions.write")
    trs = [f'<tr><td><strong>{esc(r["title"])}</strong>{" <span class=pill>election</span>" if r["election_sensitive"] else ""}'
           f'<div class="muted" style="font-size:.72rem">{esc(r["id"])}</div></td>'
           f'<td>{esc(CATEGORIES.get(r["category"], r["category"]))}</td><td>{pill(r["status"])}</td>'
           f'<td class="muted">{ist(r["closes_at"])}</td><td>{r["participants"]:,}</td>'
           f'<td>{question_actions(r["id"], r["status"], can_write)}</td></tr>' for r in rows]
    new = (f'<div class="card" id="new"><h2>New question</h2>{question_form("/admin/questions", topics, values, errors, False, True)}</div>'
           if can_write else "")
    body = (f'<h1>Questions</h1><div class="sub">{len(rows)} total. Drafts stay private until published; '
            f'publishing needs a closing time, an official resolution source and a rule.</div>'
            f'<div class="card"><h2>All questions</h2>{table(["Question", "Category", "Status", "Closes", "Calls", ""], trs)}</div>{new}')
    return layout(ctx, "questions", "Questions", body, flash)


def settlement_panel(ctx, qid: str, status: str, outcomes: list, totals: dict, history: list,
                     disputes: list, names: dict, errors: dict) -> str:
    labels = {o["key"]: o["label"] for o in outcomes}
    total_pts = sum(v["points"] for v in totals.values())
    rows = [f'<tr><td>{esc(labels.get(k, k))}</td><td>{v["calls"]:,}</td><td>{v["points"]:,}</td>'
            f'<td>{round(v["points"] * 100 / total_pts) if total_pts else 0}%</td></tr>' for k, v in totals.items()]
    out = f'<div class="card"><h2>Calls and settlement</h2>{table(["Outcome", "Calls", "Points committed", "Share"], rows, "No calls yet.")}'
    pending = next((p for p in history if p.status == "proposed"), None)
    approved = next((p for p in history if p.status == "approved"), None)
    if pending:
        res = "Void (cancelled event)" if pending.result == "void" else labels.get(pending.result, pending.result)
        out += (f'<div class="banner" style="margin-top:14px"><b>Proposed result: {esc(res)}</b> by {esc(names.get(pending.proposed_by, pending.proposed_by))} '
                f'on {ist(pending.proposed_at)}{" (correction)" if pending.corrects_id else ""}<br>'
                f'{"Source: <a href=" + chr(34) + esc(pending.source_url) + chr(34) + " target=_blank rel=noopener>" + esc(pending.source_url) + "</a><br>" if pending.source_url else ""}'
                f'{esc(pending.note or "")}</div>')
        if ctx.can("settlement.approve") and pending.proposed_by != ctx.admin.id:
            out += (f'<div class="row"><form method="post" action="/admin/settlements/{esc(pending.id)}/approve" '
                    f'onsubmit="return confirm(\'Approve this result? Points are released immediately.\')">'
                    f'<label>Note (optional)</label><input name="note" maxlength="500"><div style="margin-top:8px"><button class="btn">Approve and release points</button></div></form>'
                    f'<form method="post" action="/admin/settlements/{esc(pending.id)}/reject"><label>Reason for rejecting</label>'
                    f'<input name="note" required maxlength="500"><div style="margin-top:8px"><button class="btn danger">Reject</button></div></form></div>')
        elif ctx.can("settlement.approve"):
            out += '<p class="muted">You proposed this result, so a different admin must approve it.</p>'
        else:
            out += '<p class="muted">Waiting for a Settlement Approver.</p>'
    elif ctx.can("settlement.propose") and (status in ("closed", "open", "paused") or approved):
        window = approved and approved.dispute_until and aware(approved.dispute_until) > datetime.now(aware(approved.dispute_until).tzinfo)
        if status in ("closed", "open", "paused") or window:
            choices = {k: labels[k] for k in labels}
            choices["void"] = "Void: event cancelled or abandoned"
            heading = "Propose a correction" if approved else ("Propose the result" if status == "closed" else "Void a cancelled event")
            if status in ("open", "paused") and not approved:
                choices = {"void": choices["void"]}
            out += (f'<h3 style="font-size:.92rem;margin-top:16px">{heading}</h3>'
                    f'<form method="post" action="/admin/questions/{esc(qid)}/settlement">'
                    f'<div class="row"><div><label>Result</label><select name="result">{options(choices, None)}</select>{err(errors, "result")}</div>'
                    f'<div><label>Official source used (https)</label><input name="source_url" placeholder="https://">{err(errors, "source_url")}</div></div>'
                    f'<label>Note</label><textarea name="note" placeholder="What the source shows; for a void, why the event was cancelled."></textarea>{err(errors, "note")}'
                    f'<div style="margin-top:12px"><button class="btn">Submit for approval</button></div></form>')
    if history:
        hrows = [f'<tr><td>{esc("Void" if p.result == "void" else labels.get(p.result, p.result))}</td><td>{pill(p.status)}</td>'
                 f'<td>{esc(names.get(p.proposed_by, p.proposed_by))}<div class="muted">{ist(p.proposed_at)}</div></td>'
                 f'<td>{esc(names.get(p.decided_by, p.decided_by or "—"))}<div class="muted">{ist(p.decided_at)}</div></td>'
                 f'<td>{esc(p.applied_result or "")} {esc(p.applied_reason or "")}<div class="muted">{esc(p.decision_note or "")}</div></td>'
                 f'<td class="muted">{ist(p.dispute_until) if p.status == "approved" else ""}</td></tr>' for p in history]
        out += f'<h3 style="font-size:.92rem;margin-top:16px">Settlement history</h3>{table(["Result", "Status", "Proposed", "Decided", "Applied", "Disputes until"], hrows)}'
    if disputes:
        drows = [f'<tr><td>{esc(d.reason)}{" <a href=" + chr(34) + esc(d.evidence_url) + chr(34) + " target=_blank rel=noopener>evidence</a>" if d.evidence_url else ""}</td>'
                 f'<td>{pill(d.status)}</td><td class="muted">{ist(d.created_at)}</td></tr>' for d in disputes]
        out += f'<h3 style="font-size:.92rem;margin-top:16px">Disputes</h3>{table(["Reason", "Status", "Raised"], drows)}'
    return out + "</div>"


def page_question(ctx, qid: str, status: str, topics: list, values: dict, errors: dict,
                  panel: str, flash: str = "") -> str:
    locked = status != "draft"
    body = (f'<h1>{"Edit draft" if not locked else "Question"}</h1>'
            f'<div class="sub">{esc(qid)} · {pill(status)}</div>'
            f'<div class="card">{question_actions(qid, status, ctx.can("questions.write"))}</div>'
            f'{panel if locked else ""}'
            f'<div class="card">{question_form("/admin/questions/" + qid, topics, values, errors, locked, ctx.can("questions.write"))}</div>'
            f'<a class="btn ghost" href="/admin/questions">← All questions</a>')
    return layout(ctx, "questions", "Question", body, flash)


def page_settlements(ctx, awaiting: list, pending: list, recent: list, titles: dict, names: dict, flash: str = "") -> str:
    a = [f'<tr><td><a href="/admin/questions/{esc(q.id)}">{esc(q.title)}</a></td><td class="muted">{ist(q.closes_at)}</td>'
         f'<td>{calls:,}</td></tr>' for q, calls in awaiting]
    p = [f'<tr><td><a href="/admin/questions/{esc(x.question_id)}">{esc(titles.get(x.question_id, x.question_id))}</a></td>'
         f'<td>{esc(x.result)}{" (correction)" if x.corrects_id else ""}</td><td>{esc(names.get(x.proposed_by, x.proposed_by))}</td>'
         f'<td class="muted">{ist(x.proposed_at)}</td></tr>' for x in pending]
    r = [f'<tr><td><a href="/admin/questions/{esc(x.question_id)}">{esc(titles.get(x.question_id, x.question_id))}</a></td>'
         f'<td>{esc(x.applied_result or x.result)}</td><td>{pill(x.status)}</td><td>{esc(names.get(x.proposed_by, ""))} → {esc(names.get(x.decided_by, "—"))}</td>'
         f'<td class="muted">{ist(x.decided_at)}</td></tr>' for x in recent]
    body = (f'<h1>Settlement</h1><div class="sub">A Settlement Officer proposes each result with its official source; '
            f'a different admin with the Settlement Approver role approves it, which releases points. '
            f'Formula: points committed × total points ÷ points on the winning outcome (rounded down).</div>'
            f'<div class="card"><h2>Closed, awaiting a result</h2>{table(["Question", "Closed", "Calls"], a, "Nothing waiting.")}</div>'
            f'<div class="card"><h2>Proposed, awaiting approval</h2>{table(["Question", "Result", "Proposed by", "When"], p, "Nothing waiting.")}</div>'
            f'<div class="card"><h2>Recent decisions</h2>{table(["Question", "Result", "Status", "Officer → Approver", "Decided"], r)}</div>')
    return layout(ctx, "settlements", "Settlement", body, flash)


def page_disputes(ctx, rows: list, titles: dict, flash: str = "") -> str:
    trs = [f'<tr><td><a href="/admin/questions/{esc(d.question_id)}">{esc(titles.get(d.question_id, d.question_id))}</a>'
           f'<div>{esc(d.reason)}</div>{"<a href=" + chr(34) + esc(d.evidence_url) + chr(34) + " target=_blank rel=noopener>evidence</a>" if d.evidence_url else ""}</td>'
           f'<td>{pill(d.status)}</td><td class="muted">{ist(d.created_at)}</td><td>'
           + (f'<form method="post" action="/admin/disputes/{esc(d.id)}"><input name="note" placeholder="Decision note" required maxlength="500">'
              f'<div class="actions" style="margin-top:6px"><button class="btn sm" name="decision" value="uphold">Uphold</button>'
              f'<button class="btn ghost sm" name="decision" value="dismiss">Dismiss</button></div></form>' if d.status == "open" else esc(d.decision_note or ""))
           + '</td></tr>' for d in rows]
    body = (f'<h1>Disputes</h1><div class="sub">Users can dispute a result during its dispute window. Upholding a dispute '
            f'records the decision; a Settlement Officer then proposes the corrected result and a different approver '
            f'approves it. The ledger reverses the earlier entries with new ones; nothing is edited or deleted.</div>'
            f'<div class="card">{table(["Dispute", "Status", "Raised", "Decision"], trs, "No disputes.")}</div>')
    return layout(ctx, "disputes", "Disputes", body, flash)


# ------------------------------------------------------------------ news / topics / quiz

def page_news(ctx, items: list, errors: dict, flash: str = "") -> str:
    trs = []
    for it in items:
        status = f'<a class="pill info" href="/admin/questions/{esc(it.question_id)}">linked</a>' if it.question_id else ""
        hidden = '<span class="pill bad">hidden</span>' if it.hidden else ""
        trs.append(f'<tr><td>{esc(it.title)} {status} {hidden}<div class="muted" style="font-size:.72rem">'
                   f'{esc(it.source)} · {ist(it.published_at or it.fetched_at)} · '
                   f'<a href="{esc(it.link)}" target="_blank" rel="noopener noreferrer">open</a></div></td>'
                   f'<td>{esc(CATEGORIES.get(it.category, it.category))}</td><td><div class="actions">'
                   f'{post_button(f"/admin/news/{it.id}/draft", "Open draft" if it.question_id else "Draft question")}'
                   f'{post_button(f"/admin/news/{it.id}/hide", "Show in ticker" if it.hidden else "Hide from ticker", "ghost", {"hidden": 0 if it.hidden else 1})}'
                   f'<form class="inline" method="post" action="/admin/news/{esc(it.id)}/link"><input name="question_id" placeholder="Question id" style="width:150px;padding:4px 8px" value="{esc(it.question_id or "")}"><button class="btn ghost sm">Link</button></form>'
                   f'</div></td></tr>')
    body = (f'<h1>News</h1><div class="sub">Headlines feed the in-app context ticker. They are never published as '
            f'questions automatically: draft one, rewrite it as a checkable question, add the resolution source, then publish. '
            f'Link a headline to an open question so the ticker opens it.</div>'
            f'<div class="banner">Staging source: Google News RSS. Before public launch the spec requires a licensed or editorial source.</div>'
            f'<div class="card"><div class="actions">{post_button("/admin/news/refresh", "Refresh headlines")}'
            f'<span class="muted">Also runs daily via the scheduled job.</span></div></div>'
            f'<div class="card"><h2>Add a headline</h2><form method="post" action="/admin/news">'
            f'<label>Headline</label><input name="title" maxlength="300" required>{err(errors, "title")}'
            f'<div class="row3"><div><label>Publisher</label><input name="source" maxlength="200" required>{err(errors, "source")}</div>'
            f'<div><label>Article link (https)</label><input name="link" required>{err(errors, "link")}</div>'
            f'<div><label>Category</label><select name="category">{options(CATEGORIES, None)}</select></div></div>'
            f'<div style="margin-top:12px"><button class="btn">Add to ticker</button></div></form></div>'
            f'<div class="card">{table(["Headline", "Category", ""], trs, "No headlines yet. Refresh to fetch the latest.")}</div>')
    return layout(ctx, "news", "News", body, flash)


def page_topics(ctx, topics: list, counts: dict, flash: str = "") -> str:
    trs = [f'<tr><td><strong>{esc(t.title)}</strong></td><td>{esc(CATEGORIES.get(t.category, t.category))}</td>'
           f'<td>{counts.get(t.id, 0)}</td><td>{post_button(f"/admin/topics/{t.id}/delete", "Delete", "danger", None, "Delete topic? Its questions stay, untagged.")}</td></tr>'
           for t in topics]
    body = (f'<h1>Topics</h1><div class="sub">{len(topics)} topics</div>'
            f'<div class="card"><h2>New topic</h2><form method="post" action="/admin/topics">'
            f'<label for="t_title">Title</label><input id="t_title" name="title" required maxlength="200">'
            f'<div class="row"><div><label for="t_cat">Category</label><select id="t_cat" name="category">{options(CATEGORIES, None)}</select></div>'
            f'<div><label for="t_short">Short label</label><input id="t_short" name="short_label" maxlength="120"></div></div>'
            f'<label for="t_blurb">Blurb</label><textarea id="t_blurb" name="blurb"></textarea>'
            f'<div style="margin-top:12px"><button class="btn">Create topic</button></div></form></div>'
            f'<div class="card">{table(["Title", "Category", "Questions", ""], trs, "No topics.")}</div>')
    return layout(ctx, "topics", "Topics", body, flash)


def quiz_form(action: str, v: dict, errors: dict) -> str:
    opts = v.get("options") or []
    rows = ""
    for i, key in enumerate(("a", "b", "c", "d")):
        label = opts[i]["label"] if i < len(opts) else ""
        rows += (f'<div class="actions" style="margin-top:6px"><input type="radio" name="correct_key" value="{key}" style="width:auto"'
                 f'{" checked" if v.get("correct_key") == key else ""}><input name="option_{key}" maxlength="120" '
                 f'placeholder="Option {key.upper()}{" (optional)" if i > 1 else ""}" value="{esc(label)}" style="flex:1"></div>')
    return (f'<form method="post" action="{esc(action)}"><div class="row"><div><label>Day (IST)</label>'
            f'<input type="date" name="day" value="{esc(v.get("day", ""))}" required>{err(errors, "day")}</div>'
            f'<div><label class="check"><input type="checkbox" name="active" value="1"{" checked" if v.get("active", True) else ""}> Active</label></div></div>'
            f'<label>Question</label><textarea name="question" maxlength="300" required>{esc(v.get("question", ""))}</textarea>{err(errors, "question")}'
            f'<label>Options (select the correct one)</label>{rows}{err(errors, "options")}{err(errors, "correct_key")}'
            f'<label>Explanation shown after answering (optional)</label><textarea name="explanation" maxlength="500">{esc(v.get("explanation", ""))}</textarea>'
            f'<div style="margin-top:12px"><button class="btn">Save quiz</button></div></form>')


def page_quiz(ctx, rows: list, values: dict, errors: dict, editing: str | None, flash: str = "") -> str:
    trs = [f'<tr><td>{esc(r["quiz"].day.isoformat())}</td><td>{esc(r["quiz"].question)}</td>'
           f'<td>{"active" if r["quiz"].active else "off"}</td><td>{r["answers"]:,}</td>'
           f'<td><a class="btn ghost sm" href="/admin/quiz?edit={esc(r["quiz"].id)}">Edit</a></td></tr>' for r in rows]
    action = f"/admin/quiz/{editing}" if editing else "/admin/quiz"
    body = (f'<h1>Daily quiz</h1><div class="sub">One short quiz per Indian day. A correct answer earns a fixed reward, '
            f'within the daily reward cap. A quiz can&rsquo;t be changed once people have answered it.</div>'
            f'<div class="card"><h2>{"Edit quiz" if editing else "New quiz"}</h2>{quiz_form(action, values, errors)}</div>'
            f'<div class="card">{table(["Day", "Question", "Status", "Answers", ""], trs, "No quizzes yet.")}</div>')
    return layout(ctx, "quiz", "Daily quiz", body, flash)


# ------------------------------------------------------------------ moderation / users

def _reason_select(codes: dict) -> str:
    return f'<select name="reason_code" required><option value="">Reason…</option>{options(codes, None)}</select>'


def page_moderation(ctx, queue: list, recent: list, codes: dict, report_reasons: dict, names: dict,
                    flash: str = "") -> str:
    cards = ""
    for item in queue:
        c, hist = item["comment"], item["history"] or {}
        reports = "".join(f'<li>{esc(report_reasons.get(r.reason, r.reason))} — '
                          f'{esc(item["reporters"].get(r.reporter_id, {}).get("display_name", "a user"))}'
                          f'{": " + esc(r.note) if r.note else ""} <span class="muted">{ist(r.created_at)}</span></li>'
                          for r in item["reports"])
        actions_hist = "".join(f'<li>{esc(a.action)} · {esc(codes.get(a.reason_code, a.reason_code))} <span class="muted">{ist(a.created_at)}</span></li>'
                               for a in hist.get("actions", []))
        due = (f'<span class="pill bad">overdue · {item["waited_hours"]}h</span>' if item["overdue"]
               else f'<span class="pill warn">waiting {item["waited_hours"]}h</span>')
        cards += (f'<div class="card"><div class="actions" style="justify-content:space-between"><b>On: {esc(item["question_title"])}</b>{due} {pill(c.status)}</div>'
                  f'<p style="font-size:1rem;margin:10px 0">“{esc(c.body)}”</p>'
                  f'<div class="row"><div><h3 style="font-size:.85rem">Reports ({len(item["reports"])})</h3><ul>{reports}</ul></div>'
                  f'<div><h3 style="font-size:.85rem">Author: {esc(item["author"].get("display_name", c.author_name))}</h3>'
                  f'<div class="muted">{hist.get("comments", 0)} comments · {hist.get("removed", 0)} removed · reported {hist.get("times_reported", 0)} times</div>'
                  f'<ul>{actions_hist or "<li class=muted>No earlier moderation actions.</li>"}</ul>'
                  f'{"<a href=/admin/users/" + esc(c.user_id) + ">Open user</a>" if c.user_id else ""}</div></div>'
                  f'<form method="post" action="/admin/moderation/{c.id}"><div class="row3">{_reason_select(codes)}'
                  f'<input name="note" placeholder="Note (optional)" maxlength="500"><div class="actions">'
                  f'<button class="btn danger sm" name="action" value="remove">Remove</button>'
                  f'<button class="btn ghost sm" name="action" value="dismiss">Keep (dismiss reports)</button>'
                  f'{"<button class=" + chr(34) + "btn ghost sm" + chr(34) + " name=action value=restore>Restore</button>" if c.status in ("held", "removed") else ""}'
                  f'</div></div></form></div>')
    log_rows = [f'<tr><td>{esc(a.action)}</td><td>{esc(codes.get(a.reason_code, a.reason_code))}</td>'
                f'<td>{esc(names.get(a.admin_id, a.admin_id))}</td><td>{"comment #" + str(a.comment_id) if a.comment_id else ""} '
                f'{"<a href=/admin/users/" + esc(a.user_id) + ">user</a>" if a.user_id else ""}</td>'
                f'<td class="muted">{"" if a.handling_hours is None else str(a.handling_hours) + "h"}</td><td class="muted">{ist(a.created_at)}</td></tr>'
                for a in recent]
    body = (f'<h1>Moderation</h1><div class="sub">Reported comments, oldest first. Three reports hold a comment out of view '
            f'until reviewed. Target: act within 24 hours. Every action needs a reason code and is logged.</div>'
            f'{cards or "<div class=card><p class=muted>The queue is empty.</p></div>"}'
            f'<div class="card"><h2>Moderation log</h2>{table(["Action", "Reason", "By", "Target", "Handling time", "When"], log_rows)}</div>')
    return layout(ctx, "moderation", "Moderation", body, flash)


def page_users(ctx, users: list, k: dict, search: str, flash: str = "") -> str:
    trs = []
    for u in users:
        r = u["restriction"]
        tag = f'<span class="pill bad">{esc(r["code"].lower().replace("_", " "))}</span>' if r else ""
        trs.append(f'<tr><td><a href="/admin/users/{esc(u["id"])}"><strong>{esc(u["display_name"])}</strong></a> {tag}'
                   f'<div class="muted" style="font-size:.72rem">{esc(u["id"])} · {esc(u["kind"])}</div></td>'
                   f'<td class="muted">{esc(u["phone"])}</td><td>{u["calls"]:,}</td><td>{u["warnings"]}</td>'
                   f'<td class="muted">{ist(u["created_at"])}</td><td class="muted">{ist(u["last_seen_at"])}</td></tr>')
    body = (f'<h1>Users</h1><div class="sub">{k.get("users", 0)} users · {k.get("blocked", 0)} blocked · phone numbers are masked. '
            f'Detailed activity is visible only for a user&rsquo;s own support ticket, with their consent.</div>'
            f'<div class="card"><form method="get" action="/admin/users" class="actions"><input name="q" value="{esc(search)}" placeholder="Name or user id" style="max-width:300px">'
            f'<button class="btn ghost sm">Search</button></form></div>'
            f'<div class="card">{table(["User", "Phone", "Calls", "Warnings", "Joined", "Last seen"], trs, "No users found.")}</div>')
    return layout(ctx, "users", "Users", body, flash)


def page_user(ctx, u, restriction, history: dict, codes: dict, flash: str = "") -> str:
    can = ctx.can("users.sanction")
    status = f'{pill("removed")} {esc(restriction["message"])} {("until " + esc(restriction["until"])) if restriction["until"] else ""}' if restriction else pill("active")
    actions = ""
    if can:
        actions = (f'<form method="post" action="/admin/users/{esc(u.id)}/sanction"><div class="row3">'
                   f'<select name="action" required><option value="warn">Warn</option><option value="suspend">Suspend</option>'
                   f'<option value="unsuspend">Lift suspension</option><option value="block">Block permanently</option>'
                   f'<option value="unblock">Unblock</option></select>'
                   f'<select name="days"><option value="1">1 day</option><option value="3">3 days</option><option value="7" selected>7 days</option><option value="30">30 days</option></select>'
                   f'{_reason_select(codes)}</div><label>Note</label><input name="note" maxlength="500">'
                   f'<div style="margin-top:10px"><button class="btn">Apply</button></div></form>')
    acts = "".join(f'<li>{esc(a.action)} · {esc(codes.get(a.reason_code, a.reason_code))} {esc(a.note or "")} <span class="muted">{ist(a.created_at)}</span></li>'
                   for a in history.get("actions", []))
    body = (f'<h1>{esc(u.display_name)}</h1><div class="sub">{esc(u.id)} · {esc(u.kind)} · joined {ist(u.created_at)}</div>'
            f'<div class="card"><h2>Status</h2><p>{status}</p><p class="muted">Warnings: {u.warnings} · Self-exclusion until: {ist(u.excluded_until)}</p>'
            f'{actions}</div>'
            f'<div class="card"><h2>Moderation history</h2><p class="muted">{history.get("comments", 0)} comments · '
            f'{history.get("removed", 0)} removed · reported {history.get("times_reported", 0)} times</p><ul>{acts or "<li class=muted>None.</li>"}</ul></div>'
            f'<a class="btn ghost" href="/admin/users">← Users</a>')
    return layout(ctx, "users", "User", body, flash)


# ------------------------------------------------------------------ grievances

def page_grievances(ctx, rows: list, status: str, categories: dict, flash: str = "") -> str:
    trs = [f'<tr><td><a href="/admin/grievances/{esc(r["g"].id)}"><b>{esc(r["g"].ref)}</b> {esc(r["g"].subject)}</a>'
           f'<div class="muted">{esc(categories.get(r["g"].category, r["g"].category))}</div></td><td>{pill(r["g"].status)}</td>'
           f'<td>{r["age_hours"]}h {"<span class=" + chr(34) + "pill bad" + chr(34) + ">not acknowledged</span>" if r["ack_overdue"] else ""}'
           f'{"<span class=" + chr(34) + "pill bad" + chr(34) + ">past 15 days</span>" if r["resolve_overdue"] else ""}</td>'
           f'<td class="muted">{ist(r["g"].created_at)}</td></tr>' for r in rows]
    tabs = "".join(f'<a class="btn {"" if status == s else "ghost"} sm" href="/admin/grievances?status={s}">{label}</a>'
                   for s, label in (("active", "Open"), ("resolved", "Resolved"), ("rejected", "Rejected"), ("", "All")))
    body = (f'<h1>Grievances</h1><div class="sub">Acknowledge within 24 hours and resolve within 15 days '
            f'(IT Rules 2021). Every update is kept as a record.</div><div class="actions" style="margin-bottom:12px">{tabs}</div>'
            f'<div class="card">{table(["Complaint", "Status", "Age", "Raised"], trs, "No complaints.")}</div>')
    return layout(ctx, "grievances", "Grievances", body, flash)


def page_grievance(ctx, g, notes: list, user, categories: dict, activity: dict | None, names: dict,
                   flash: str = "") -> str:
    note_rows = "".join(f'<li>{esc(n.note)} <span class="muted">— {esc(names.get(n.admin_id, "admin"))}, {ist(n.created_at)}'
                        f'{" · visible to user" if n.visible_to_user else " · internal"}</span></li>' for n in notes)
    form = ""
    if g.status in ("open", "in_progress"):
        form = (f'<form method="post" action="/admin/grievances/{esc(g.id)}"><div class="row"><div><label>Status</label>'
                f'<select name="status">{options({"in_progress": "In progress", "resolved": "Resolved", "rejected": "Rejected", "open": "Open"}, "in_progress")}</select></div>'
                f'<div><label class="check"><input type="checkbox" name="visible" value="1" checked> Show this update to the user</label></div></div>'
                f'<label>Update</label><textarea name="note" maxlength="2000"></textarea>'
                f'<label>Outcome for the user (required to resolve or reject)</label><textarea name="resolution" maxlength="2000"></textarea>'
                f'<div style="margin-top:12px"><button class="btn">Save</button></div></form>')
    act = ""
    if activity is not None:
        calls = "".join(f'<li>{esc(c["question_title"])}: {esc(c["outcome_label"])} · {c["points"]} pts · {esc(c["status"])}</li>' for c in activity["calls"][:50])
        ledger_rows = "".join(f'<li>{esc(t["kind"])} {t["available_change"]:+} <span class="muted">{esc(t["created_at"])}</span></li>' for t in activity["ledger"][:50])
        act = (f'<div class="card"><h2>User activity (shared with consent for this ticket)</h2>'
               f'<div class="row"><div><h3 style="font-size:.85rem">Calls</h3><ul>{calls or "<li class=muted>None</li>"}</ul></div>'
               f'<div><h3 style="font-size:.85rem">Points ledger</h3><ul>{ledger_rows or "<li class=muted>None</li>"}</ul></div></div></div>')
    elif g.status in ("open", "in_progress"):
        act = '<div class="card"><p class="muted">The user did not allow support to view their activity for this ticket.</p></div>'
    body = (f'<h1>{esc(g.ref)}: {esc(g.subject)}</h1><div class="sub">{pill(g.status)} · {esc(categories.get(g.category, g.category))} · '
            f'raised {ist(g.created_at)} by <a href="/admin/users/{esc(g.user_id)}">{esc(user.display_name if user else g.user_id)}</a>'
            f'{" · question " + esc(g.question_id) if g.question_id else ""}</div>'
            f'<div class="card"><p style="white-space:pre-wrap">{esc(g.description)}</p>'
            f'<p class="muted">Acknowledged: {ist(g.acknowledged_at)} · Resolved: {ist(g.resolved_at)}</p>'
            f'{"<p><b>Outcome:</b> " + esc(g.resolution) + "</p>" if g.resolution else ""}</div>'
            f'<div class="card"><h2>Updates</h2><ul>{note_rows or "<li class=muted>None yet.</li>"}</ul>{form}</div>{act}'
            f'<a class="btn ghost" href="/admin/grievances">← Grievances</a>')
    return layout(ctx, "grievances", "Grievance", body, flash)


# ------------------------------------------------------------------ policy / economy / badges

def page_policy(ctx, values: dict, features: dict, periods: list, now, errors: dict, flash: str = "") -> str:
    states_sorted = dict(sorted(STATES.items(), key=lambda kv: kv[1]))
    feat_rows = []
    for key, label in features.items():
        f = values["features"][key]
        opts = "".join(f'<option value="{esc(c)}"{" selected" if c in f["off_states"] else ""}>{esc(n)}</option>' for c, n in states_sorted.items())
        feat_rows.append(f'<tr><td><b>{esc(label)}</b></td><td><form method="post" action="/admin/policy/features/{esc(key)}">'
                         f'<label class="check" style="margin:0"><input type="checkbox" name="on" value="1"{" checked" if f["on"] else ""}> On nationally</label>'
                         f'<label>Off in these states (Ctrl/Cmd-click for several)</label><select name="off_states" multiple>{opts}</select>'
                         f'<div style="margin-top:6px"><button class="btn sm">Save</button></div></form></td></tr>')
    p_rows = []
    for p in periods:
        active = aware(p.starts_at) <= now < aware(p.ends_at)
        states = "All states" if p.states == "*" else ", ".join(STATES.get(x, x) for x in p.states.split(","))
        p_rows.append(f'<tr><td><b>{esc(p.label)}</b>{" <span class=" + chr(34) + "pill warn" + chr(34) + ">active</span>" if active else ""}</td>'
                      f'<td>{esc(states)}</td><td class="muted">{ist(p.starts_at)} → {ist(p.ends_at)}</td>'
                      f'<td>{"yes" if p.hide_sentiment else "no"}</td><td>'
                      f'{post_button(f"/admin/policy/quiet/{p.id}/end", "End now", "ghost", None, "End this quiet period now?") if aware(p.ends_at) > now else ""}</td></tr>')
    st_opts = '<option value="*">All states</option>' + "".join(f'<option value="{esc(c)}">{esc(n)}</option>' for c, n in states_sorted.items())
    body = (f'<h1>Regions &amp; flags</h1><div class="sub">Switch Phase 1 features off nationally or for chosen states, and set '
            f'election quiet periods. Users choose their state in their profile; Phase 2 features stay off and can\'t be switched on here.</div>'
            f'<div class="card"><h2>Election quiet periods</h2><p class="muted">While a period is active, election-sensitive questions for '
            f'those states hide their live chance{", and drop out of the sentiment dashboard when chosen" }. Ask counsel how RP Act s.126/126A applies.</p>'
            f'{table(["Period", "States", "When", "Hides sentiment", ""], p_rows, "No quiet periods.")}'
            f'<h3 style="font-size:.92rem;margin-top:16px">Add a quiet period</h3><form method="post" action="/admin/policy/quiet">'
            f'<label>Name</label><input name="label" maxlength="120" placeholder="Bihar Assembly election, phase 1" required>{err(errors, "label")}'
            f'<div class="row"><div><label>Starts (IST)</label><input type="datetime-local" name="starts_at" required></div>'
            f'<div><label>Ends (IST)</label><input type="datetime-local" name="ends_at" required></div></div>{err(errors, "when")}'
            f'<label>States</label><select name="states" multiple required>{st_opts}</select>'
            f'<label class="check"><input type="checkbox" name="hide_sentiment" value="1" checked> Also hide these questions from the sentiment dashboard</label>'
            f'<div style="margin-top:12px"><button class="btn">Add period</button></div></form></div>'
            f'<div class="card"><h2>Feature switches</h2>{table(["Feature", "Setting"], feat_rows)}</div>')
    return layout(ctx, "policy", "Regions & flags", body, flash)


def page_economy(ctx, e: dict, cap: int, flash: str = "") -> str:
    tiles = [("Points issued", e["issued_total"], ""), ("With users (available)", e["available_total"], ""),
             ("Committed to open calls", e["committed_total"], ""), ("In settling pools", e["in_pools"], ""),
             ("Rounded off at settlement", e["rounding_total"], "")]
    today = "".join(f'<tr><td>{esc(k.replace("_", " "))}</td><td>{v:,}</td></tr>' for k, v in sorted(e["rewards_today"].items()))
    check = ('<span class="pill ok">balanced</span>' if e["balanced"] else '<span class="pill bad">does not balance: investigate</span>')
    body = (f'<h1>Points economy</h1><div class="sub">Closed loop: points are issued as rewards, committed to calls and released at '
            f'settlement. There is no purchase, withdrawal or transfer path.</div>{kpis(tiles)}'
            f'<div class="card"><h2>Ledger check</h2><p>Issued = available + committed + pools + rounding: {check}</p></div>'
            f'<div class="card"><h2>Issued today (IST)</h2>{table(["Kind", "Points"], [today] if today else [], "Nothing issued today.")}</div>'
            f'<div class="card"><h2>Daily reward cap</h2><p class="muted">The most a user can receive in a day from everyday rewards '
            f'(check-in and quiz). Settlement releases and the one-time welcome reward are not capped.</p>'
            f'<form method="post" action="/admin/economy/cap" class="actions"><input type="number" name="cap" min="0" max="10000" value="{cap}" style="max-width:160px">'
            f'<button class="btn sm">Save cap</button></form></div>')
    return layout(ctx, "economy", "Points economy", body, flash)


def page_badges(ctx, tiers: list, badges: list, rules: dict, errors: dict, editing, flash: str = "") -> str:
    tier_inputs = "".join(f'<div><label>{esc(t["emoji"])} {esc(t["name"])}</label><input type="number" name="min_{i}" value="{t["min"]}" min="0"'
                          f'{" readonly" if i == 0 else ""}></div>' for i, t in enumerate(tiers))
    b_rows = [f'<tr><td>{esc(b.emoji)} <b>{esc(b.name)}</b><div class="muted">{esc(b.description)}</div></td>'
              f'<td>{esc(rules.get(b.rule, b.rule))} ≥ {b.threshold:,}</td><td>{"active" if b.active else "off"}</td>'
              f'<td><a class="btn ghost sm" href="/admin/badges?edit={esc(b.id)}">Edit</a></td></tr>' for b in badges]
    v = editing or {}
    form = (f'<form method="post" action="/admin/badges{"/" + esc(v.get("id")) if v.get("id") else ""}"><div class="row3">'
            f'<div><label>Name</label><input name="name" maxlength="60" value="{esc(v.get("name", ""))}" required>{err(errors, "name")}</div>'
            f'<div><label>Emoji</label><input name="emoji" maxlength="8" value="{esc(v.get("emoji", ""))}" required>{err(errors, "emoji")}</div>'
            f'<div><label>Order</label><input type="number" name="sort" value="{esc(v.get("sort", 0))}"></div></div>'
            f'<label>Description</label><input name="description" maxlength="200" value="{esc(v.get("description", ""))}">'
            f'<div class="row"><div><label>Measures</label><select name="rule">{options(rules, v.get("rule"))}</select>{err(errors, "rule")}</div>'
            f'<div><label>Threshold</label><input type="number" name="threshold" min="1" value="{esc(v.get("threshold", 1))}">{err(errors, "threshold")}</div></div>'
            f'<label class="check"><input type="checkbox" name="active" value="1"{" checked" if v.get("active", True) else ""}> Active</label>'
            f'<div style="margin-top:12px"><button class="btn">{"Save badge" if v.get("id") else "Add badge"}</button></div></form>')
    body = (f'<h1>Ranks &amp; badges</h1><div class="sub">Status rewards only in Phase 1: ranks, badges and profile flair. '
            f'Rank follows lifetime points earned, so committing points never lowers it.</div>'
            f'<div class="card"><h2>Rank thresholds (lifetime points earned)</h2><form method="post" action="/admin/badges/tiers">'
            f'<div class="row3">{tier_inputs}</div>{err(errors, "tiers")}<div style="margin-top:12px"><button class="btn">Save thresholds</button></div></form></div>'
            f'<div class="card"><h2>{"Edit badge" if v.get("id") else "New badge"}</h2>{form}</div>'
            f'<div class="card"><h2>Badge catalogue</h2>{table(["Badge", "Earned when", "Status", ""], b_rows, "No badges.")}</div>')
    return layout(ctx, "badges", "Ranks & badges", body, flash)


# ------------------------------------------------------------------ ops / sentiment

def bars(series: list[tuple[str, int]]) -> str:
    top = max([v for _, v in series] + [1])
    cols = "".join(f'<div style="height:{max(2, round(v * 86 / top))}px" title="{esc(d)}: {v}"><span>{v}</span></div>' for d, v in series)
    labels = "".join(f'<span>{esc(d[5:])}</span>' for d, _ in series)
    return f'<div class="bars">{cols}</div><div class="bar-labels">{labels}</div>'


def _pct(x) -> str:
    return "—" if x is None else f"{round(x * 100)}%"


def page_ops(ctx, act: dict, funnel: dict, retention: list, volume: list, errors: list, health: dict,
             handling: dict, flash: str = "") -> str:
    ret_rows = [f'<tr><td>{esc(r["week"])}</td><td>{r["size"]:,}</td><td>{_pct(r["d1"])}</td><td>{_pct(r["d7"])}</td><td>{_pct(r["d30"])}</td></tr>' for r in retention]
    f = funnel
    steps = [("New accounts", f["new_accounts"]), ("Made a call", f["made_a_call"]), ("Checked in", f["checked_in"]),
             ("Came back another day", f["came_back"])]
    funnel_rows = [f'<tr><td>{esc(lbl)}</td><td>{n:,}</td><td>{_pct(n / f["new_accounts"]) if f["new_accounts"] else "—"}</td></tr>' for lbl, n in steps]
    inconsistent = ('<span class="pill ok">consistent</span>' if not health["inconsistent"]
                    else f'<span class="pill bad">{len(health["inconsistent"])} inconsistent</span>')
    body = (f'<h1>Operations</h1><div class="sub">Pseudonymous counts only. No individual journey is shown here.</div>'
            f'{kpis([("Active today", act["dau"], ""), ("Active 7 days", act["wau"], ""), ("Active 30 days", act["mau"], ""), ("New today", act["new_today"], "")])}'
            f'<div class="row"><div class="card"><h2>Calls per day</h2>{bars(volume)}</div>'
            f'<div class="card"><h2>Server errors per day</h2>{bars(errors)}<p class="hint">5xx responses. Details are in the logs, by correlation ID.</p></div></div>'
            f'<div class="row"><div class="card"><h2>Funnel (accounts from the last {f["days"]} days)</h2>{table(["Step", "Users", "Share"], funnel_rows)}</div>'
            f'<div class="card"><h2>Retention by sign-up week</h2>{table(["Week", "Users", "Day 1+", "Day 7+", "Day 30+"], ret_rows, "No cohorts yet.")}'
            f'<p class="hint">Share of each cohort seen again at least 1, 7 or 30 days after joining.</p></div></div>'
            f'<div class="row"><div class="card"><h2>Sentiment index health</h2><p>Computed in {health["computed_in_ms"]} ms · '
            f'{health["questions_with_enough_data"]} of {health["questions_considered"]} questions have 50+ participants · '
            f'{health["categories_with_enough_data"]} categories shown · {inconsistent}</p></div>'
            f'<div class="card"><h2>Report handling (7 days)</h2><p>{handling["handled"]} handled · {handling["within_target"]} within 24 h · '
            f'median {handling["median_hours"] if handling["median_hours"] is not None else "—"} h</p></div></div>')
    return layout(ctx, "ops", "Operations", body, flash)


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


def page_sentiment(ctx, m: dict, public: dict) -> str:
    rows = [f'<tr><td><strong>{esc(CATEGORIES.get(c["category"], c["category"]))}</strong></td><td>{c["count"]}</td>'
            f'<td style="color:{_mood_color(c["mood"])}">{_signed(c["mood"])}</td><td>{round(c["consensus"] * 100)}%</td>'
            f'<td>{c["total_votes"]:,}</td></tr>' for c in m.get("categories", [])]
    pub = [f'<tr><td>{esc(c["label"])}</td><td>{c["questions"]}</td><td>{"—" if c["participants"] is None else c["participants"]}</td>'
           f'<td>{_pct(c["average_lean"])}</td><td>{"shown" if c["enough_data"] else "withheld (under 50)"}</td></tr>' for c in public["categories"]]
    body = (f'<h1>Sentiment</h1><div class="sub">Admin-only signal from question wording and call split · '
            f'{m.get("total_polls", 0)} questions · {m.get("total_votes", 0):,} calls.</div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-bottom:18px">'
            f'<div class="card" style="text-align:center"><h2>Overall mood</h2>{speedometer(m.get("overall_mood", 0) or 0, "mood", "g1")}</div>'
            f'<div class="card" style="text-align:center"><h2>Crowd lean</h2>{speedometer(m.get("overall_optimism", 0) or 0, "net yes-lean", "g2")}</div></div>'
            f'<div class="card"><h2>By category (admin signal)</h2>{table(["Category", "Questions", "Mood", "Consensus", "Calls"], rows, "No published questions yet.")}</div>'
            f'<div class="card"><h2>Public dashboard preview</h2><p class="muted">What users see: aggregates only, nothing for a group under 50 participants'
            f'{"; election quiet period active" if public["election_restricted"] else ""}.</p>'
            f'{table(["Category", "Questions", "Participants", "Average lean", "Status"], pub, "No data.")}</div>')
    return layout(ctx, "sentiment", "Sentiment", body)


# ------------------------------------------------------------------ admins / audit

def page_admins(ctx, admins: list, roles: dict, errors: dict, values: dict, flash: str = "") -> str:
    from app.modules.governance.auth import two_factor_required
    two_fa = two_factor_required()
    trs = []
    for a in admins:
        role_boxes = "".join(f'<label class="check" style="margin:2px 0"><input type="checkbox" name="roles" value="{esc(k)}"'
                             f'{" checked" if k in (a.roles or []) else ""}> {esc(v)}</label>' for k, v in roles.items())
        trs.append(f'<tr><td><b>{esc(a.name)}</b><div class="muted">{esc(a.email)}</div>'
                   f'<div class="muted" style="font-size:.72rem">{("2FA " + ("on" if a.totp_enabled else "not set up") + " · ") if two_fa else ""}last sign-in {ist(a.last_login_at)}'
                   f'{"" if a.active else " · <span class=" + chr(34) + "pill bad" + chr(34) + ">disabled</span>"}</div></td>'
                   f'<td><form method="post" action="/admin/admins/{esc(a.id)}">{role_boxes}'
                   f'<label class="check"><input type="checkbox" name="active" value="1"{" checked" if a.active else ""}> Active</label>'
                   f'<button class="btn sm" style="margin-top:6px">Save</button></form></td>'
                   f'<td><div class="actions">{post_button(f"/admin/admins/{a.id}/reset-2fa", "Reset 2FA", "ghost", None, "Reset two-factor sign-in? They must enrol again.") if two_fa else ""}'
                   f'</div></td></tr>')
    role_boxes = "".join(f'<label class="check" style="margin:2px 0"><input type="checkbox" name="roles" value="{esc(k)}"'
                         f'{" checked" if k in values.get("roles", []) else ""}> {esc(v)}</label>' for k, v in roles.items())
    signin = "a password and a two-factor code" if two_fa else "a username and password (two-factor sign-in is off: turn it on with ADMIN_REQUIRE_2FA before launch)"
    body = (f'<h1>Admin accounts</h1><div class="sub">Every admin signs in with {signin}. '
            f'Nobody can hold both settlement roles; at least one active Super Admin is always kept.</div>'
            f'<div class="card">{table(["Admin", "Roles", ""], trs)}</div>'
            f'<div class="card"><h2>Add an admin</h2><form method="post" action="/admin/admins"><div class="row">'
            f'<div><label>Name</label><input name="name" maxlength="80" value="{esc(values.get("name", ""))}" required></div>'
            f'<div><label>Work email</label><input name="email" maxlength="160" value="{esc(values.get("email", ""))}" required>{err(errors, "email")}</div></div>'
            f'<label>Temporary password</label><input type="password" name="password" autocomplete="new-password" required>'
            f'<div class="hint">Share it privately. They must change it on first sign-in{" and set up two-factor sign-in" if two_fa else ""}.</div>{err(errors, "password")}'
            f'<label>Roles</label>{role_boxes}{err(errors, "roles")}<div style="margin-top:12px"><button class="btn">Add admin</button></div></form></div>')
    return layout(ctx, "admins", "Admin accounts", body, flash)


def page_audit(ctx, rows: list, action: str, can_export: bool) -> str:
    import json
    trs = [f'<tr><td class="muted">{ist(r.created_at)}</td><td>{esc(r.admin_email or "system")}<div class="muted" style="font-size:.7rem">{esc(", ".join(r.roles or []))}</div></td>'
           f'<td><b>{esc(r.action)}</b><div class="muted" style="font-size:.72rem">{esc(r.target_type or "")} {esc(r.target_id or "")}</div></td>'
           f'<td style="max-width:380px;font-size:.72rem"><div class="muted">before: {esc(json.dumps(r.before, ensure_ascii=False)[:300]) if r.before else "—"}</div>'
           f'<div>after: {esc(json.dumps(r.after, ensure_ascii=False)[:300]) if r.after else "—"}</div></td>'
           f'<td class="muted" style="font-size:.72rem">{esc(r.ip or "")}</td></tr>' for r in rows]
    export = f'<a class="btn ghost sm" href="/admin/audit.csv?action={esc(action)}">Download CSV</a>' if can_export else ""
    body = (f'<h1>Audit log</h1><div class="sub">Append-only: who, which role, from which IP, when, and the before and after state. '
            f'Records can\'t be edited or deleted.</div>'
            f'<div class="card"><form method="get" action="/admin/audit" class="actions"><input name="action" value="{esc(action)}" placeholder="Filter by action, e.g. settlement" style="max-width:300px">'
            f'<button class="btn ghost sm">Filter</button>{export}</form></div>'
            f'<div class="card">{table(["When", "Admin", "Action", "Change", "IP"], trs, "No records.")}</div>')
    return layout(ctx, "audit", "Audit log", body)


def days_ago(n: int):
    from app.clock import now_utc
    return now_utc() - timedelta(days=n)
