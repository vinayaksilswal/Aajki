// Bharat Foreseez consumer app.
import { api, allOpenQuestions, ensureSession, newId } from './api.js';
import { t, getLang, setLang } from './i18n.js';

const BRAND = import.meta.env.BASE_URL + 'brand/';

(function(){
  "use strict";

  /* ============ utils ============ */
  function clamp(v,a,b){ return Math.max(a,Math.min(b,v)); }
  function fmtNum(n){ return Math.round(n).toLocaleString('en-IN'); }
  const WEEKDAYS=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function fmtDate(d){ return d.getDate()+' '+MONTHS[d.getMonth()]; }
  function formatDateLong(d){ return WEEKDAYS[d.getDay()]+', '+d.getDate()+' '+MONTHS[d.getMonth()]; }
  function formatTime(d){ let h=d.getHours(); const m=String(d.getMinutes()).padStart(2,'0'); const ap=h>=12?'pm':'am'; h=h%12; if(h===0)h=12; return h+':'+m+' '+ap; }
  function isoIST(d){ const p=n=>String(n).padStart(2,'0'); return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'T'+p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds())+'+05:30'; }
  function liveNow(){ return new Date(); }
  function timeNow(){ return formatTime(liveNow()); }
  function esc(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  // Simple 18+ check from a self-declared date of birth — the only identity
  // gate this prototype needs, since Foreseez Points are never redeemable
  // for cash and there's nothing here that would trigger financial KYC.
  function ageFromDOB(dobStr){
    if(!dobStr) return null;
    const d = new Date(dobStr+'T00:00:00');
    if(isNaN(d.getTime())) return null;
    const now = liveNow();
    let age = now.getFullYear() - d.getFullYear();
    const m = now.getMonth() - d.getMonth();
    if(m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
    return age;
  }

  /* ============ static content ============ */
  const CATS = [
    {key:'elections', label:'Elections', color:'var(--cat-elections)', emoji:'🗳️'},
    {key:'markets', label:'Markets', color:'var(--cat-markets)', emoji:'📈'},
    {key:'sports', label:'Sports', color:'var(--cat-sports)', emoji:'🏏'},
    {key:'policy', label:'Policy', color:'var(--cat-policy)', emoji:'📜'},
    {key:'world', label:'World', color:'var(--cat-world)', emoji:'🌍'},
    {key:'community', label:'Community', color:'var(--cat-community)', emoji:'💬'}
  ];
  const CAT_MAP = Object.fromEntries(CATS.map(c=>[c.key,c]));
  const AVATARS = { lotus:'🪷', tiger:'🐯', peacock:'🦚', elephant:'🐘', mango:'🥭', kite:'🪁', diya:'🪔', cricket:'🏏' };
  function avatarOf(key){ return AVATARS[key] || '🙂'; }

  /* ============ live data (Bharat Foreseez API) ============
     Everything shown comes from the backend: questions, headlines, points, calls, ranks,
     comments and rewards. There is no offline or sample content: while loading, or if the
     server can't be reached, the app says so. */
  const FEED_REFRESH_MS = 60000;
  const TICKER_REFRESH_MS = 300000;
  // Open questions poll for chance updates while a question is open on screen (spec s.4:
  // live updates under 2 s with polling fallback; SSE arrives with container hosting).
  const SHEET_REFRESH_MS = 15000;
  // Bumped with each app release; the server's min/latest build drive update prompts.
  const APP_BUILD = Number(import.meta.env.VITE_APP_BUILD || 1);
  const DEFAULT_RULES = { daily_call_cap:10, call_min_points:10, call_max_points:500, checkin_reward:50,
    quiz_reward:25, session_reminder_minutes:30, comment_max_length:140, min_group:50, self_exclusion_days:[1,7,30,90] };
  const PHASE1_FLAGS = { prizes:false, plus:false, sponsored_polls:false, user_created_polls:false, spin_the_wheel:false,
    forecasting:true, debate:true, checkin:true, quiz:true, leaderboards:true, sentiment_dashboard:true, invites:true };

  function toDef(q){
    const out = {}; (q.outcomes||[]).forEach(o=>{ out[o.key] = o; });
    return {
      id:q.id, category:q.category, title:q.title, desc:q.description||'',
      yes:(out.yes && out.yes.label) || 'Yes', no:(out.no && out.no.label) || 'No',
      closes: q.closes_at ? new Date(q.closes_at) : null,
      participants:q.participants||0, chanceHidden:!!q.chance_hidden,
      chance:{ yes: out.yes ? out.yes.chance : null, no: out.no ? out.no.chance : null },
      resolution:q.resolution||{}, context:q.context||null, status:q.status, result:q.result||null
    };
  }
  function applyQuestions(list){
    const defs = {};
    list.forEach(q=>{ if(CAT_MAP[q.category]) defs[q.id] = toDef(q); });
    state.questionDefs = defs;
    state.contests = Object.values(defs).map(d=>({ id:d.id, status:'open' }));
  }
  let feedInFlight = null, feedLoadedAt = 0;
  const FEED_MIN_GAP_MS = 15000;
  function loadFeed(){
    // One request at a time: boot, the refresh timer and tab-visibility events can overlap.
    if(!feedInFlight) feedInFlight = fetchFeed().finally(()=>{ feedInFlight = null; });
    return feedInFlight;
  }
  async function fetchFeed(){
    const hadData = state.contests.length > 0;
    state.feedStatus = hadData ? 'refreshing' : 'loading';
    if(!hadData) render();
    try {
      applyQuestions(await allOpenQuestions());
      state.feedStatus = 'ready'; state.feedError = null; feedLoadedAt = Date.now();
    } catch(e){
      // Keep showing the last good data on a failed background refresh.
      state.feedStatus = hadData ? 'ready' : 'error';
      state.feedError = e;
    }
    render();
  }
  async function loadTicker(){
    try { const t = await api.ticker(); state.newsFeed = t.items || []; state.newsAttribution = t.attribution || ''; }
    catch(e){ /* the ticker is optional context; keep whatever was shown */ }
    render();
  }
  async function loadAppConfig(){
    try {
      const cfg = await api.appConfig(state.me && state.me.region);
      state.cfg = cfg;
      state.flags = Object.assign({}, PHASE1_FLAGS, cfg.flags || {});
      state.grievance = cfg.grievance_officer || null;
      render();
    } catch(e){ /* stay on the Phase 1 defaults */ }
  }
  function rules(){ return (state.cfg && state.cfg.rules) || DEFAULT_RULES; }

  // The signed-in account: points, rank, stats, badges, safeguards and regional switches.
  async function loadMe(){
    try {
      const prevRegion = state.me && state.me.region;
      state.me = await api.me();
      state.meError = null;
      if(state.me.flags) state.flags = Object.assign({}, PHASE1_FLAGS, state.me.flags);
      if(state.me.region !== prevRegion && state.cfg) loadAppConfig();
    } catch(e){ state.meError = e; }
    render();
  }
  async function loadMyCalls(){
    try {
      const calls = await api.myCalls();
      state.myCalls = calls;
      const map = {};
      calls.forEach(c=>{ map[c.question_id] = { option:c.outcome_key, staked:c.points, status:c.status, released:c.released }; });
      state.predictions = map;
      noticeSettledCalls(calls);
    } catch(e){ /* keep the last list */ }
    render();
  }
  async function loadLedger(more){
    if(state._ledgerLoading) return;
    state._ledgerLoading = true;
    try {
      const page = await api.ledger(more ? state.ledgerCursor : null);
      state.ledgerItems = more ? state.ledgerItems.concat(page.items) : page.items;
      state.ledgerCursor = page.next_cursor;
      state.ledgerError = null;
    } catch(e){ state.ledgerError = e; }
    state._ledgerLoading = false;
    render();
  }
  async function loadLeaderboard(period){
    try { state.lb[period] = await api.leaderboard(period); state.lbError = null; }
    catch(e){ state.lbError = e; }
    render();
  }
  async function loadQuiz(){
    try { state.quiz = (await api.quizToday()).quiz; } catch(e){ /* optional */ }
    render();
  }
  async function loadSentiment(){
    try { state.sentiment = await api.sentiment(); state.sentimentError = null; }
    catch(e){ state.sentimentError = e; }
    render();
  }
  async function loadGrievances(){
    try { state.grievances = await api.grievances(); } catch(e){ /* keep */ }
    render();
  }
  async function loadBlocks(){
    try { state.blocks = await api.blocks(); } catch(e){ /* keep */ }
    render();
  }
  async function loadThread(qid){
    const th = state.threads[qid] || (state.threads[qid] = { items:[], total:0, status:'loading' });
    try {
      const page = await api.comments(qid);
      Object.assign(th, page, { status:'ready' });
    } catch(e){ th.status = 'error'; th.error = e; }
    render();
  }
  // A question opened from "My calls" may have closed and left the open feed.
  async function ensureQuestion(qid){
    if(contestDef(qid)) return;
    try { state.extraDefs[qid] = toDef(await api.question(qid)); }
    catch(e){ state.extraDefs[qid] = null; }
    render();
  }
  async function refreshOpenQuestion(){
    const id = state.openContest;
    if(!id || document.visibilityState!=='visible') return;
    try {
      const d = toDef(await api.question(id));
      if(state.questionDefs[id]) state.questionDefs[id] = d; else state.extraDefs[id] = d;
      render();
    } catch(e){ /* keep the last figure */ }
  }

  // Rank tiers come from the server (admins can tune thresholds); these match the spec defaults.
  const RANK_TIERS = [
    {min:0,     name:'Navodit',       emoji:'🌱', color:'#8a8f98'},
    {min:1000,  name:'Drishta',       emoji:'✅', color:'#1d9bf0'},
    {min:2500,  name:'Vishleshak',    emoji:'📊', color:'#1baf7a'},
    {min:4500,  name:'Top Voice',     emoji:'🌟', color:'#c98500'},
    {min:7000,  name:'Hall of Famer', emoji:'🏆', color:'#b8860b'},
    {min:10000, name:'Mahadrishta',   emoji:'👑', color:'linear-gradient(135deg,#FF9933,#b8860b)'}
  ];
  function tiers(){ return (state.cfg && state.cfg.rank_tiers && state.cfg.rank_tiers.length) ? state.cfg.rank_tiers : RANK_TIERS; }
  function rankTierFor(pts){
    let tier = tiers()[0];
    for(const t of tiers()){ if(pts >= t.min) tier = t; }
    return tier;
  }
  function rankBadgeChip(pts, sm){
    const t = rankTierFor(pts);
    return '<span class="rank-badge'+(sm?' sm':'')+'" style="background:'+t.color+';">'+t.emoji+' '+esc(t.name)+'</span>';
  }

  /* ============ state ============ */
  function defaultState(){
    return {
      activeView:'app',
      phoneScreen:'onboarding',
      obStep:'start',
      otpCode:null, otpPhone:null, otpAttempt:'',
      fullName:'', dob:'', interests:[], _hookContestId:null, _hookChoice:null,
      phoneVerified:false, ageDeclared:false, consentGiven:false,
      selfieVerified:false, selfieSkipped:false, selfieSheetOpen:false,
      _selfiePreviewDataUrl:null, _selfieCameraError:false,
      user:{ signedIn:false, name:'', method:'' },
      contests: [], questionDefs: {}, extraDefs:{}, feedStatus:'idle', feedError:null,
      me:null, meError:null, cfg:null,
      predictions:{}, myCalls:[],
      ledgerItems:[], ledgerCursor:null, ledgerError:null, ledgerTab:'calls',
      lb:{}, lbPeriod:'weekly', lbError:null,
      quiz:undefined, sentiment:null, sentimentError:null,
      grievances:[], blocks:[], threads:{}, replyTo:null,
      catFilter:'all',
      notifications:[],
      activity:[],
      searchQuery:'',
      sortMode:'closing',
      notifPanelOpen:false,
      newsFeed: [], newsAttribution:'',
      flags: Object.assign({}, PHASE1_FLAGS), grievance:null,
      _busy:{}, _callKey:null, _editingName:false, _grievanceOpen:false
    };
  }
  let state = defaultState();

  function contestDef(id){ return (state.questionDefs||{})[id] || (state.extraDefs||{})[id] || null; }
  function callsToday(){ return state.me ? state.me.calls_today : 0; }
  function dailyCallCap(){ return rules().daily_call_cap; }
  function callsLeftToday(){ return Math.max(0, dailyCallCap() - callsToday()); }
  function balance(){ return state.me ? state.me.points.available : 0; }
  function committedPoints(){ return state.me ? state.me.points.committed : 0; }
  // Spec s.6: rank follows lifetime points earned, so committing points never lowers it.
  function lifetimeEarned(){ return state.me ? state.me.rank.lifetime_earned : 0; }
  function restriction(){ return state.me && state.me.restriction; }
  function busy(key, on){ if(on===undefined) return !!state._busy[key]; state._busy[key] = on; }
  function errText(e){ return (e && e.message) || 'Something went wrong. Please try again.'; }

  /* ============ debate ============
     Text comments (140 characters) with one level of replies. Photos, videos and voice notes
     open once automated screening is live: the spec requires every attachment to be checked
     before anyone sees it, and that can't be done safely in the app. */
  function timeAgo(isoStr){
    const s = Math.max(0, (Date.now() - new Date(isoStr).getTime())/1000);
    if(s < 60) return 'just now';
    if(s < 3600) return Math.floor(s/60)+'m';
    if(s < 86400) return Math.floor(s/3600)+'h';
    return Math.floor(s/86400)+'d';
  }
  function commentRow(c, isReply){
    const actions = c.mine
      ? '<button class="link-btn" data-del-comment="'+c.id+'">'+t('delete')+'</button>'
      : (isReply ? '' : '<button class="link-btn" data-reply="'+c.id+'">'+t('reply')+'</button>')
        + '<button class="link-btn" data-report-comment="'+c.id+'">'+t('report')+'</button>'
        + '<button class="link-btn" data-block-author="'+c.id+'">'+t('block')+'</button>';
    return '<div class="comment'+(isReply?' reply':'')+'"><div class="who"><span class="av">'+avatarOf(c.author.avatar)+'</span><b>'+esc(c.author.display_name)+'</b><span class="t">'+timeAgo(c.created_at)+'</span></div>'
      + '<p>'+esc(c.body)+'</p><div class="c-actions">'+actions+'</div>'
      + (state._reportFor===c.id ? '<div class="report-menu">Why report this? '+((state.cfg && state.cfg.report_reasons)||[]).map(r=>'<button class="btn btn-sm" data-report-reason="'+esc(r.key)+'">'+esc(r.label)+'</button>').join('')+'</div>' : '')
      + '</div>';
  }
  function renderThread(qid){
    if(!state.flags.debate) return '<div class="discuss"><h4>'+t('debate')+'</h4><p class="hint">Debate isn&rsquo;t available in your region right now.</p></div>';
    const th = state.threads[qid];
    let list;
    if(!th || th.status==='loading') list = '<p class="hint">'+t('loading')+'</p>';
    else if(th.status==='error') list = '<p class="hint">Couldn&rsquo;t load comments. <button class="link-btn" data-reload-thread="'+esc(qid)+'">'+t('retry')+'</button></p>';
    else if(!th.items.length) list = '<p class="hint">No comments yet. Start the debate.</p>';
    else list = th.items.map(c=>commentRow(c,false) + (c.replies||[]).map(r=>commentRow(r,true)).join('')).join('');
    const replying = state.replyTo ? '<div class="replying">Replying &middot; <button class="link-btn" id="btnCancelReply">cancel</button></div>' : '';
    const blocked = !!restriction();
    const form = blocked ? '<p class="hint">'+esc(restriction().message)+'</p>'
      : replying + '<div class="comment-form"><input id="commentInput" type="text" maxlength="'+rules().comment_max_length+'" placeholder="Add to the debate…" value="'+esc(state._commentDraft||'')+'">'
        + '<button class="btn btn-sm" id="btnPostComment" '+(busy('comment')?'disabled':'')+'>'+t('post')+'</button></div>'
        + '<p class="media-policy">Up to '+rules().comment_max_length+' characters, no links. Photos, videos and voice notes open once automated screening is live. Reported comments are reviewed by moderators.</p>';
    return '<div class="discuss"><h4>'+t('debate')+(th && th.total ? ' &middot; '+th.total : '')+'</h4>'+form+'<div class="comments">'+list+'</div></div>';
  }

  /* ============ notifications ============
     Built from your own calls: when a result is released or a question is voided. */
  const CALL_STATUS_KEY = 'bf-call-status';
  function noticeSettledCalls(calls){
    let seen = {};
    try { seen = JSON.parse(localStorage.getItem(CALL_STATUS_KEY) || '{}'); } catch(_) {}
    const first = Object.keys(seen).length === 0;
    calls.forEach(c=>{
      const before = seen[c.id];
      if(!first && before === 'active' && c.status !== 'active'){
        const title = c.question_title || 'a question';
        if(c.status==='correct') pushNotification('Correct call on “'+title+'”: '+fmtNum(c.released)+' points released.');
        else if(c.status==='incorrect') pushNotification('“'+title+'” has settled. Your call didn’t match the result.');
        else if(c.status==='refunded') pushNotification('“'+title+'” was voided. Your '+fmtNum(c.points)+' points were returned.');
      }
      seen[c.id] = c.status;
    });
    try { localStorage.setItem(CALL_STATUS_KEY, JSON.stringify(seen)); } catch(_) {}
  }

  function pushActivity(text){
    state.activity.unshift({ text, ts:timeNow() });
    state.activity = state.activity.slice(0,20);
  }
  function pushNotification(text){
    state.notifications.unshift({ id:'nf'+Date.now()+Math.random().toString(36).slice(2,6), text, ts:timeNow(), read:false });
    state.notifications = state.notifications.slice(0,30);
  }
  function renderNotifBadge(){
    const badge = document.getElementById('notifBadge');
    if(!badge) return;
    const unread = state.notifications.filter(n=>!n.read).length;
    badge.hidden = unread===0;
    badge.textContent = unread>9 ? '9+' : String(unread);
  }

  /* ============ toast ============ */
  function toast(msg){
    const host = document.getElementById('toastHost');
    const t = document.createElement('div'); t.className='toast'; t.textContent=msg;
    host.appendChild(t);
    setTimeout(()=>t.remove(), 3400);
  }

  /* ============ onboarding ============ */
  function svgIcon(name){
    const icons = {
      home:'<path d="M3 11 12 4l9 7"/><path d="M5 10v9h14v-9"/><path d="M9.5 19v-5h5v5"/>',
      ledger:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/>',
      board:'<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
      wallet:'<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18"/><circle cx="16" cy="14" r="1.3" fill="currentColor" stroke="none"/>',
      user:'<circle cx="12" cy="8.5" r="3.3"/><path d="M5 20c1.2-4 4-6 7-6s5.8 2 7 6"/>',
      pulse:'<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
      camera:'<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.3"/>',
      video:'<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10.5 21 7v10l-5-3.5z"/>',
      mic:'<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/>'
    };
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+icons[name]+'</svg>';
  }

  function renderOnboarding(){
    const dots = ['start','otp','kyc','selfie','interests','hook','welcome'];
    const dotIdx = dots.indexOf(state.obStep==='phone-gate' ? 'start' : state.obStep);
    let dotsHtml = dots.map((d,i)=>'<i class="'+(i<=dotIdx?'on':'')+'"></i>').join('');

    if(state.obStep==='start'){
      return '<div class="ob">'
        +'<div class="ob-logo"><div class="ring stk"><img class="logo-light" src="'+BRAND+'stacked-light.png" alt="Bharat Foreseez" style=""><img class="logo-dark" src="'+BRAND+'stacked-dark.png" alt="Bharat Foreseez" style=""></div><p>Foresee real&#8209;world outcomes, earn Foreseez Points, redeem non&#8209;cash prizes. No purchase, ever.</p></div>'
        +'<button class="btn btn-block" id="btnGoogle" style="justify-content:flex-start; padding-left:14px;">'+googleG()+'<span style="margin-left:6px;">Continue with Google</span></button>'
        +'<button class="btn btn-block" id="btnApple" style="justify-content:flex-start; padding-left:14px; background:var(--ink); color:var(--page); border-color:var(--ink);">'+appleA()+'<span style="margin-left:6px;">Continue with Apple</span></button>'
        +'<div class="divider">OR CONTINUE WITH PHONE</div>'
        +'<div class="field"><label for="phoneInput">Mobile number</label><input id="phoneInput" type="tel" placeholder="98xxxxxxxx" maxlength="10"></div>'
        +'<button class="btn btn-primary btn-block" id="btnSendOtp">Send OTP</button>'
        +'<p class="hint" style="text-align:center;">By continuing you agree Foreseez Points are non‑purchasable and non‑cash.</p>'
        +'<div class="step-dots">'+dotsHtml+'</div></div>';
    }
    if(state.obStep==='phone-gate'){
      return '<div class="ob">'
        +'<div class="ob-logo"><div class="ring" style="font-size:34px;">📱</div><h1>Verify your number</h1><p>You&rsquo;re signed in as '+esc(state.user.name)+'. One more step &mdash; confirming a real phone number is what keeps Bharat Foreseez&rsquo;s sentiment data authentic, not bot‑generated.</p></div>'
        +'<div class="field"><label for="phoneInput">Mobile number</label><input id="phoneInput" type="tel" placeholder="98xxxxxxxx" maxlength="10"></div>'
        +'<button class="btn btn-primary btn-block" id="btnSendOtp">Send OTP</button>'
        +'<div class="step-dots">'+dotsHtml+'</div></div>';
    }
    if(state.obStep==='otp'){
      return '<div class="ob">'
        +'<div class="ob-logo"><div class="ring"><img class="logo-light mk" src="'+BRAND+'mark-light.png" alt="Bharat Foreseez" style=""><img class="logo-dark mk" src="'+BRAND+'mark-dark.png" alt="Bharat Foreseez" style=""></div><h1>Verify your number</h1><p>Code sent to +91 '+esc(state.otpPhone)+'</p></div>'
        +'<div class="callout"><strong>Demo mode</strong> &mdash; no real SMS is sent. Your OTP is <span class="mono" style="font-weight:700;">'+state.otpCode+'</span></div>'
        +'<div class="field"><label for="otpInput">6‑digit code</label><div class="otp-boxes"><input class="mono" id="otpInput" inputmode="numeric" maxlength="6" placeholder="••••••"></div></div>'
        +'<button class="btn btn-primary btn-block" id="btnVerifyOtp">Verify &amp; continue</button>'
        +'<button class="btn btn-ghost btn-block" id="btnResendOtp">Resend code</button>'
        +'<div class="step-dots">'+dotsHtml+'</div></div>';
    }
    if(state.obStep==='kyc'){
      const age = ageFromDOB(state.dob);
      const underage = state.dob && age!==null && age<18;
      const nameOk = (state.fullName||'').trim().length>1;
      const ageOk = age!==null && age>=18;
      const ageDeclared = !!state.ageDeclared;
      const consentGiven = !!state.consentGiven;
      const canContinue = nameOk && ageOk && ageDeclared && consentGiven;
      return '<div class="ob">'
        +'<div class="ob-logo"><div class="ring"><img class="logo-light mk" src="'+BRAND+'mark-light.png" alt="Bharat Foreseez" style=""><img class="logo-dark mk" src="'+BRAND+'mark-dark.png" alt="Bharat Foreseez" style=""></div><h1>Confirm your details &amp; consent</h1><p>Your number is verified. In line with India&rsquo;s Digital Personal Data Protection Act, here&rsquo;s exactly what we collect and why &mdash; in plain language, before you continue. No PAN or financial KYC needed, since nothing here is ever cashed out.</p></div>'
        +'<div class="field"><label for="fullNameInput">Full name</label><input id="fullNameInput" placeholder="As you’d like it shown on leaderboards" value="'+esc(state.fullName||'')+'"></div>'
        +'<div class="field"><label for="dobInput">Date of birth</label><input id="dobInput" type="date" value="'+esc(state.dob||'')+'"></div>'
        +(underage ? '<div class="callout" style="border-color:var(--status-critical); color:var(--status-critical);"><strong>You must be 18 or older</strong> to use Bharat Foreseez.</div>' : '')
        +'<div class="consent-box">'
          +'<h4>What we collect &amp; why</h4>'
          +'<ul>'
            +'<li>Your name &amp; date of birth &mdash; to confirm you&rsquo;re 18+ and personalise your leaderboard name.</li>'
            +'<li>Your verified phone number &mdash; to confirm a real person is behind every foresight, so our sentiment data reflects real public opinion, not bots.</li>'
            +'<li>Your foresight responses &mdash; aggregated and anonymised into the Pulse sentiment index. Never sold, never linked back to you individually.</li>'
          +'</ul>'
          +'<p class="hint">You can withdraw this consent anytime from Profile. Withdrawing pauses new data collection &mdash; it doesn&rsquo;t delete what&rsquo;s already been aggregated anonymously.</p>'
        +'</div>'
        +'<label class="consent-check"><input type="checkbox" id="chkAgeDeclare" '+(ageDeclared?'checked':'')+'><span>I confirm I am 18 years of age or older, as verified by my date of birth above.</span></label>'
        +'<label class="consent-check"><input type="checkbox" id="chkConsent" '+(consentGiven?'checked':'')+'><span>I have read and agree to the Terms of Use and Privacy Policy, and I consent to Bharat Foreseez collecting my responses as described above.</span></label>'
        +'<button class="btn btn-primary btn-block" id="btnFinishKyc" '+(canContinue?'':'disabled')+' style="margin-top:10px;">Continue</button>'
        +'<p class="hint" style="text-align:center; margin-top:10px; font-size:10.5px;">Bharat Foreseez is an independent platform, not a bank or government body. This notice follows the plain‑language principles of India&rsquo;s DPDP Act &mdash; it is not a KYC or Aadhaar verification process.</p>'
        +'<div class="step-dots">'+dotsHtml+'</div></div>';
    }
    if(state.obStep==='selfie'){
      return '<div class="ob">'
        +'<div class="ob-logo"><div class="ring" style="font-size:34px;">🤳</div><h1>Get your Verified badge</h1><p>A quick selfie confirms a real person is behind this account &mdash; it strengthens the authenticity of Bharat Foreseez&rsquo;s sentiment data. Nothing here is uploaded or stored beyond this session.</p></div>'
        + renderSelfieInner('onboarding')
        + '<p class="hint" style="text-align:center; margin-top:10px;">+100 pts and a blue Verified checkmark, right away.</p>'
        + '<div class="step-dots">'+dotsHtml+'</div></div>';
    }
    if(state.obStep==='interests'){
      const picked = state.interests||[];
      const chips = CATS.map(c=>{
        const on = picked.includes(c.key);
        return '<button data-interest="'+c.key+'" class="interest-chip'+(on?' on':'')+'" style="'+(on?('border-color:'+c.color+'; background:color-mix(in srgb, '+c.color+' 16%, var(--surface)); color:var(--ink);'):'')+'"><span class="emoji">'+c.emoji+'</span>'+c.label+'</button>';
      }).join('');
      return '<div class="ob">'
        +'<div class="ob-logo"><div class="ring" style="font-size:34px;">🔮</div><h1>What are you into?</h1><p>Pick a few &mdash; we’ll surface more of these first. Change this anytime.</p></div>'
        +'<div class="interest-grid">'+chips+'</div>'
        +'<button class="btn btn-primary btn-block" id="btnContinueInterests" style="margin-top:8px;">Continue'+(picked.length?' &middot; '+picked.length+' picked':'')+'</button>'
        +'<div class="step-dots">'+dotsHtml+'</div></div>';
    }
    if(state.obStep==='hook'){
      const c = state.contests.find(x=>x.id===state._hookContestId);
      const def = c ? contestDef(c.id) : null;
      if(!def){
        return '<div class="ob"><div class="ob-logo"><div class="ring" style="font-size:34px;">🎯</div><h1>Let&rsquo;s go</h1></div><button class="btn btn-primary btn-block" id="btnSkipHook">Continue</button><div class="step-dots">'+dotsHtml+'</div></div>';
      }
      if(!state._hookChoice){
        return '<div class="ob">'
          +'<div class="ob-logo"><div class="ring" style="font-size:34px;">🎯</div><h1>Got sharp foresight?</h1><p>Try one for fun &mdash; no risk, and you’ll earn a bonus just for playing.</p></div>'
          +'<div class="card" style="padding:14px 16px;"><h3 style="font-size:14px; margin-bottom:10px;">'+esc(def.title)+'</h3>'
          +'<div class="opt-grid">'
          +'<button class="opt-btn yes" data-hook="yes"><span class="lbl">'+esc(def.yes)+'</span></button>'
          +'<button class="opt-btn no" data-hook="no"><span class="lbl">'+esc(def.no)+'</span></button>'
          +'</div></div>'
          +'<button class="btn btn-ghost btn-block" id="btnSkipHook" style="margin-top:4px;">Maybe later</button>'
          +'<div class="step-dots">'+dotsHtml+'</div></div>';
      }
      const yesPct = chancePct(def, 'yes');
      const withPct = yesPct===null ? null : (state._hookChoice==='yes' ? yesPct : 100-yesPct);
      return '<div class="ob">'
        +'<div class="ob-logo"><div class="ring" style="font-size:34px;">✨</div><h1>Nice pick!</h1><p>'+(withPct===null ? 'You’re among the first to weigh in' : 'You’re with <strong>'+withPct+'%</strong> of players')+' on &ldquo;'+esc(def.title)+'&rdquo;.</p></div>'
        +'<button class="btn btn-primary btn-block" id="btnContinueToWelcome" style="margin-top:8px;">Continue</button>'
        +'<div class="step-dots">'+dotsHtml+'</div></div>';
    }
    if(state.obStep==='welcome'){
      const interestLabels = (state.interests||[]).map(k=>CAT_MAP[k]?CAT_MAP[k].label:k);
      const firstName = (state.user.name||'').trim().split(' ')[0] || 'Player';
      // Project the balance enterApp() is about to credit (signup + KYC bonus,
      // plus anything already earned this onboarding — the selfie bonus and/or
      // the hook bonus) so the displayed starting rank is accurate rather than
      // a hardcoded guess.
      const projectedBalance = balance() + 1000 + 150 + (state._hookChoice ? 30 : 0);
      const startTier = rankTierFor(projectedBalance);
      return '<div class="ob">'
        +'<div class="ob-logo"><div class="ring" style="font-size:38px;">🏆</div><h1>You&rsquo;re all set, '+esc(firstName)+'!</h1>'
        +'<p>Starting rank: <strong>'+startTier.emoji+' '+esc(startTier.name)+'</strong>'+(interestLabels.length?' &middot; watching '+esc(interestLabels.join(', ')):'')+'</p></div>'
        +'<button class="btn btn-primary btn-block" id="btnEnterApp">Enter Bharat Foreseez</button>'
        +'<div class="step-dots">'+dotsHtml+'</div></div>';
    }
    return '';
  }
  function googleG(){ return '<svg width="16" height="16" viewBox="0 0 48 48"><path fill="#4285F4" d="M45 24.5c0-1.6-.1-2.8-.4-4H24v7.6h11.8c-.2 1.9-1.5 4.9-4.3 6.8l-.04.3 6.3 4.9.4.04C42.5 36 45 30.8 45 24.5z"/><path fill="#34A853" d="M24 46c5.7 0 10.5-1.9 14-5.1l-6.7-5.2c-1.8 1.2-4.2 2.1-7.3 2.1-5.6 0-10.3-3.7-12-8.9l-.25.02-6.6 5.1-.09.24C8.4 41 15.6 46 24 46z"/><path fill="#FBBC05" d="M12 28.9c-.4-1.2-.7-2.5-.7-3.9s.3-2.7.7-3.9l-.01-.26-6.7-5.2-.22.1A21.9 21.9 0 0 0 2 25c0 3.6.9 6.9 2.4 9.9L12 28.9z"/><path fill="#EA4335" d="M24 10.8c4 0 6.6 1.7 8.1 3.1l5.9-5.7C34.5 4.9 29.7 3 24 3 15.6 3 8.4 8 5.1 15.2l6.9 5.4c1.7-5.2 6.4-8.9 12-8.9z"/></svg>'; }
  function appleA(){ return '<svg width="15" height="17" viewBox="0 0 384 512" fill="currentColor"><path d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141 8 184.8 8 273.5c0 26.2 4.8 53.3 14.4 81.2 12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-65.7-90-65.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z"/></svg>'; }
  function checkIcon(){ return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--status-good)" stroke-width="2.2"><path d="m5 13 4 4L19 7"/></svg>'; }
  function digiIcon(){ return '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h6"/></svg>'; }
  // Blue checkmark badge — a generic "verified" convention (circle + tick),
  // not any specific platform's proprietary logo. Shown next to a name once
  // the selfie step has been completed.
  function verifiedBadgeIcon(){
    return '<svg class="verified-badge" width="15" height="15" viewBox="0 0 24 24" aria-label="Verified" role="img"><circle cx="12" cy="12" r="12" fill="#1d9bf0"/><path d="m7 12.4 3.2 3.2L17 9" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }

  /* ============ selfie verification (front camera) ============ */
  // The captured frame lives only as a transient data: URL in `state` for the
  // brief "does this look okay?" confirmation screen, then is discarded —
  // never persisted beyond the session, never sent over the network. Camera
  // access degrades gracefully: any denial/absence just falls back to a
  // "verify later from Profile" option rather than blocking onboarding.
  let selfieStream = null;
  function selfieActive(){ return state.obStep==='selfie' || state.selfieSheetOpen; }
  function stopSelfieCamera(){
    if(selfieStream){ selfieStream.getTracks().forEach(function(t){ t.stop(); }); selfieStream = null; }
  }
  function ensureSelfieCamera(){
    if(!selfieActive() || state._selfiePreviewDataUrl || state._selfieCameraError){ stopSelfieCamera(); return; }
    const video = document.getElementById('selfieVideo');
    if(!video) return;
    if(selfieStream){
      if(video.srcObject !== selfieStream) video.srcObject = selfieStream;
      return;
    }
    if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
      state._selfieCameraError = true; render(); return;
    }
    navigator.mediaDevices.getUserMedia({ video:{ facingMode:'user' }, audio:false }).then(function(stream){
      if(!selfieActive() || state._selfiePreviewDataUrl){ stream.getTracks().forEach(function(t){ t.stop(); }); return; }
      selfieStream = stream;
      const v = document.getElementById('selfieVideo');
      if(v){ v.srcObject = stream; v.play().catch(function(){}); }
      else { stream.getTracks().forEach(function(t){ t.stop(); }); selfieStream = null; }
    }).catch(function(){
      state._selfieCameraError = true; render();
    });
  }
  function renderSelfieInner(mode){
    const captured = state._selfiePreviewDataUrl;
    const err = state._selfieCameraError;
    const isOb = mode==='onboarding';
    if(captured){
      return '<div class="selfie-frame"><img src="'+captured+'" alt="Your selfie preview"></div>'
        + '<button class="btn btn-primary btn-block" id="btnConfirmSelfie" style="margin-top:10px;">Looks good &mdash; get Verified</button>'
        + '<button class="btn btn-ghost btn-block" id="btnRetakeSelfie">Retake</button>';
    }
    if(err){
      return '<div class="callout">Camera access isn&rsquo;t available right now &mdash; it may be blocked, denied, or unsupported in this preview.'+(isOb?' You can verify later from Profile instead.':'')+'</div>'
        + '<button class="btn btn-ghost btn-block" id="btnSkipSelfie">'+(isOb?'Continue for now':'Close')+'</button>';
    }
    return (mode==='sheet' ? '<p class="hint" style="margin-bottom:10px;">A quick selfie confirms a real person is behind this account. Nothing here is uploaded or stored beyond this session.</p>' : '')
      + '<div class="selfie-frame"><video id="selfieVideo" autoplay playsinline muted></video></div>'
      + '<button class="btn btn-primary btn-block" id="btnCaptureSelfie" style="margin-top:10px;">Capture</button>'
      + '<button class="btn btn-ghost btn-block" id="btnSkipSelfie">'+(isOb?'Skip for now':'Cancel')+'</button>';
  }
  function renderSelfieSheet(){
    return '<div class="sheet-head"><h3 style="font-size:14px;">Get your Verified badge</h3><button class="btn btn-ghost btn-sm" id="btnCloseSheet" aria-label="Close">&#10005;</button></div>'
      + '<div class="sheet-body">' + renderSelfieInner('sheet') + '</div>';
  }

  /* ============ home / contests ============ */
  function statusChip(c){
    const def = contestDef(c.id);
    if(c.status==='resolved') return '<span class="chip chip-status-muted"><span class="chip-dot"></span>Resolved</span>';
    if(def && def.status==='paused') return '<span class="chip chip-status-muted"><span class="chip-dot"></span>Paused</span>';
    const diff = def && def.closes ? def.closes - liveNow() : Infinity;
    if(diff <= 0) return '<span class="chip chip-status-muted"><span class="chip-dot"></span>Closed</span>';
    if(diff < 24*3600000) return '<span class="chip chip-status-warn"><span class="chip-dot"></span>Closing soon</span>';
    return '<span class="chip chip-status-good"><span class="chip-dot"></span>Open</span>';
  }
  function closesText(def){
    if(!def || !def.closes) return '';
    const diff = def.closes - liveNow();
    if(diff<=0) return 'Closed';
    if(diff < 3600000) return Math.max(1, Math.floor(diff/60000))+'m left';
    const days = Math.floor(diff/86400000), hrs = Math.floor((diff%86400000)/3600000);
    return days>=1 ? days+'d '+hrs+'h left' : hrs+'h left';
  }
  function chancePct(def, key){
    const v = def && def.chance ? def.chance[key] : null;
    return (v===null || v===undefined) ? null : Math.round(v*100);
  }
  function callsText(n){ return fmtNum(n)+' call'+(n===1?'':'s'); }
  function chanceBlock(def){
    if(def.chanceHidden) return '<div class="prob-row"><span class="prob-lbl">Live chance paused for the election period</span></div>';
    const p = chancePct(def, 'yes');
    if(p===null) return '<div class="prob-row"><span class="prob-lbl">No calls yet &mdash; be the first</span></div><div class="prob-bar empty"><i style="width:0%;"></i></div>';
    return '<div class="prob-row"><span class="prob-num">'+p+'%</span><span class="prob-lbl">chance of &ldquo;'+esc(def.yes)+'&rdquo;</span></div>'
      + '<div class="prob-bar"><i style="width:'+p+'%;"></i></div>';
  }
  function feedStateHtml(){
    if(state.feedStatus==='error'){
      const e = state.feedError || {};
      return '<div class="feed-state error" role="alert"><b>Couldn&rsquo;t load questions.</b><span>'+esc(e.message || 'Please try again.')+'</span>'
        + (e.correlationId ? '<span class="ref">Ref: '+esc(e.correlationId)+'</span>' : '')
        + '<button class="btn btn-sm" id="btnRetryFeed">Try again</button></div>';
    }
    return '<div class="feed-state loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading questions&hellip;</div>';
  }
  function feedReady(){ return state.feedStatus==='ready' || state.feedStatus==='refreshing'; }


  function restrictionBanner(){
    const r = restriction();
    if(!r) return '';
    const until = r.until ? ' Until '+new Date(r.until).toLocaleString('en-IN', { dateStyle:'medium', timeStyle:'short' })+'.' : '';
    return '<div class="callout warn" role="status"><strong>'+esc(r.message)+'</strong>'+esc(until)+'</div>';
  }
  function renderHome(){
    const q = (state.searchQuery||'').trim().toLowerCase();
    let filtered = state.contests.filter(c => {
      const def = contestDef(c.id);
      if(!def) return false;
      if(state.catFilter!=='all' && def.category!==state.catFilter) return false;
      if(q && !(def.title.toLowerCase().includes(q) || def.desc.toLowerCase().includes(q))) return false;
      return true;
    });
    filtered = filtered.slice().sort((a,b)=>{
      const da = contestDef(a.id), db = contestDef(b.id);
      if(state.sortMode==='trending') return (db.participants - da.participants) || (da.closes - db.closes);
      return da.closes - db.closes;
    });
    let cards;
    if(!feedReady()) cards = feedStateHtml();
    else if(!state.contests.length) cards = '<div class="feed-state"><b>'+t('no_open')+'</b><span>'+t('no_open_sub')+'</span></div>';
    else cards = filtered.map(c=>{
      const def = contestDef(c.id), cat = CAT_MAP[def.category], mine = state.predictions[c.id];
      return '<div class="contest-card" data-open-contest="'+esc(c.id)+'" role="button" tabindex="0">'
        +'<div class="row1"><span class="chip" style="background:color-mix(in srgb, '+cat.color+' 16%, transparent); color:'+cat.color+';"><span class="chip-dot"></span>'+cat.label+'</span>'+statusChip(c)+'</div>'
        +'<h4>'+esc(def.title)+'</h4>'
        + chanceBlock(def)
        +'<div class="meta"><span>'+closesText(def)+(mine?' &middot; you called':'')+'</span><span class="vol">'+callsText(def.participants)+'</span></div>'
        +'</div>';
    }).join('') || '<p class="hint">No questions match &mdash; try another category or search term.</p>';

    const filters = '<div class="cat-filters">'
      + '<button data-filter="all" class="'+(state.catFilter==='all'?'active':'')+'">'+t('all')+'</button>'
      + CATS.map(c=>'<button data-filter="'+c.key+'" class="'+(state.catFilter===c.key?'active':'')+'"><span class="cat-dot" style="background:'+c.color+';"></span>'+c.label+'</button>').join('')
      + '</div>';

    const openCount = state.contests.length;
    const sub = feedReady() ? openCount+' question'+(openCount===1?'':'s')+' open &middot; '+formatDateLong(liveNow()) : formatDateLong(liveNow());
    const name = state.me ? state.me.display_name : '';
    const bal = state.me ? fmtNum(balance()) : '&mdash;';
    const committed = committedPoints() ? '<div class="sub-k">'+fmtNum(committedPoints())+' '+t('committed')+'</div>' : '';
    return restrictionBanner()
      + '<div class="greet"><div><h2>'+t('namaste')+(name ? ', '+esc(name) : '')+' '+(state.me ? rankBadgeChip(lifetimeEarned()) : '')+'</h2><div class="sub">'+sub+'</div></div></div>'
      + '<div class="balance-card"><div class="k">'+t('points')+'</div><div class="v mono">'+bal+'</div>'+committed+'</div>'
      + renderNewsTicker()
      + '<div class="search-row"><input id="searchInput" type="search" placeholder="'+t('search')+'" aria-label="Search questions" value="'+esc(state.searchQuery||'')+'">'
      + '<div class="sort-toggle"><button data-sort="closing" class="'+(state.sortMode==='closing'?'active':'')+'">'+t('closing_soon')+'</button><button data-sort="trending" class="'+(state.sortMode==='trending'?'active':'')+'">'+t('trending')+'</button></div></div>'
      + filters + '<div>' + cards + '</div>';
  }
  function tickerItem(n, duplicate){
    const cat = CAT_MAP[n.category] || { color:'var(--ink-muted)' };
    const linked = n.question_id && contestDef(n.question_id) ? ' data-open-contest="'+esc(n.question_id)+'"' : '';
    return '<a class="news-item" href="'+esc(n.link)+'" target="_blank" rel="noopener noreferrer"'+linked+(duplicate?' tabindex="-1"':'')+'>'
      + '<span class="cat-dot" style="background:'+cat.color+';"></span>'+esc(n.title)+' <span class="news-src">'+esc(n.source)+'</span></a>';
  }
  function renderNewsTicker(){
    const list = (state.newsFeed||[]).slice(0,12);
    if(!list.length) return '';
    const sep = '<span class="news-sep" aria-hidden="true">&bull;</span>';
    const first = list.map(n=>tickerItem(n,false)).join(sep);
    const second = list.map(n=>tickerItem(n,true)).join(sep);
    return '<div class="news-ticker"><div class="news-hd"><span class="live-label"><span class="live-dot"></span>Context feed</span><span class="news-note">'+esc(state.newsAttribution)+'</span></div>'
      + '<div class="news-track-wrap"><div class="news-track">'+first+sep+'<span aria-hidden="true">'+second+'</span></div></div></div>';
  }

  // Pulse: the national sentiment dashboard. Aggregates only, computed on the server, and
  // nothing for any group under the minimum size (spec s.6).
  function pct(x){ return x===null || x===undefined ? '&mdash;' : Math.round(x*100)+'%'; }
  function shiftText(x){
    if(x===null || x===undefined) return '';
    const p = Math.round(x*100);
    return p===0 ? 'no change today' : (p>0?'&#9650; ':'&#9660; ')+Math.abs(p)+' pts today';
  }
  function sparkline(trend){
    const pts = trend.map(p=>p.chance_yes).filter(v=>v!==null);
    if(pts.length < 2) return '';
    const w = 120, h = 28;
    const d = trend.map((p,i)=> p.chance_yes===null ? null : [i*(w/(trend.length-1)), h - p.chance_yes*h]).filter(Boolean)
      .map((xy,i)=>(i?'L':'M')+xy[0].toFixed(1)+' '+xy[1].toFixed(1)).join(' ');
    return '<svg class="spark" viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" aria-hidden="true"><path d="'+d+'" fill="none" stroke="var(--brand)" stroke-width="1.8"/></svg>';
  }
  function renderPulse(){
    const head = '<div class="dash-head"><div><h2 style="font-size:19px;">'+t('pulse_title')+'</h2>'
      + '<p>What the crowd believes across every open question, captured before the answer is known. Aggregates only.</p></div>'
      + '<span class="live-label"><span class="live-dot"></span>Live</span></div>';
    if(!state.flags.sentiment_dashboard) return head + '<p class="hint">The dashboard isn&rsquo;t available in your region right now.</p>';
    const d = state.sentiment;
    if(!d){
      if(state.sentimentError) return head + '<div class="feed-state error"><b>Couldn&rsquo;t load the dashboard.</b><button class="btn btn-sm" id="btnRetrySentiment">'+t('retry')+'</button></div>';
      return head + '<div class="feed-state loading"><span class="spinner"></span>'+t('loading')+'</div>';
    }
    const tiles = d.categories.map(c=>{
      const cat = CAT_MAP[c.key] || { color:'var(--border)' };
      return '<div class="tile callout" style="border-color:color-mix(in srgb, '+cat.color+' 35%, var(--border));">'
        + '<div class="top"><span class="cat-dot" style="background:'+cat.color+';"></span>'+esc(c.label)+'</div>'
        + (c.enough_data
            ? '<div class="val">'+pct(c.average_lean)+'</div><div class="delta" style="color:var(--ink-muted); font-weight:600;">average lean to the larger side &middot; '+fmtNum(c.participants)+' people</div>'
            : '<div class="val" style="font-size:15px;">Gathering calls</div><div class="delta" style="color:var(--ink-muted); font-weight:600;">Shown once '+d.min_group+'+ people take part</div>')
        + '<div class="hint" style="margin-top:6px;">'+c.questions+' question'+(c.questions===1?'':'s')+'</div></div>';
    }).join('');
    function row(q){
      const cat = CAT_MAP[q.category] || { color:'var(--border)' };
      return '<div class="feed-row" data-open-contest="'+esc(q.id)+'" role="button" tabindex="0" style="cursor:pointer;">'
        + '<span class="who"><span class="cat-dot" style="background:'+cat.color+'; margin-right:6px;"></span>'+esc(q.title)+'</span>'
        + '<span class="meta">'+pct(q.chance_yes)+' &ldquo;'+esc(q.yes_label)+'&rdquo; &middot; '+shiftText(q.shift_24h)+' '+sparkline(q.trend||[])+'</span></div>';
    }
    const thin = '<p class="hint">Appears once a question has '+d.min_group+'+ participants.</p>';
    const quiet = d.election_restricted ? '<div class="callout">Some election questions are hidden during an election quiet period.</div>' : '';
    return head + quiet
      + '<div class="callout" style="margin-bottom:16px;"><strong>'+d.questions_shown+'</strong> of '+d.questions_considered+' recent questions have enough participants to show. Readings appear only for groups of '+d.min_group+' or more, so no individual call can be singled out.</div>'
      + (tiles ? '<div class="tiles">'+tiles+'</div>' : '<p class="hint">No open questions right now.</p>')
      + '<div class="chart-card callout"><h3 style="margin-bottom:2px;">Biggest moves today</h3><p class="hint" style="margin-bottom:8px;">How consensus shifted in the last 24 hours.</p>' + (d.movers.map(row).join('') || thin) + '</div>'
      + '<div class="chart-card callout"><h3 style="margin-bottom:2px;">Most decisive</h3><p class="hint" style="margin-bottom:8px;">Where the crowd is most confident.</p>' + (d.decisive.map(row).join('') || thin) + '</div>'
      + '<div class="chart-card callout"><h3 style="margin-bottom:2px;">Most contested</h3><p class="hint" style="margin-bottom:8px;">Where the crowd is split down the middle.</p>' + (d.contested.map(row).join('') || thin) + '</div>';
  }

  function resultBox(def, mine){
    const r = def.result;
    if(!r) return '';
    const label = r.result==='void' ? 'Voided: every committed point was returned'+(r.reason ? ' ('+esc(r.reason.toLowerCase())+')' : '')
      : 'Result: &ldquo;'+esc(r.result==='yes'?def.yes:def.no)+'&rdquo;';
    let yours = '';
    if(mine){
      if(mine.status==='correct') yours = '<p>Your call was correct: <strong>'+fmtNum(mine.released)+' points released</strong>.</p>';
      else if(mine.status==='incorrect') yours = '<p>Your call didn&rsquo;t match the result.</p>';
      else if(mine.status==='refunded') yours = '<p>Your '+fmtNum(mine.staked)+' points were returned.</p>';
    }
    const windowOpen = r.dispute_until && new Date(r.dispute_until) > liveNow();
    let dispute = '';
    if(mine && windowOpen && r.result!=='void'){
      dispute = state._disputeOpen
        ? '<div class="field"><label for="disputeInput">What&rsquo;s wrong with this result?</label><textarea id="disputeInput" maxlength="1000" rows="3"></textarea></div>'
          + '<div class="field"><label for="disputeLink">Link to evidence (optional, https)</label><input id="disputeLink" type="url" maxlength="500"></div>'
          + '<button class="btn btn-sm" id="btnSendDispute" '+(busy('dispute')?'disabled':'')+'>Send dispute</button>'
        : '<button class="link-btn" id="btnOpenDispute">Dispute this result</button> <span class="hint">until '+new Date(r.dispute_until).toLocaleString('en-IN',{dateStyle:'medium', timeStyle:'short'})+'</span>';
    }
    return '<div class="resolve-box"><h4>'+label+'</h4>'+yours
      + (r.source_url ? '<a href="'+esc(r.source_url)+'" target="_blank" rel="noopener noreferrer">Source used &rarr;</a>' : '')
      + (dispute ? '<div style="margin-top:8px;">'+dispute+'</div>' : '') + '</div>';
  }
  function renderContestSheet(id){
    const def = contestDef(id);
    if(def===undefined || (def===null && state.extraDefs[id]===undefined)) return { title:'Question', body:'<p class="hint">'+t('loading')+'</p>' };
    if(!def) return { title:'Question', body:'<p class="hint">This question is no longer available.</p>' };
    const cat = CAT_MAP[def.category];
    const yesPct = chancePct(def, 'yes');
    const noPct = yesPct===null ? null : 100 - yesPct;
    const mine = state.predictions[id];
    const sel = state._sheetSel || (mine ? mine.option : null);
    const amt = (state._sheetStake===undefined || state._sheetStake===null) ? 50 : state._sheetStake;
    const isOpen = def.status==='open' && def.closes && def.closes > liveNow();
    const res = def.resolution || {};
    const r = rules();

    const head = '<span class="chip" style="background:color-mix(in srgb, '+cat.color+' 16%, transparent); color:'+cat.color+';"><span class="chip-dot"></span>'+cat.label+'</span>'
      + '<h3 class="sheet-title">'+esc(def.title)+'</h3>';
    let body = (def.desc ? '<p style="font-size:12.5px; color:var(--ink-2); line-height:1.55;">'+esc(def.desc)+'</p>' : '')
      + (def.context && def.context.link ? '<p class="hint">Context: <a href="'+esc(def.context.link)+'" target="_blank" rel="noopener noreferrer">'+esc(def.context.headline)+'</a></p>' : '')
      + chanceBlock(def)
      + '<div class="meta" style="margin-top:4px; display:flex; justify-content:space-between;"><span>'+closesText(def)+'</span><span class="vol">'+callsText(def.participants)+'</span></div>'
      + resultBox(def, mine)
      + '<div class="resolve-box"><h4>'+t('how_resolves')+'</h4><p>'+esc(res.rule || '')+'</p>'
      + (res.source_url ? '<a href="'+esc(res.source_url)+'" target="_blank" rel="noopener noreferrer">Official source &rarr;</a>' : '')
      + '<p class="hint" style="margin-top:6px;">Points you could earn: points committed &times; total points on the question &divide; points on the correct outcome. If nobody picks the correct outcome, or everyone picks the same one, the question is voided and every point is returned.</p>'
      + '</div>';

    if(!isOpen){
      if(!def.result) body += '<div class="callout" style="margin-top:10px;">'+(def.status==='paused'
        ? 'Calls are paused on this question for now.'
        : 'This question has closed. The result will be confirmed from the official source above.')+'</div>';
      if(mine && !def.result) body += '<div class="callout">You committed <strong>'+fmtNum(mine.staked)+' pts</strong> to &ldquo;'+esc(mine.option==='yes'?def.yes:def.no)+'&rdquo;. Awaiting the result.</div>';
    } else {
      body += '<div class="opt-grid" style="margin-top:12px;">'
        + optBtn('yes', def.yes, yesPct, sel, mine)
        + optBtn('no', def.no, noPct, sel, mine)
        + '</div>';
      if(mine){
        body += '<div class="callout">You committed <strong>'+fmtNum(mine.staked)+' pts</strong> to &ldquo;'+esc(mine.option==='yes'?def.yes:def.no)+'&rdquo;. Awaiting the result.</div>';
      } else if(restriction()){
        body += restrictionBanner();
      } else if(!state.flags.forecasting){
        body += '<p class="hint">Making calls isn&rsquo;t available in your region right now.</p>';
      } else {
        const limitHint = callsLeftToday()+' of '+dailyCallCap()+' daily calls left';
        const max = Math.min(balance(), r.call_max_points);
        body += '<div class="field" style="margin-top:6px;"><label for="stakeInput">'+t('points_to_commit')+'</label><input class="mono" id="stakeInput" type="number" inputmode="numeric" min="'+r.call_min_points+'" max="'+max+'" value="'+esc(amt)+'"></div>'
          + '<div class="chip-row">'
          + [25,50,100,250].map(v=>'<button data-chip="'+v+'">'+v+'</button>').join('')
          + '<button data-chip="max">Max</button></div>'
          + '<button class="btn btn-primary btn-block" id="btnPlacePrediction" '+(sel&&callsLeftToday()>0&&!busy('call')?'':'disabled')+'>'+(busy('call')?t('loading'):t('make_call'))+'</button>'
          + '<p class="hint" style="margin:8px 0 0; text-align:center;">'+limitHint+' &middot; '+r.call_min_points+'&ndash;'+r.call_max_points+' points per call</p>';
      }
    }
    body += renderThread(id);
    return { title: def.title, head, body };
  }
  function optBtn(key,label,pct_,sel,mine){
    const disabled = !!mine;
    return '<button class="opt-btn '+key+' '+(sel===key?'sel':'')+'" data-opt="'+key+'" '+(disabled?'disabled style="opacity:.6;"':'')+'>'
      + '<span class="lbl">'+esc(label)+'</span>'
      + (pct_===null ? '<span style="font-size:11px; color:var(--ink-muted); font-weight:600;">No calls yet</span>'
          : '<span class="chance-val">'+pct_+'%</span><span style="font-size:10px; color:var(--ink-muted); font-weight:600;">current chance</span>')
      + '</button>';
  }

  /* ============ my calls / ledger / leaderboard / rewards / profile ============ */
  const LEDGER_LABEL = {
    signup_reward:'Welcome reward', checkin_reward:'Daily check-in reward', quiz_reward:'Daily quiz reward',
    call_commit:'Points committed', call_settle:'Call settled', call_refund:'Points returned', reversal:'Correction'
  };
  const CALL_STATUS = { active:['Awaiting result','warn'], correct:['Correct','good'], incorrect:['Settled','muted'], refunded:['Returned','muted'] };
  function renderMyCalls(){
    if(!state.myCalls.length) return '<p class="hint" style="margin-top:12px;">No calls yet. Pick a question on Home and make your first call.</p>';
    return '<div class="card" style="padding:2px 14px; margin-top:8px;">' + state.myCalls.map(c=>{
      const st = CALL_STATUS[c.status] || [c.status,'muted'];
      const outcome = c.status==='correct' ? '+'+fmtNum(c.released)+' released' : c.status==='refunded' ? fmtNum(c.released)+' returned' : fmtNum(c.points)+' committed';
      return '<div class="ledger-row" data-open-contest="'+esc(c.question_id)+'" role="button" tabindex="0" style="cursor:pointer;">'
        + '<div class="txt"><b>'+esc(c.question_title||'Question')+'</b><span>'+esc(c.outcome_label||c.outcome_key)+' &middot; <span class="chip chip-status-'+st[1]+'" style="padding:1px 7px;">'+st[0]+'</span></span></div>'
        + '<div class="amt">'+outcome+'</div></div>';
    }).join('') + '</div>';
  }
  function renderPointsLedger(){
    if(state.ledgerError && !state.ledgerItems.length) return '<div class="feed-state error"><b>Couldn&rsquo;t load your ledger.</b><button class="btn btn-sm" id="btnRetryLedger">'+t('retry')+'</button></div>';
    if(!state.ledgerItems.length) return '<p class="hint" style="margin-top:12px;">'+t('loading')+'</p>';
    const rows = state.ledgerItems.map(e=>{
      const a = e.available_change;
      const sign = a>0 ? '+' : a<0 ? '−' : '';
      const good = a>0;
      const committedNote = e.committed_change ? '<small>'+(e.committed_change>0?'+':'−')+fmtNum(Math.abs(e.committed_change))+' committed</small>' : '';
      return '<div class="ledger-row"><div class="ico" style="background:'+(good?'color-mix(in srgb, var(--status-good) 18%, transparent)':'var(--surface-3)')+'; color:'+(good?'var(--status-good)':'var(--ink-muted)')+'; font-weight:700;">'+(good?'&#8593;':a<0?'&#8722;':'&#8226;')+'</div>'
        + '<div class="txt"><b>'+esc(LEDGER_LABEL[e.kind]||e.kind)+'</b><span>'+(e.memo && !e.memo.startsWith(LEDGER_LABEL[e.kind]||' ') ? esc(e.memo)+' &middot; ' : '')+new Date(e.created_at).toLocaleString('en-IN',{dateStyle:'medium', timeStyle:'short'})+'</span></div>'
        + '<div class="amt" style="color:'+(good?'var(--status-good)':'var(--ink)')+';">'+sign+fmtNum(Math.abs(a))+committedNote+'</div></div>';
    }).join('');
    const more = state.ledgerCursor ? '<button class="btn btn-sm btn-block" id="btnMoreLedger" style="margin-top:8px;">Show more</button>' : '';
    return '<p class="hint">Append-only. Every reward, commitment and return is a permanent entry; corrections are new entries.</p><div class="card" style="padding:2px 14px; margin-top:8px;">'+rows+'</div>'+more;
  }
  function renderLedger(){
    const tab = state.ledgerTab;
    return '<h2 style="font-size:16px; margin:14px 0 8px;">'+t('my_calls')+'</h2>'
      + '<div class="sort-toggle" style="margin-bottom:8px;"><button data-ledger-tab="calls" class="'+(tab==='calls'?'active':'')+'">'+t('my_calls')+'</button><button data-ledger-tab="ledger" class="'+(tab==='ledger'?'active':'')+'">'+t('points_ledger')+'</button></div>'
      + (tab==='calls' ? renderMyCalls() : renderPointsLedger());
  }

  function renderLeaderboard(){
    const p = state.lbPeriod;
    const tabs = [['daily',t('daily')],['weekly',t('weekly')],['all',t('all_time')]].map(([k,l])=>'<button data-lb="'+k+'" class="'+(p===k?'active':'')+'">'+l+'</button>').join('');
    let list;
    if(!state.flags.leaderboards) list = '<p class="hint">Leaderboards aren&rsquo;t available in your region right now.</p>';
    else {
      const board = state.lb[p];
      if(!board) list = state.lbError ? '<div class="feed-state error"><b>Couldn&rsquo;t load rankings.</b><button class="btn btn-sm" id="btnRetryLb">'+t('retry')+'</button></div>' : '<p class="hint">'+t('loading')+'</p>';
      else if(!board.entries.length) list = '<div class="feed-state"><b>No points earned yet in this period.</b><span>Check in, answer the quiz or make a correct call to appear here.</span></div>';
      else {
        list = '<div class="card" style="padding:2px 14px;">' + board.entries.map(e=>
          '<div class="ledger-row'+(e.is_you?' you':'')+'"><div class="ico" style="font-weight:800;">'+e.position+'</div>'
          + '<div class="txt"><b>'+avatarOf(e.avatar)+' '+esc(e.display_name)+(e.is_you?' (you)':'')+'</b><span>'+esc(e.tier)+'</span></div>'
          + '<div class="amt">'+fmtNum(e.points)+' pts</div></div>').join('') + '</div>';
        if(board.you && !board.entries.some(e=>e.is_you)) list += '<p class="hint" style="margin-top:8px;">You: '+fmtNum(board.you.points)+' pts'+(board.you.position ? ' &middot; position '+fmtNum(board.you.position) : '')+'</p>';
      }
    }
    return '<h2 style="font-size:16px; margin:14px 0 4px;">'+t('leaderboards')+'</h2>'
      + '<p class="hint" style="margin-bottom:10px;">Ranked by points earned &mdash; committing points to a call never lowers your rank.</p>'
      + renderRankCard()
      + '<div class="sort-toggle" style="margin:12px 0 8px;">'+tabs+'</div>' + list;
  }

  function renderBadges(){
    const list = (state.me && state.me.badges) || [];
    if(!list.length) return '';
    return '<div class="badge-grid">' + list.map(b=>'<div class="badge-tile'+(b.earned?' on':'')+'" title="'+esc(b.description)+'"><span class="e">'+esc(b.emoji)+'</span><b>'+esc(b.name)+'</b>'
      + '<span class="hint">'+(b.earned ? 'Earned' : fmtNum(b.progress)+' / '+fmtNum(b.threshold))+'</span></div>').join('') + '</div>';
  }
  function renderQuiz(){
    if(!state.flags.quiz) return '';
    const q = state.quiz;
    if(q===undefined) return '';
    if(!q) return '<div class="earn-item"><div><b>'+t('daily_quiz')+'</b><span>No quiz today. Check back tomorrow.</span></div></div>';
    let body = '<div class="quiz"><b>'+t('daily_quiz')+'</b><p>'+esc(q.question)+'</p><div class="quiz-opts">';
    body += q.options.map(o=>{
      let cls = '';
      if(q.answered){ cls = o.key===q.correct_key ? ' right' : (o.key===q.your_answer ? ' wrong' : ''); }
      return '<button class="btn btn-sm'+cls+'" data-quiz="'+esc(o.key)+'" '+(q.answered||busy('quiz')?'disabled':'')+'>'+esc(o.label)+'</button>';
    }).join('') + '</div>';
    if(q.answered) body += '<p class="hint">'+(q.correct ? 'Correct! +'+fmtNum(q.reward_received)+' pts.' : 'Not quite.')+(q.explanation ? ' '+esc(q.explanation) : '')+'</p>';
    else body += '<p class="hint">A correct answer earns '+fmtNum(q.reward)+' points.</p>';
    return body + '</div>';
  }
  function renderWallet(){
    const ci = state.me ? state.me.checkin : null;
    const checkin = !state.flags.checkin ? '' : '<div class="earn-item"><div><b>'+t('daily_checkin')+'</b><span>'
      + (ci ? (ci.streak ? ci.streak+'-day streak &middot; ' : '')+'+'+ci.reward+' pts a day' : '')+'</span></div>'
      + '<button class="btn btn-sm" id="btnCheckin" '+(!ci||ci.checked_in_today||busy('checkin')||restriction()?'disabled':'')+'>'+(ci&&ci.checked_in_today?'Done today':'Check in')+'</button></div>';
    return '<h2 style="font-size:16px; margin:14px 0 4px;">'+t('rewards')+'</h2>'
      + '<div class="balance-card" style="margin-top:8px;"><div class="k">Available</div><div class="v mono">'+fmtNum(balance())+' pts</div>'
      + (committedPoints() ? '<div class="sub-k">'+fmtNum(committedPoints())+' '+t('committed')+'</div>' : '') + '</div>'
      + '<div class="callout" style="margin-bottom:12px;"><strong>Foreseez Points are earned, never sold.</strong> They have no cash value and can&rsquo;t be bought, withdrawn or transferred. Rewards are status only: ranks, badges and standing.</div>'
      + checkin + renderQuiz()
      + '<h3 style="font-size:13px; margin:18px 0 8px;">'+t('badges')+'</h3>' + renderBadges()
      + renderInvites();
  }
  function renderInvites(){
    if(!state.flags.invites || !state.me) return '';
    const inv = state.me.invites;
    const link = location.origin + location.pathname + '?invite=' + encodeURIComponent(inv.code || '');
    return '<h3 style="font-size:13px; margin:18px 0 8px;">Invite friends</h3><div class="card" style="padding:12px 14px;">'
      + '<p class="hint" style="margin:0 0 8px;">Share your link. '+fmtNum(inv.joined)+' friend'+(inv.joined===1?' has':'s have')+' joined. Invites count toward the Connector badge.</p>'
      + '<div class="comment-form"><input id="inviteLink" readonly value="'+esc(link)+'"><button class="btn btn-sm" id="btnCopyInvite">Copy</button></div></div>';
  }
  // Rank card: a screenshot-worthy summary of the player's current named tier.
  function renderRankCard(){
    const pts = lifetimeEarned();
    const tier = rankTierFor(pts);
    const next = tiers().find(t_ => t_.min > pts);
    return '<div class="rank-card" style="background:'+tier.color+';">'
      + '<div class="rank-card-top"><span class="rank-emoji">'+tier.emoji+'</span><span>'+esc(tier.name)+'</span></div>'
      + '<div class="rank-card-pts">'+fmtNum(pts)+' pts earned</div>'
      + (next ? '<div class="rank-card-next">'+fmtNum(next.min-pts)+' pts to '+esc(next.name)+'</div>' : '<div class="rank-card-next">Highest rank achieved</div>')
      + '<button class="btn btn-sm" id="btnShareRank" style="margin-top:12px; background:rgba(255,255,255,.22); color:#fff; border-color:rgba(255,255,255,.45);">Share my rank</button>'
      + '</div>';
  }
  function renderProfile(){
    const me = state.me;
    if(!me) return '<h2 style="font-size:16px; margin:14px 0 4px;">'+t('profile')+'</h2>' + (state.meError ? '<div class="feed-state error"><b>'+esc(errText(state.meError))+'</b><button class="btn btn-sm" id="btnRetryMe">'+t('retry')+'</button></div>' : '<p class="hint">'+t('loading')+'</p>');
    const s = me.stats;
    const states = (state.cfg && state.cfg.states) || [];
    const avatars = Object.keys(AVATARS).map(k=>'<button class="av-pick'+(me.avatar===k?' on':'')+'" data-avatar="'+k+'" aria-label="'+k+'">'+AVATARS[k]+'</button>').join('');
    const nameRow = state._editingName
      ? '<div class="comment-form"><input id="nameInput" maxlength="24" value="'+esc(me.display_name)+'"><button class="btn btn-sm" id="btnSaveName">Save</button></div>'
      : '<b style="font-size:15px;">'+avatarOf(me.avatar)+' '+esc(me.display_name)+'</b> <button class="link-btn" id="btnEditName">Edit</button>';
    const stateOpts = '<option value="">Not set</option>' + states.map(x=>'<option value="'+esc(x.code)+'"'+(me.region===x.code?' selected':'')+'>'+esc(x.name)+'</option>').join('');
    const lang = getLang();
    return '<h2 style="font-size:16px; margin:14px 0 4px;">'+t('profile')+'</h2>'
      + restrictionBanner()
      + '<div class="card" style="padding:14px 16px; display:flex; flex-direction:column; gap:10px;">'
      + '<div>'+nameRow+'</div><div class="av-row">'+avatars+'</div>'
      + '<div class="field"><label for="regionSelect">Your state</label><select id="regionSelect">'+stateOpts+'</select><span class="hint">Used only for regional settings. Optional.</span></div>'
      + '<p class="hint" style="margin:0;">Pseudonymous account on this device. Phone sign-in arrives soon; your points and calls will carry over.</p>'
      + '</div>'
      + renderRankCard()
      + '<div class="tiles" style="margin-top:12px;">'
      + '<div class="tile callout"><div class="top">Calls</div><div class="val">'+fmtNum(s.calls)+'</div></div>'
      + '<div class="tile callout"><div class="top">Accuracy</div><div class="val">'+(s.accuracy===null?'&mdash;':Math.round(s.accuracy*100)+'%')+'</div><div class="hint">'+s.correct+' correct of '+(s.correct+s.incorrect)+' settled</div></div>'
      + '<div class="tile callout"><div class="top">Best streak</div><div class="val">'+fmtNum(s.longest_streak)+'</div></div></div>'
      + '<h3 style="font-size:13px; margin:18px 0 8px;">'+t('badges')+'</h3>' + renderBadges()
      + renderSafeguards()
      + renderGrievanceCard()
      + renderPrivacy()
      + '<div class="card" style="padding:12px 14px; margin-top:12px;"><span class="k">'+t('language')+'</span><div class="sort-toggle" style="margin-top:8px;">'
      + '<button data-lang="en" class="'+(lang==='en'?'active':'')+'">English</button><button data-lang="hi" class="'+(lang==='hi'?'active':'')+'">हिंदी</button></div></div>';
  }
  function renderSafeguards(){
    const days = rules().self_exclusion_days || [1,7,30,90];
    return '<div class="card" style="padding:12px 14px; margin-top:12px;"><span class="k">'+t('take_break')+'</span>'
      + '<p class="hint" style="margin:6px 0 8px;">Pause calls and posting for a while. A break can be extended but not cut short. Up to '+dailyCallCap()+' calls a day; you&rsquo;ll get a reminder after '+rules().session_reminder_minutes+' minutes in the app.</p>'
      + '<div class="chip-row">'+days.map(d=>'<button data-exclude="'+d+'">'+d+' day'+(d===1?'':'s')+'</button>').join('')+'</div></div>';
  }
  function renderGrievanceCard(){
    const g = state.grievance || {};
    const rows = [g.name && '<b>'+esc(g.name)+'</b>',
                  g.email && '<a href="mailto:'+esc(g.email)+'">'+esc(g.email)+'</a>',
                  g.phone && '<span>'+esc(g.phone)+'</span>',
                  g.address && '<span class="hint">'+esc(g.address)+'</span>'].filter(Boolean);
    const cats = (state.cfg && state.cfg.grievance_categories) || [];
    const form = state._grievanceOpen
      ? '<div class="field"><label for="gCat">About</label><select id="gCat">'+cats.map(c=>'<option value="'+esc(c.key)+'">'+esc(c.label)+'</option>').join('')+'</select></div>'
        + '<div class="field"><label for="gSubject">Subject</label><input id="gSubject" maxlength="140"></div>'
        + '<div class="field"><label for="gDesc">What happened?</label><textarea id="gDesc" rows="4" maxlength="3000"></textarea></div>'
        + '<label class="media-consent"><input type="checkbox" id="gConsent"> Let support look at my calls and points for this complaint only.</label>'
        + '<button class="btn btn-sm btn-primary" id="btnSendGrievance" '+(busy('grievance')?'disabled':'')+'>Send</button> <button class="link-btn" id="btnCancelGrievance">Cancel</button>'
      : '<button class="btn btn-sm" id="btnOpenGrievance">Raise a complaint</button>';
    const mine = state.grievances.map(x=>'<div class="ledger-row"><div class="txt"><b>'+esc(x.ref)+' &middot; '+esc(x.subject)+'</b><span>'+esc(x.status.replace('_',' '))
      + (x.resolution ? ' &middot; '+esc(x.resolution) : (x.updates.length ? ' &middot; '+esc(x.updates[x.updates.length-1].note) : ''))+'</span></div></div>').join('');
    return '<div class="card grievance" style="margin-top:12px;"><span class="k">'+t('help')+'</span>'
      + '<span>We acknowledge complaints within 24 hours and resolve them within 15 days.</span>'
      + form + (mine ? '<div style="margin-top:8px;">'+mine+'</div>' : '')
      + '<span style="margin-top:8px;">Grievance Officer'+(rows.length ? ':' : '')+'</span>'
      + (rows.length ? rows.join('') : '<span class="hint">Contact details are being finalised.</span>')
      + '</div>';
  }
  function renderPrivacy(){
    const legal = (state.cfg && state.cfg.legal) || {};
    const blocks = state.blocks.length ? '<p class="hint" style="margin:8px 0 4px;">Blocked:</p>' + state.blocks.map(b=>'<div class="earn-item"><div><b>'+esc(b.display_name)+'</b></div><button class="btn btn-sm" data-unblock="'+esc(b.user_id)+'">Unblock</button></div>').join('') : '';
    return '<div class="card" style="padding:12px 14px; margin-top:12px;"><span class="k">'+t('privacy')+'</span>'
      + '<p class="hint" style="margin:6px 0 8px;">The sentiment dashboard only ever shows anonymous totals. You can download a copy of your data or close your account at any time.</p>'
      + '<div class="chip-row"><button id="btnExportData">Download my data</button><button id="btnDeleteAccount">Close my account</button></div>'
      + blocks
      + ((legal.privacy_notice_url || legal.terms_url) ? '<p class="hint" style="margin-top:8px;">'
        + (legal.privacy_notice_url ? '<a href="'+esc(legal.privacy_notice_url)+'" target="_blank" rel="noopener">Privacy notice</a> ' : '')
        + (legal.terms_url ? '<a href="'+esc(legal.terms_url)+'" target="_blank" rel="noopener">Terms</a>' : '') + '</p>' : '')
      + '</div>';
  }

  /* ============ phone render / router ============ */
  function renderPhoneNav(){
    if(!state.user.signedIn){ document.getElementById('phoneNav').innerHTML=''; return; }
    const tabs = [['home','nav_home'],['pulse','nav_pulse'],['ledger','nav_ledger'],['leaderboard','nav_ranks'],['wallet','nav_wallet'],['profile','nav_profile']];
    const iconFor = {home:'home',pulse:'pulse',ledger:'ledger',leaderboard:'board',wallet:'wallet',profile:'user'};
    document.getElementById('phoneNav').innerHTML = tabs.map(([key,label])=>
      '<button data-nav="'+key+'" class="'+(state.phoneScreen===key?'active':'')+'">'+svgIcon(iconFor[key])+t(label)+'</button>'
    ).join('');
  }
  function updateBanner(){
    const cfg = state.cfg;
    if(!cfg) return '';
    if(APP_BUILD < cfg.min_supported_build) return '<div class="update-block"><h2>Update required</h2><p>This version of Bharat Foreseez is no longer supported. Please update the app to continue.</p></div>';
    if(APP_BUILD < cfg.latest_build) return '<div class="callout">A newer version of the app is available. Update for the latest features and fixes.</div>';
    return '';
  }
  function renderPhoneBody(){
    let html='';
    const upd = updateBanner();
    if(upd.indexOf('update-block')>=0) html = upd;
    else if(!state.user.signedIn) html = renderOnboarding();
    else if(state.phoneScreen==='home') html = upd + renderHome();
    else if(state.phoneScreen==='pulse') html = renderPulse();
    else if(state.phoneScreen==='ledger') html = renderLedger();
    else if(state.phoneScreen==='leaderboard') html = renderLeaderboard();
    else if(state.phoneScreen==='wallet') html = renderWallet();
    else if(state.phoneScreen==='profile') html = renderProfile();
    document.getElementById('phoneBody').innerHTML = html;
  }
  function renderNotifPanel(){
    const rows = state.notifications.length
      ? state.notifications.map(n=>'<div class="notif-row '+(n.read?'read':'')+'"><span class="dot"></span><div class="txt"><span>'+esc(n.text)+'</span><span class="t">'+n.ts+'</span></div></div>').join('')
      : '<p class="hint">No notifications yet &mdash; results on questions you&rsquo;ve called will show up here.</p>';
    return '<div class="sheet-head"><h3 style="font-size:14px;">Notifications</h3><button class="btn btn-ghost btn-sm" id="btnCloseSheet" aria-label="Close">&#10005;</button></div><div class="sheet-body">'+rows+'</div>';
  }
  function renderSheet(){
    const backdrop = document.getElementById('sheetBackdrop'), sheet = document.getElementById('sheet');
    if(state.notifPanelOpen){
      sheet.innerHTML = renderNotifPanel();
      backdrop.classList.add('open'); sheet.classList.add('open');
      return;
    }
    if(state.selfieSheetOpen){
      sheet.innerHTML = renderSelfieSheet();
      backdrop.classList.add('open'); sheet.classList.add('open');
      return;
    }
    if(!state.openContest){ backdrop.classList.remove('open'); sheet.classList.remove('open'); sheet.innerHTML=''; return; }
    const {head, body} = renderContestSheet(state.openContest);
    sheet.dataset.qid = state.openContest;
    sheet.innerHTML = '<div class="sheet-head"><div class="sheet-head-main">'+(head || '<h3 class="sheet-title">Your call</h3>')+'</div><button class="btn btn-ghost btn-sm" id="btnCloseSheet" aria-label="Close">&#10005;</button></div><div class="sheet-body">'+body+'</div>';
    backdrop.classList.add('open'); sheet.classList.add('open');
  }
  function renderPhone(){ renderPhoneBody(); renderPhoneNav(); renderSheet(); renderNotifBadge(); }
  /* ============ actions ============ */
  function place(action, payload){
    switch(action){
      case 'google': case 'apple': {
        state.user.name = action==='google' ? 'Aisha Rao' : 'Kabir Singh';
        state.user.method = action==='google' ? 'Google' : 'Apple';
        state.fullName = state.user.name; // pre-filled, editable on the next step
        // Every account — SSO or phone-first — now verifies a real phone
        // number by OTP before continuing. This is what backs the "authentic,
        // real-human sentiment data" claim: a Google/Apple sign-in alone
        // doesn't prove a real person is behind the foresights that follow.
        state.obStep = 'phone-gate';
        render(); toast('Signed in with '+state.user.method);
        return;
      }
      case 'sendOtp': {
        const val = document.getElementById('phoneInput').value.trim();
        if(!/^[6-9]\d{9}$/.test(val)){ toast('Enter a valid 10‑digit mobile number'); return; }
        state.otpPhone = val.slice(0,2)+'••••••'+val.slice(-2);
        state._realPhone = val;
        state.otpCode = String(Math.floor(100000+Math.random()*900000));
        state.obStep='otp'; render(); break;
      }
      case 'resendOtp': {
        state.otpCode = String(Math.floor(100000+Math.random()*900000));
        toast('New code sent'); render(); break;
      }
      case 'verifyOtp': {
        const val = document.getElementById('otpInput').value.trim();
        if(val !== state.otpCode){ toast('Incorrect code, try again'); return; }
        state.phoneVerified = true;
        state.obStep='kyc'; render(); break;
      }
      case 'finishKyc': {
        const age = ageFromDOB(state.dob);
        if(!(state.fullName||'').trim()){ toast('Enter your full name'); return; }
        if(age===null){ toast('Enter your date of birth'); return; }
        if(age<18){ toast('You must be 18 or older to use Bharat Foreseez'); return; }
        if(!state.ageDeclared){ toast('Please confirm the age declaration'); return; }
        if(!state.consentGiven){ toast('Please accept the consent to continue'); return; }
        state.user.name = state.fullName.trim();
        if(!state.user.method){ state.user.method = 'Phone + OTP'; }
        state.obStep = 'selfie';
        state._selfieCameraError = false;
        render(); break;
      }
      case 'captureSelfie': {
        const video = document.getElementById('selfieVideo');
        if(!video || !video.videoWidth){ toast('Camera still loading — try again in a moment'); return; }
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth; canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        // Mirror the drawn frame so the captured photo matches the mirrored
        // live preview the user just looked at (front-camera selfie apps
        // mirror the preview; without this the saved photo looks flipped).
        ctx.translate(canvas.width, 0); ctx.scale(-1, 1);
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        state._selfiePreviewDataUrl = canvas.toDataURL('image/jpeg', 0.85);
        render(); break;
      }
      case 'retakeSelfie': { state._selfiePreviewDataUrl = null; render(); break; }
      case 'confirmSelfie': {
        // Selfie image never leaves the device: it exists only as a data URL
        // in memory for this immediate confirm step, then is discarded —
        // never added to persistent state, never sent over the network.
        state.selfieVerified = true;
        state.selfieSkipped = false;
        state._selfiePreviewDataUrl = null;
        if(state.obStep==='selfie'){ state.obStep = 'interests'; }
        else { state.selfieSheetOpen = false; }
        render(); break;
      }
      case 'skipSelfie': {
        state.selfieSkipped = true;
        state._selfiePreviewDataUrl = null;
        if(state.obStep==='selfie'){ state.obStep = 'interests'; }
        else { state.selfieSheetOpen = false; }
        render(); break;
      }
      case 'openSelfieSheet': {
        state.selfieSheetOpen = true;
        state._selfieCameraError = false;
        state._selfiePreviewDataUrl = null;
        state.openContest = null; state.notifPanelOpen = false;
        render(); break;
      }
      case 'toggleInterest': {
        const list = state.interests || (state.interests=[]);
        const i = list.indexOf(payload);
        if(i>=0) list.splice(i,1); else list.push(payload);
        render(); break;
      }
      case 'continueInterests': {
        const openList = state.contests.filter(c=>c.status==='open');
        const pick = openList.slice().sort((a,b)=>contestDef(b.id).participants-contestDef(a.id).participants)[0];
        state._hookContestId = pick ? pick.id : null;
        state._hookChoice = null;
        state.obStep = 'hook';
        render(); break;
      }
      case 'hookPick': {
        if(state._hookChoice) return;
        state._hookChoice = payload;
        render(); break;
      }
      case 'skipHook': { state.obStep='welcome'; render(); break; }
      case 'continueToWelcome': { state.obStep='welcome'; render(); break; }
      case 'enterApp': {
        state.user.signedIn = true;
        loadMe(); loadMyCalls();
        state.catFilter = (state.interests && state.interests[0]) || 'all';
        state.phoneScreen='home';
        render(); toast('Welcome to Bharat Foreseez'); break;
      }
      case 'nav': {
        state.phoneScreen = payload; state._sheetSel=null; render();
        if(payload==='pulse') loadSentiment();
        else if(payload==='ledger'){ loadMyCalls(); if(state.ledgerTab==='ledger') loadLedger(false); }
        else if(payload==='leaderboard') loadLeaderboard(state.lbPeriod);
        else if(payload==='wallet'){ loadMe(); loadQuiz(); }
        else if(payload==='profile'){ loadMe(); loadGrievances(); loadBlocks(); }
        break;
      }
      case 'filter': { state.catFilter = payload; render(); break; }
      case 'sort': { state.sortMode = payload; render(); break; }
      case 'openContest': {
        state.openContest = payload; state._sheetSel=null; state._sheetStake=50; state._commentDraft='';
        state.replyTo=null; state._reportFor=null; state._disputeOpen=false; state._callKey=null;
        state.notifPanelOpen=false; state.selfieSheetOpen=false;
        render(); ensureQuestion(payload); loadThread(payload); break;
      }
      case 'closeSheet': { state.openContest=null; state.notifPanelOpen=false; state.selfieSheetOpen=false; render(); break; }
      case 'toggleBell': {
        state.openContest=null;
        state.selfieSheetOpen=false;
        state.notifPanelOpen = true;
        state.notifications.forEach(n=>n.read=true);
        render(); break;
      }
      case 'selectOpt': { state._sheetSel = payload; render(); break; }
      case 'chip': {
        state._sheetStake = payload==='max' ? Math.min(balance(), rules().call_max_points) : Number(payload);
        render(); break;
      }
      case 'placePrediction': { placeCall(); break; }
      case 'checkin': { doCheckin(); break; }
      case 'shareRank': {
        const tier = rankTierFor(lifetimeEarned());
        const text = 'I’m '+tier.name+' on Bharat Foreseez with '+fmtNum(lifetimeEarned())+' points earned.';
        if(navigator.share) navigator.share({ text }).catch(()=>{});
        else if(navigator.clipboard) navigator.clipboard.writeText(text).then(()=>toast('Copied to share'));
        break;
      }
    }
  }

  /* ============ server actions ============ */
  async function placeCall(){
    const input = document.getElementById('stakeInput');
    const amt = Math.round(Number(input && input.value));
    const sel = state._sheetSel, r = rules();
    const id = state.openContest, def = contestDef(id);
    if(!sel){ toast('Choose an outcome first'); return; }
    if(!amt || amt < r.call_min_points || amt > r.call_max_points){ toast('Commit between '+r.call_min_points+' and '+r.call_max_points+' points'); return; }
    if(amt > balance()){ toast('Not enough points'); return; }
    if(!def || def.status!=='open' || !(def.closes > liveNow())){ toast('This question is no longer open'); return; }
    if(busy('call')) return;
    // One key per attempt at this call: a retry after a network error reuses it, so the
    // server never commits points twice.
    state._callKey = state._callKey || newId();
    busy('call', true); render();
    try {
      await api.call(id, sel, amt, state._callKey);
      state._callKey = null;
      toast('Call locked in');
      await Promise.all([loadMe(), loadMyCalls(), refreshOpenQuestion()]);
      loadFeed();
    } catch(e){
      if(e.status && e.status < 500) state._callKey = null;   // a definite refusal: next try is new
      toast(errText(e));
      if(e.code==='ALREADY_CALLED' || e.code==='INSUFFICIENT_POINTS') loadMe();
    } finally { busy('call', false); render(); }
  }
  async function doCheckin(){
    if(busy('checkin')) return;
    busy('checkin', true); render();
    try { const r = await api.checkin(); toast(r.reward ? '+'+r.reward+' pts · day '+r.streak : 'Checked in · daily reward limit reached'); await loadMe(); }
    catch(e){ toast(errText(e)); }
    finally { busy('checkin', false); render(); }
  }
  async function answerQuiz(key){
    if(busy('quiz') || !state.quiz) return;
    busy('quiz', true); render();
    try { state.quiz = await api.answerQuiz(state.quiz.id, key); if(state.quiz.correct) loadMe(); }
    catch(e){ toast(errText(e)); }
    finally { busy('quiz', false); render(); }
  }
  async function postComment(){
    const input = document.getElementById('commentInput');
    const txt = (input ? input.value : '').trim();
    const qid = state.openContest;
    if(!txt || !qid || busy('comment')) return;
    busy('comment', true); render();
    try {
      await api.postComment(qid, txt, state.replyTo);
      state._commentDraft = ''; state.replyTo = null;
      await loadThread(qid);
    } catch(e){ toast(errText(e)); }
    finally { busy('comment', false); render(); }
  }
  async function deleteComment(id){
    if(!confirm('Delete your comment?')) return;
    try { await api.deleteComment(id); await loadThread(state.openContest); toast('Comment deleted'); }
    catch(e){ toast(errText(e)); }
  }
  async function reportComment(reason){
    const id = state._reportFor;
    state._reportFor = null; render();
    try { await api.reportComment(id, reason); toast('Reported. A moderator will review it.'); }
    catch(e){ toast(errText(e)); }
  }
  async function blockAuthor(id){
    if(!confirm('Block this person? You won’t see their comments.')) return;
    try { await api.blockAuthor(id); await loadThread(state.openContest); toast('Blocked'); }
    catch(e){ toast(errText(e)); }
  }
  async function sendDispute(){
    const reason = (document.getElementById('disputeInput')||{}).value || '';
    const link = (document.getElementById('disputeLink')||{}).value || '';
    if(reason.trim().length < 10){ toast('Explain the problem in at least 10 characters'); return; }
    busy('dispute', true); render();
    try { await api.dispute(state.openContest, reason.trim(), link.trim()); state._disputeOpen = false; toast('Dispute sent. You’ll see the outcome in Profile.'); }
    catch(e){ toast(errText(e)); }
    finally { busy('dispute', false); render(); }
  }
  async function saveProfile(patch, okMsg){
    try { await api.updateMe(patch); state._editingName = false; await loadMe(); if(okMsg) toast(okMsg); }
    catch(e){ toast(errText(e)); }
  }
  async function selfExclude(days){
    if(!confirm('Take a '+days+'-day break? You won’t be able to make calls or post until it ends, and it can’t be cut short.')) return;
    try { await api.selfExclude(days); await loadMe(); toast('Your break has started'); }
    catch(e){ toast(errText(e)); }
  }
  async function sendGrievance(){
    const v = id => (document.getElementById(id)||{}).value || '';
    const body = { category:v('gCat'), subject:v('gSubject').trim(), description:v('gDesc').trim(),
                   question_id: state.openContest || null,
                   support_review_consent: !!(document.getElementById('gConsent')||{}).checked };
    if(body.subject.length < 5 || body.description.length < 20){ toast('Add a subject and describe the problem (20+ characters)'); return; }
    busy('grievance', true); render();
    try { const g = await api.raiseGrievance(body); state._grievanceOpen = false; toast('Complaint '+g.ref+' received'); await loadGrievances(); }
    catch(e){ toast(errText(e)); }
    finally { busy('grievance', false); render(); }
  }
  async function exportData(){
    try {
      const data = await api.exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type:'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = 'bharat-foreseez-my-data.json';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(()=>URL.revokeObjectURL(a.href), 2000);
    } catch(e){ toast(errText(e)); }
  }
  async function deleteAccount(){
    const typed = prompt('This closes your account and removes your name and details. Your points can’t be recovered. Type DELETE to confirm.');
    if(typed !== 'DELETE') return;
    try {
      await api.deleteAccount();
      try { localStorage.removeItem('bf-session'); localStorage.removeItem(CALL_STATUS_KEY); } catch(_) {}
      toast('Your account is closed');
      setTimeout(()=>location.reload(), 1200);
    } catch(e){ toast(errText(e)); }
  }
  async function unblock(uid){
    try { await api.unblock(uid); await loadBlocks(); } catch(e){ toast(errText(e)); }
  }

  /* ============ event delegation ============ */
  /* ============ theme (light / dark) ============ */
  const THEME_KEY = 'bf-theme';
  const SUN_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const MOON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  function effectiveTheme(){
    const attr = document.documentElement.getAttribute('data-theme');
    if(attr === 'light' || attr === 'dark') return attr;
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  }
  function paintThemeIcon(){
    const b = document.getElementById('btnTheme');
    if(!b) return;
    // Show the icon for the mode you'd switch TO.
    b.innerHTML = effectiveTheme() === 'dark' ? SUN_SVG : MOON_SVG;
  }
  function applyTheme(mode){
    document.documentElement.setAttribute('data-theme', mode);
    try{ localStorage.setItem(THEME_KEY, mode); }catch(e){}
    paintThemeIcon();
  }
  function initTheme(){
    let saved = null;
    try{ saved = localStorage.getItem(THEME_KEY); }catch(e){}
    if(saved === 'light' || saved === 'dark') document.documentElement.setAttribute('data-theme', saved);
    paintThemeIcon();
  }
  function toggleTheme(){ applyTheme(effectiveTheme() === 'dark' ? 'light' : 'dark'); }
  initTheme();

  document.body.addEventListener('click', function(e){
    const t_ = e.target;
    const idHandlers = {
      btnGoogle:()=>place('google'), btnApple:()=>place('apple'), btnSendOtp:()=>place('sendOtp'),
      btnVerifyOtp:()=>place('verifyOtp'), btnResendOtp:()=>place('resendOtp'),
      btnFinishKyc:()=>place('finishKyc'), btnCloseSheet:()=>place('closeSheet'),
      btnContinueInterests:()=>place('continueInterests'), btnSkipHook:()=>place('skipHook'),
      btnContinueToWelcome:()=>place('continueToWelcome'), btnEnterApp:()=>place('enterApp'),
      btnPlacePrediction:()=>place('placePrediction'), btnCheckin:()=>place('checkin'),
      btnBell:()=>place('toggleBell'), btnTheme:()=>toggleTheme(),
      btnRetryFeed:()=>{ loadFeed(); loadTicker(); }, btnRetrySentiment:()=>loadSentiment(),
      btnRetryLedger:()=>loadLedger(false), btnMoreLedger:()=>loadLedger(true), btnRetryLb:()=>loadLeaderboard(state.lbPeriod),
      btnRetryMe:()=>loadMe(),
      btnPostComment:()=>postComment(), btnCancelReply:()=>{ state.replyTo=null; render(); },
      btnOpenDispute:()=>{ state._disputeOpen=true; render(); }, btnSendDispute:()=>sendDispute(),
      btnShareRank:()=>place('shareRank'),
      btnEditName:()=>{ state._editingName=true; render(); },
      btnSaveName:()=>saveProfile({ display_name:(document.getElementById('nameInput')||{}).value || '' }, 'Name updated'),
      btnOpenGrievance:()=>{ state._grievanceOpen=true; render(); }, btnCancelGrievance:()=>{ state._grievanceOpen=false; render(); },
      btnSendGrievance:()=>sendGrievance(), btnExportData:()=>exportData(), btnDeleteAccount:()=>deleteAccount(),
      btnCopyInvite:()=>{ const el=document.getElementById('inviteLink'); if(el && navigator.clipboard) navigator.clipboard.writeText(el.value).then(()=>toast('Invite link copied')); },
      btnCaptureSelfie:()=>place('captureSelfie'), btnRetakeSelfie:()=>place('retakeSelfie'),
      btnConfirmSelfie:()=>place('confirmSelfie'), btnSkipSelfie:()=>place('skipSelfie')
    };
    const idBtn = t_.closest('button[id]');
    if(idBtn && idHandlers[idBtn.id]){ idHandlers[idBtn.id](); return; }
    const data = (sel)=>t_.closest(sel);
    let el;
    if((el = data('button[data-nav]'))){ place('nav', el.dataset.nav); return; }
    if((el = data('button[data-filter]'))){ place('filter', el.dataset.filter); return; }
    if((el = data('button[data-sort]'))){ place('sort', el.dataset.sort); return; }
    if((el = data('button[data-ledger-tab]'))){ state.ledgerTab = el.dataset.ledgerTab; render(); if(state.ledgerTab==='ledger') loadLedger(false); return; }
    if((el = data('button[data-lb]'))){ state.lbPeriod = el.dataset.lb; render(); loadLeaderboard(state.lbPeriod); return; }
    if((el = data('button[data-quiz]'))){ answerQuiz(el.dataset.quiz); return; }
    if((el = data('button[data-reply]'))){ state.replyTo = Number(el.dataset.reply); state._reportFor=null; render(); const i=document.getElementById('commentInput'); if(i) i.focus(); return; }
    if((el = data('button[data-del-comment]'))){ deleteComment(Number(el.dataset.delComment)); return; }
    if((el = data('button[data-report-comment]'))){ const id=Number(el.dataset.reportComment); state._reportFor = state._reportFor===id ? null : id; render(); return; }
    if((el = data('button[data-report-reason]'))){ reportComment(el.dataset.reportReason); return; }
    if((el = data('button[data-block-author]'))){ blockAuthor(Number(el.dataset.blockAuthor)); return; }
    if((el = data('button[data-reload-thread]'))){ loadThread(el.dataset.reloadThread); return; }
    if((el = data('button[data-avatar]'))){ saveProfile({ avatar: el.dataset.avatar }); return; }
    if((el = data('button[data-exclude]'))){ selfExclude(Number(el.dataset.exclude)); return; }
    if((el = data('button[data-unblock]'))){ unblock(el.dataset.unblock); return; }
    if((el = data('button[data-lang]'))){ setLang(el.dataset.lang); render(); return; }
    const cardOpen = data('[data-open-contest]');
    if(cardOpen){ if(cardOpen.tagName==='A') e.preventDefault(); place('openContest', cardOpen.dataset.openContest); return; }
    if((el = data('button[data-interest]'))){ place('toggleInterest', el.dataset.interest); return; }
    if((el = data('button[data-hook]'))){ place('hookPick', el.dataset.hook); return; }
    if((el = data('button[data-opt]')) && !el.disabled){ place('selectOpt', el.dataset.opt); return; }
    if((el = data('button[data-chip]'))){ place('chip', el.dataset.chip); return; }
  });
  document.getElementById('sheetBackdrop').addEventListener('click', ()=>place('closeSheet'));
  document.body.addEventListener('keydown', function(e){
    if((e.key==='Enter' || e.key===' ') && e.target.matches && e.target.matches('[data-open-contest][role="button"]')){
      e.preventDefault(); place('openContest', e.target.dataset.openContest); return;
    }
    if(e.key==='Enter'){
      if(e.target.id==='phoneInput') place('sendOtp');
      if(e.target.id==='otpInput') place('verifyOtp');
      if(e.target.id==='commentInput') postComment();
      if(e.target.id==='nameInput') idClick('btnSaveName');
    }
  });
  function idClick(id){ const b = document.getElementById(id); if(b) b.click(); }
  document.body.addEventListener('input', function(e){
    const el = e.target;
    if(el.id==='searchInput'){ state.searchQuery = el.value; render(); }
    else if(el.id==='stakeInput'){ state._sheetStake = el.value===''? '' : Number(el.value); }
    else if(el.id==='commentInput'){ state._commentDraft = el.value; }
    else if(el.id==='fullNameInput'){ state.fullName = el.value; render(); }
    else if(el.id==='dobInput'){ state.dob = el.value; render(); }
  });
  document.body.addEventListener('change', function(e){
    if(e.target.id==='chkAgeDeclare'){ state.ageDeclared = e.target.checked; render(); }
    else if(e.target.id==='chkConsent'){ state.consentGiven = e.target.checked; render(); }
    else if(e.target.id==='regionSelect'){
      const v = e.target.value;
      saveProfile(v ? { region:v } : { clear_region:true }, 'State saved');
    }
  });


  /* ============ live refresh ============ */
  function refreshIfVisible(){
    if(document.visibilityState!=='visible' || !state.user.signedIn) return;
    if(Date.now() - feedLoadedAt >= FEED_MIN_GAP_MS) loadFeed();
  }
  setInterval(refreshIfVisible, FEED_REFRESH_MS);
  setInterval(function(){ if(document.visibilityState==='visible') loadTicker(); }, TICKER_REFRESH_MS);
  setInterval(refreshOpenQuestion, SHEET_REFRESH_MS);
  // Results land while the app is open: check your calls now and then.
  setInterval(function(){ if(document.visibilityState==='visible' && state.myCalls.some(c=>c.status==='active')) loadMyCalls(); }, 120000);
  document.addEventListener('visibilitychange', refreshIfVisible);

  // Safeguard (spec s.2): a reminder after a stretch of continuous use.
  let sessionStartedAt = Date.now();
  setInterval(function(){
    if(document.visibilityState!=='visible'){ return; }
    const mins = rules().session_reminder_minutes;
    if(mins && Date.now() - sessionStartedAt >= mins*60000){
      sessionStartedAt = Date.now();
      toast(t('session_reminder'));
      pushNotification(t('session_reminder'));
      renderNotifBadge();
    }
  }, 60000);
  document.addEventListener('visibilitychange', function(){
    // A long absence starts a fresh session.
    if(document.visibilityState==='visible' && Date.now() - lastHidden > 10*60000) sessionStartedAt = Date.now();
    if(document.visibilityState==='hidden') lastHidden = Date.now();
  });
  let lastHidden = Date.now();

  /* ============ boot ============ */
  function withFocusPreserved(fn){
    const active = document.activeElement;
    const id = active && active.id;
    const isTextField = id && active.tagName==='INPUT';
    const selStart = isTextField ? active.selectionStart : null;
    const selEnd = isTextField ? active.selectionEnd : null;
    const phoneBody = document.getElementById('phoneBody');
    const sheetBody = document.querySelector('.sheet-body');
    const scrollTop = phoneBody ? phoneBody.scrollTop : 0;
    const sheetScrollTop = sheetBody ? sheetBody.scrollTop : 0;
    const sheetWas = document.getElementById('sheet').dataset.qid || null;
    fn();
    const newPhoneBody = document.getElementById('phoneBody');
    if(newPhoneBody) newPhoneBody.scrollTop = scrollTop;
    const newSheetBody = document.querySelector('.sheet-body');
    if(newSheetBody) newSheetBody.scrollTop = (sheetWas && sheetWas === state.openContest) ? sheetScrollTop : 0;
    if(id){
      const el = document.getElementById(id);
      if(el && el.tagName==='INPUT'){
        el.focus();
        if(selStart!==null && el.setSelectionRange){
          try{ el.setSelectionRange(selStart, selEnd); }catch(e){}
        }
      }
    }
  }
  function render(){ withFocusPreserved(function(){ renderPhone(); }); ensureSelfieCamera(); }

  // Onboarding (sign-in, OTP, 18+ and consent) is built but gated off until phone sign-in
  // ships (M2). Until then the app opens straight into a pseudonymous device account.
  // Set SHOW_ONBOARDING to true (e.g. for the packaged APK) once sign-in is live.
  const SHOW_ONBOARDING = false;
  async function start(){
    state = defaultState();
    if(!SHOW_ONBOARDING){ state.user = { signedIn:true, name:'', method:'device' }; state.phoneScreen = 'home'; }
    render();
    loadAppConfig();
    loadFeed();
    loadTicker();
    try { await ensureSession(); }
    catch(e){ state.meError = e; render(); return; }
    await loadMe();
    loadMyCalls();
  }
  start();
})();
