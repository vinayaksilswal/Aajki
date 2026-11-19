// Bharat Foreseez consumer app.
import { api, allOpenQuestions } from './api.js';

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

  /* ============ live data (Bharat Foreseez API) ============
     Questions and headlines come from the backend. There is no offline or sample content:
     while loading, or if the server can't be reached, the app says so. */
  const FEED_REFRESH_MS = 60000;
  const TICKER_REFRESH_MS = 300000;
  // Spec s.6: no sentiment breakdown is shown for a group smaller than this.
  const MIN_GROUP = 50;
  // Phase 1 ships status-only rewards; the server's /v1/app-config is the source of truth.
  const PHASE1_FLAGS = { prizes:false, plus:false, sponsored_polls:false, user_created_polls:false, spin_the_wheel:false };

  function toDef(q){
    const out = {}; (q.outcomes||[]).forEach(o=>{ out[o.key] = o; });
    return {
      id:q.id, category:q.category, title:q.title, desc:q.description||'',
      yes:(out.yes && out.yes.label) || 'Yes', no:(out.no && out.no.label) || 'No',
      closes: q.closes_at ? new Date(q.closes_at) : null,
      participants:q.participants||0, chanceHidden:!!q.chance_hidden,
      chance:{ yes: out.yes ? out.yes.chance : null, no: out.no ? out.no.chance : null },
      resolution:q.resolution||{}, context:q.context||null, status:q.status
    };
  }
  function applyQuestions(list){
    const defs = {};
    list.forEach(q=>{ if(CAT_MAP[q.category]) defs[q.id] = toDef(q); });
    state.questionDefs = defs;
    state.contests = Object.values(defs).map(d=>({ id:d.id, status: d.status==='settled' ? 'resolved' : 'open', resolvedOption:null }));
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
      const cfg = await api.appConfig();
      state.flags = Object.assign({}, PHASE1_FLAGS, cfg.flags || {});
      state.grievance = cfg.grievance_officer || null;
      render();
    } catch(e){ /* stay on the Phase 1 defaults */ }
  }

  // Winner Prizes: grand, non‑cash prizes awarded — never purchased or point‑redeemed —
  // to the top‑ranked players each period. Distinct from the everyday points
  // catalogue above; skews toward flagship devices and educational‑platform
  // subscriptions since students and university players are a core audience.
  const WINNER_PRIZES = [
    {id:'iphone', name:'iPhone 16', desc:'Latest‑generation flagship smartphone.', tag:'Electronics', tier:'Grand Prize — Rank 1, monthly', icon:'📱'},
    {id:'ipad', name:'iPad (10th Gen), 128GB', desc:'Wi‑Fi model — for notes, research and reading.', tag:'Electronics', tier:'Grand Prize — Top 3, monthly', icon:'📱'},
    {id:'coursera-plus', name:'Coursera Plus — 1 Year', desc:'Unlimited access to 7,000+ courses and certificates.', tag:'Education', tier:'Top 10, monthly', icon:'🎓'},
    {id:'udemy-personal', name:'Udemy Personal Plan — 1 Year', desc:'Unlimited access to Udemy’s course library.', tag:'Education', tier:'Top 10, monthly', icon:'🎓'},
    {id:'linkedin-learning', name:'LinkedIn Learning — 1 Year', desc:'Professional and technical skills courses.', tag:'Education', tier:'Top 25, monthly', icon:'🎓'},
    {id:'duolingo-super', name:'Duolingo Super — 1 Year', desc:'Ad‑free, unlimited language learning.', tag:'Education', tier:'Top 25, monthly', icon:'🎓'}
  ];

  // Rank badges: named tiers derived from lifetime Foreseez Points balance.
  // Purely an identity/status layer on top of the same earn‑only balance that
  // already drives the ledger, wallet and leaderboard — gives every
  // player, not just the top of the leaderboard, a named badge to climb
  // toward as their points grow.
  const RANK_TIERS = [
    {min:0,     name:'Navodit',        emoji:'🌱', color:'#8a8f98'},
    {min:1000,  name:'Drishta',   emoji:'✅', color:'#1d9bf0'},
    {min:2500,  name:'Vishleshak',     emoji:'📊', color:'#1baf7a'},
    {min:4500,  name:'Top Voice',             emoji:'🌟', color:'#c98500'},
    {min:7000,  name:'Hall of Famer',         emoji:'🏆', color:'#b8860b'},
    {min:10000, name:"Mahadrishta", emoji:'👑', color:'linear-gradient(135deg,#FF9933,#b8860b)'}
  ];
  function rankTierFor(pts){
    let tier = RANK_TIERS[0];
    for(const t of RANK_TIERS){ if(pts >= t.min) tier = t; }
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
      ledger:[],
      contests: [], questionDefs: {}, feedStatus:'idle', feedError:null,
      predictions:{},
      checkedIn:false,
      catFilter:'all',
      feed:[],
      comments:{},
      notifications:[],
      activity:[],
      searchQuery:'',
      sortMode:'closing',
      notifPanelOpen:false,
      plus:false,
      plusTier:null,
      callsDay:null, callsToday:0,
      customPolls:[],
      creatingPoll:false,
      openCampaign:null,
      _pollDraft:null,
      showRaw:false,
      newsFeed: [], newsAttribution:'',
      flags: Object.assign({}, PHASE1_FLAGS), grievance:null,
      _commentMedia:null, _commentConsent:false, _voiceRecording:false, _voiceElapsed:0
    };
  }
  let state = defaultState();

  function contestDef(id){ return (state.questionDefs||{})[id] || (state.customPolls||[]).find(c=>c.id===id); }
  // Daily call limits by plan: free 10, Plus 25, Plus Pro unlimited.
  const DAILY_CALL_LIMITS = { free:10, plus:25, pro:Infinity };
  function dailyCallCap(){ return state.plusTier==='pro' ? DAILY_CALL_LIMITS.pro : (state.plus ? DAILY_CALL_LIMITS.plus : DAILY_CALL_LIMITS.free); }
  function rollCallDay(){ const k = liveNow().toDateString(); if(state.callsDay!==k){ state.callsDay=k; state.callsToday=0; } }
  function callsLeftToday(){ rollCallDay(); return Math.max(0, dailyCallCap() - state.callsToday); }
  function balance(){ return state.ledger.length ? state.ledger[state.ledger.length-1].balanceAfter : 0; }
  // Spec s.6: rank follows lifetime points earned, so committing points never lowers it.
  function lifetimeEarned(){ return state.ledger.reduce((s,e)=>s + (e.amount > 0 ? e.amount : 0), 0); }
  function addLedger(type,label,amount,contestId){
    const bal = balance() + amount;
    state.ledger.push({ id:'lg'+state.ledger.length+'-'+Date.now(), type, label, amount, balanceAfter:bal, contestId:contestId||null, ts:timeNow() });
    return bal;
  }

  /* ============ comments / activity / notifications ============ */
  function ensureComments(contestId){ return state.comments[contestId] || (state.comments[contestId] = []); }

  /* ============ debate attachments: photo / video / voice note ============
     PROTOTYPE NOTE: this demo enforces "no explicit or graphic content" via
     a required self-certification checkbox plus community reporting (below).
     A production build MUST also run every photo/video/voice upload through
     a server-side automated moderation pipeline (e.g. image/video SafeSearch
     classifiers, transcription + text moderation for voice notes) before it
     becomes visible to anyone else, backed by a human review queue for
     reports — that step cannot be done safely in client-side JS alone, so
     nothing here should be mistaken for real moderation. */
  const MAX_PHOTO_BYTES = 8*1024*1024;
  const MAX_VIDEO_BYTES = 40*1024*1024;
  const MAX_VIDEO_SECONDS = 20;
  const MAX_VOICE_SECONDS = 60;
  let voiceStream = null, voiceRecorder = null, voiceChunks = [], voiceRecTimer = null;

  function formatDur(sec){
    sec = Math.max(0, Math.round(sec||0));
    const m = Math.floor(sec/60), s = sec%60;
    return m+':'+(s<10?'0':'')+s;
  }
  function renderCommentMedia(cm){
    if(!cm.media) return '';
    if(cm.media.reported) return '<div class="comment-media reported">Media hidden &mdash; reported for moderator review</div>';
    const m = cm.media;
    if(m.type==='photo') return '<div class="comment-media"><img src="'+m.dataUrl+'" alt="Attached photo"></div>';
    if(m.type==='video') return '<div class="comment-media"><video src="'+m.dataUrl+'" controls playsinline muted></video></div>';
    if(m.type==='voice') return '<div class="comment-media voice"><audio src="'+m.dataUrl+'" controls></audio><span class="dur">Voice note &middot; '+formatDur(m.duration)+'</span></div>';
    return '';
  }
  function renderCommentForm(){
    const media = state._commentMedia;
    const recording = state._voiceRecording;
    // Note: typing in #commentInput deliberately doesn't trigger a re-render
    // (it would steal focus/cursor position), so the Post button here is
    // only gated on the media-consent requirement, not on text presence —
    // an empty, media-less submit is already a silent no-op in postComment.
    const postBlocked = !!(media && !state._commentConsent);
    let html = '<div class="comment-form"><input id="commentInput" type="text" maxlength="140" placeholder="Add to the debate…" value="'+esc(state._commentDraft||'')+'">'
      + '<button class="btn btn-sm" id="btnPostComment" '+(postBlocked?'disabled':'')+'>Post</button></div>';

    html += '<p class="media-policy">Back up your view with a photo, a short video (&le;'+MAX_VIDEO_SECONDS+'s) or a voice note (&le;'+MAX_VOICE_SECONDS+'s). Keep it real &mdash; <strong>no explicit or graphic content</strong>. Reported media is hidden pending review.</p>';

    html += '<div class="attach-row">'
      + '<button class="attach-btn" id="btnAttachPhoto" type="button" '+((media||recording)?'disabled':'')+'>'+svgIcon('camera')+' Photo</button>'
      + '<button class="attach-btn" id="btnAttachVideo" type="button" '+((media||recording)?'disabled':'')+'>'+svgIcon('video')+' Video</button>'
      + '<button class="attach-btn '+(recording?'rec':'')+'" id="btnRecordVoice" type="button" '+((media&&!recording)?'disabled':'')+'>'
        + (recording ? '<span class="rec-dot"></span> Stop &middot; '+formatDur(state._voiceElapsed||0) : svgIcon('mic')+' Voice')
        + '</button>'
      + '<input type="file" id="commentPhotoInput" accept="image/*" hidden>'
      + '<input type="file" id="commentVideoInput" accept="video/*" hidden>'
      + '</div>';

    if(media){
      const label = media.type==='photo' ? 'Photo attached'
        : media.type==='video' ? 'Video attached &middot; '+formatDur(media.duration)
        : 'Voice note &middot; '+formatDur(media.duration);
      const thumb = media.type==='photo' ? '<img class="thumb" src="'+media.dataUrl+'">' : '<div class="thumb"></div>';
      html += '<div class="media-pending">'+thumb+'<div class="meta"><b>'+label+'</b>Ready to post</div><button class="rm" id="btnRemoveCommentMedia" type="button">&times;</button></div>';
      html += '<label class="media-consent"><input type="checkbox" id="chkMediaConsent" '+(state._commentConsent?'checked':'')+'> This doesn&rsquo;t contain explicit or graphic content, and I have the right to share it.</label>';
    }
    return html;
  }
  function attachCommentMedia(media){
    state._commentMedia = media;
    state._commentConsent = false;
    render();
  }
  function resetVoiceRecordingState(){
    state._voiceRecording = false;
    state._voiceElapsed = 0;
    if(voiceRecTimer){ clearInterval(voiceRecTimer); voiceRecTimer = null; }
  }
  function startVoiceRecording(){
    if(state._commentMedia || state._voiceRecording) return;
    if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
      toast('Microphone isn’t available in this browser'); return;
    }
    navigator.mediaDevices.getUserMedia({ audio:true }).then(function(stream){
      voiceStream = stream;
      voiceChunks = [];
      try{ voiceRecorder = new MediaRecorder(stream); }
      catch(err){
        stream.getTracks().forEach(function(t){ t.stop(); });
        toast('Voice recording isn’t supported in this browser'); return;
      }
      voiceRecorder.ondataavailable = function(e){ if(e.data && e.data.size>0) voiceChunks.push(e.data); };
      voiceRecorder.onstop = function(){
        voiceStream.getTracks().forEach(function(t){ t.stop(); });
        voiceStream = null;
        const blob = new Blob(voiceChunks, { type: voiceRecorder.mimeType||'audio/webm' });
        const durationSec = state._voiceElapsed;
        const reader = new FileReader();
        reader.onload = function(){
          resetVoiceRecordingState();
          attachCommentMedia({ type:'voice', dataUrl: reader.result, duration: durationSec });
        };
        reader.readAsDataURL(blob);
      };
      voiceRecorder.start();
      state._voiceRecording = true;
      state._voiceElapsed = 0;
      render();
      voiceRecTimer = setInterval(function(){
        state._voiceElapsed++;
        if(state._voiceElapsed >= MAX_VOICE_SECONDS){ stopVoiceRecording(); }
        else { render(); }
      }, 1000);
    }).catch(function(){
      toast('Microphone access was blocked — allow it to record a voice note');
    });
  }
  function stopVoiceRecording(){
    if(voiceRecorder && state._voiceRecording){ voiceRecorder.stop(); }
    else { resetVoiceRecordingState(); render(); }
  }
  function handleCommentFile(kind, file){
    if(!file) return;
    if(kind==='photo'){
      if(!file.type.startsWith('image/')){ toast('Please choose an image file'); return; }
      if(file.size > MAX_PHOTO_BYTES){ toast('Photos must be under 8MB'); return; }
      const reader = new FileReader();
      reader.onload = function(){ attachCommentMedia({ type:'photo', dataUrl: reader.result }); };
      reader.readAsDataURL(file);
    } else if(kind==='video'){
      if(!file.type.startsWith('video/')){ toast('Please choose a video file'); return; }
      if(file.size > MAX_VIDEO_BYTES){ toast('Videos must be under 40MB'); return; }
      const url = URL.createObjectURL(file);
      const probe = document.createElement('video');
      probe.preload = 'metadata';
      let settled = false;
      // Safety net: on an unusual device/codec combo where the browser never
      // fires loadedmetadata *or* error (rather than firing error promptly,
      // as most unsupported-format cases do), don't leave the user with a
      // picker that silently did nothing.
      const giveUpTimer = setTimeout(function(){
        if(settled) return;
        settled = true;
        URL.revokeObjectURL(url);
        toast('That video took too long to read — try a shorter clip or a different format');
      }, 8000);
      probe.onloadedmetadata = function(){
        if(settled) return;
        settled = true;
        clearTimeout(giveUpTimer);
        const dur = probe.duration;
        URL.revokeObjectURL(url);
        if(dur > MAX_VIDEO_SECONDS){ toast('Videos must be '+MAX_VIDEO_SECONDS+' seconds or shorter'); return; }
        const reader = new FileReader();
        reader.onload = function(){ attachCommentMedia({ type:'video', dataUrl: reader.result, duration: dur }); };
        reader.readAsDataURL(file);
      };
      probe.onerror = function(){
        if(settled) return;
        settled = true;
        clearTimeout(giveUpTimer);
        URL.revokeObjectURL(url);
        toast('Couldn’t read that video — try a different clip or format');
      };
      probe.src = url;
    }
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
      const total = c.pool.yes + c.pool.no;
      const yesPct = Math.round((c.pool.yes/total)*100), noPct = 100-yesPct;
      const withPct = state._hookChoice==='yes' ? yesPct : noPct;
      return '<div class="ob">'
        +'<div class="ob-logo"><div class="ring" style="font-size:34px;">✨</div><h1>Nice pick!</h1><p>You’re with <strong>'+withPct+'%</strong> of players on &ldquo;'+esc(def.title)+'&rdquo;.</p></div>'
        +'<div class="callout"><strong>+30 pts</strong> &mdash; first forecast reward, already credited to your wallet.</div>'
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

  // Shown right on Home so a prize catalogue is the first thing a player sees
  // after signing in — the "what could I win" hook, before any topic list.
  function renderHomePrizeStrip(){
    if(!state.flags.prizes) return '';
    const cards = WINNER_PRIZES.map(p=>
      '<div class="hp-card"><span class="ic">'+p.icon+'</span><b>'+esc(p.name)+'</b><span class="tier">'+esc(p.tier)+'</span></div>'
    ).join('');
    return '<div class="home-prizes"><div class="hd"><h3>Prizes to be won</h3><button data-nav="wallet" style="border:0; background:none; padding:0; font-size:11px; font-weight:700; color:var(--brand); cursor:pointer;">See all &rarr;</button></div>'
      + '<div class="hp-scroll">'+cards+'</div></div>';
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
    else if(!state.contests.length) cards = '<div class="feed-state"><b>No open questions right now.</b><span>New questions are added through the day &mdash; check back soon.</span></div>';
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
      + '<button data-filter="all" class="'+(state.catFilter==='all'?'active':'')+'">All</button>'
      + CATS.map(c=>'<button data-filter="'+c.key+'" class="'+(state.catFilter===c.key?'active':'')+'"><span class="cat-dot" style="background:'+c.color+';"></span>'+c.label+'</button>').join('')
      + '</div>';

    const openCount = state.contests.filter(c=>c.status==='open').length;
    const sub = feedReady() ? openCount+' question'+(openCount===1?'':'s')+' open &middot; '+formatDateLong(liveNow()) : formatDateLong(liveNow());
    return '<div class="greet"><div><h2>Namaste, '+esc(state.user.name)+(state.selfieVerified?' '+verifiedBadgeIcon():'')+' '+rankBadgeChip(lifetimeEarned())+(state.flags.plus && state.plus?' <span class="plus-badge">'+(state.plusTier==='pro'?'Plus Pro':'Plus')+'</span>':'')+'</h2><div class="sub">'+sub+'</div></div></div>'
      + '<div class="balance-card"><div class="k">Foreseez Points</div><div class="v mono">'+fmtNum(balance())+'</div></div>'
      + renderHomePrizeStrip()
      + renderNewsTicker()
      + '<div class="search-row"><input id="searchInput" type="search" placeholder="Search questions…" aria-label="Search questions" value="'+esc(state.searchQuery||'')+'">'
      + '<div class="sort-toggle"><button data-sort="closing" class="'+(state.sortMode==='closing'?'active':'')+'">Closing soon</button><button data-sort="trending" class="'+(state.sortMode==='trending'?'active':'')+'">Trending</button></div></div>'
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

  // Pulse: the product's actual differentiator made visible on-screen. Every
  // open contest already carries a live pool.yes/pool.no split — this screen
  // does nothing but aggregate that same real data up to category level and
  // surface it as a first-class destination, instead of leaving it implicit
  // inside individual contest cards. Framed explicitly as "not a market" so
  // it reads as a data/insights product, not a Kalshi/Polymarket clone.
  function pulseStats(){
    const open = state.contests.filter(c=>c.status==='open').map(c=>contestDef(c.id)).filter(Boolean);
    const byCat = {};
    CATS.forEach(cat=>{ byCat[cat.key] = { count:0, calls:0, leanSum:0, leanN:0 }; });
    let totalCalls = 0;
    const ranked = [];
    open.forEach(def=>{
      const b = byCat[def.category];
      if(!b) return;
      b.count += 1; b.calls += def.participants; totalCalls += def.participants;
      const p = chancePct(def, 'yes');
      if(p!==null && !def.chanceHidden && def.participants >= MIN_GROUP){
        const lean = Math.max(p, 100-p);
        b.leanSum += lean*def.participants; b.leanN += def.participants;
        ranked.push({ id:def.id, def, conf:lean, total:def.participants });
      }
    });
    return { open, byCat, totalCalls, ranked };
  }
  function renderPulse(){
    const head = '<div class="dash-head"><div><h2 style="font-size:19px;">Pulse &mdash; what India foresees</h2>'
      + '<p>Aggregated across every open question. No money, no trading &mdash; this is what the crowd believes, captured before the answer is known.</p></div>'
      + '<span class="live-label"><span class="live-dot"></span>Live</span></div>';
    if(!feedReady()) return head + feedStateHtml();
    const { open, byCat, totalCalls, ranked } = pulseStats();
    const activeCats = CATS.filter(cat => byCat[cat.key].count);
    const tiles = activeCats.map(cat=>{
      const b = byCat[cat.key];
      const enough = b.calls >= MIN_GROUP && b.leanN > 0;
      return '<div class="tile callout" style="border-color:color-mix(in srgb, '+cat.color+' 35%, var(--border));">'
        + '<div class="top"><span class="cat-dot" style="background:'+cat.color+';"></span>'+cat.label+'</div>'
        + (enough
            ? '<div class="val">'+Math.round(b.leanSum/b.leanN)+'%</div><div class="delta" style="color:var(--ink-muted); font-weight:600;">average lean to the larger side</div>'
            : '<div class="val" style="font-size:15px;">Gathering calls</div><div class="delta" style="color:var(--ink-muted); font-weight:600;">Shown once '+MIN_GROUP+'+ calls are in</div>')
        + '<div class="hint" style="margin-top:6px;">'+b.count+' open question'+(b.count===1?'':'s')+' &middot; '+callsText(b.calls)+'</div>'
        + '</div>';
    }).join('');
    function insightRow(r){
      const cat = CAT_MAP[r.def.category];
      return '<div class="feed-row" data-open-contest="'+esc(r.id)+'" role="button" tabindex="0" style="cursor:pointer;">'
        + '<span class="who"><span class="cat-dot" style="background:'+cat.color+'; margin-right:6px;"></span>'+esc(r.def.title)+'</span>'
        + '<span class="meta">'+r.conf+'% lean &middot; '+callsText(r.total)+'</span></div>';
    }
    const decisive = ranked.slice().sort((a,b)=>b.conf-a.conf).slice(0,3);
    const contested = ranked.slice().sort((a,b)=>a.conf-b.conf).slice(0,3);
    const thin = '<p class="hint">Appears once a question has '+MIN_GROUP+'+ calls.</p>';
    return head
      + '<div class="callout" style="margin-bottom:16px;"><strong>'+callsText(totalCalls)+'</strong> across <strong>'+open.length+' open question'+(open.length===1?'':'s')+'</strong> in '+activeCats.length+' categor'+(activeCats.length===1?'y':'ies')+'. Readings appear only for groups of '+MIN_GROUP+' or more, so no individual call can be singled out.</div>'
      + (tiles ? '<div class="tiles">'+tiles+'</div>' : '<p class="hint">No open questions right now.</p>')
      + '<div class="chart-card callout"><h3 style="margin-bottom:2px;">Most decisive</h3><p class="hint" style="margin-bottom:8px;">Where the crowd is most confident.</p>'
      + (decisive.map(insightRow).join('') || thin) + '</div>'
      + '<div class="chart-card callout"><h3 style="margin-bottom:2px;">Most contested</h3><p class="hint" style="margin-bottom:8px;">Where the crowd is split down the middle.</p>'
      + (contested.map(insightRow).join('') || thin) + '</div>';
  }

  function renderContestSheet(id){
    const def = contestDef(id);
    if(!def) return { title:'Question', body:'<p class="hint">This question is no longer available.</p>' };
    const c = state.contests.find(x=>x.id===id) || { status:'open' };
    const cat = CAT_MAP[def.category];
    const yesPct = chancePct(def, 'yes');
    const noPct = yesPct===null ? null : 100 - yesPct;
    const mine = state.predictions[id];
    const sel = state._sheetSel || (mine ? mine.option : null);
    const amt = (state._sheetStake===undefined || state._sheetStake===null) ? 50 : state._sheetStake;
    const isOpen = c.status==='open' && def.status==='open' && def.closes && def.closes > liveNow();
    const res = def.resolution || {};

    let body = '<span class="chip" style="background:color-mix(in srgb, '+cat.color+' 16%, transparent); color:'+cat.color+'; margin-bottom:8px;"><span class="chip-dot"></span>'+cat.label+'</span>'
      + '<h3 style="font-size:15.5px; margin-top:4px;">'+esc(def.title)+'</h3>'
      + (def.desc ? '<p style="font-size:12.5px; color:var(--ink-2); line-height:1.55;">'+esc(def.desc)+'</p>' : '')
      + (def.context && def.context.link ? '<p class="hint">Context: <a href="'+esc(def.context.link)+'" target="_blank" rel="noopener noreferrer">'+esc(def.context.headline)+'</a></p>' : '')
      + chanceBlock(def)
      + '<div class="meta" style="margin-top:4px; display:flex; justify-content:space-between;"><span>'+closesText(def)+'</span><span class="vol">'+callsText(def.participants)+'</span></div>'
      + '<div class="resolve-box"><h4>How this resolves</h4><p>'+esc(res.rule || '')+'</p>'
      + (res.source_url ? '<a href="'+esc(res.source_url)+'" target="_blank" rel="noopener noreferrer">Official source &rarr;</a>' : '')
      + '</div>';

    if(!isOpen){
      body += '<div class="callout" style="margin-top:10px;">'+(def.status==='paused'
        ? 'Calls are paused on this question for now.'
        : 'This question has closed. The result will be confirmed from the official source above.')+'</div>';
    } else {
      body += '<div class="opt-grid" style="margin-top:12px;">'
        + optBtn('yes', def.yes, yesPct, sel, mine)
        + optBtn('no', def.no, noPct, sel, mine)
        + '</div>';
      if(mine){
        body += '<div class="callout">You committed <strong>'+fmtNum(mine.staked)+' pts</strong> to &ldquo;'+esc(mine.option==='yes'?def.yes:def.no)+'&rdquo;. Awaiting the result.</div>';
      } else {
        const limitHint = callsLeftToday()+' of '+dailyCallCap()+' daily calls left';
        body += '<div class="field" style="margin-top:6px;"><label for="stakeInput">Points to commit</label><input class="mono" id="stakeInput" type="number" inputmode="numeric" min="10" max="'+balance()+'" value="'+esc(amt)+'"></div>'
          + '<div class="chip-row">'
          + [25,50,100,250].map(v=>'<button data-chip="'+v+'">'+v+'</button>').join('')
          + '<button data-chip="max">Max</button></div>'
          + '<button class="btn btn-primary btn-block" id="btnPlacePrediction" '+(sel&&callsLeftToday()>0?'':'disabled')+'>Make your call</button>'
          + '<p class="hint" style="margin:8px 0 0; text-align:center;">'+limitHint+'</p>'
          + '<p class="news-note" style="margin-top:8px; text-align:center;">Preview: calls stay on this device and don&rsquo;t count toward the public chance until sign-in launches.</p>';
      }
    }
    body += '<div class="discuss"><h4>Debate</h4><p class="hint" style="margin:0;">Comments, replies and voice notes open with sign-in. Every post is checked before it appears.</p></div>';
    return { title: def.title, body };
  }
  function optBtn(key,label,pct,sel,mine){
    const disabled = !!mine;
    return '<button class="opt-btn '+key+' '+(sel===key?'sel':'')+'" data-opt="'+key+'" '+(disabled?'disabled style="opacity:.6;"':'')+'>'
      + '<span class="lbl">'+esc(label)+'</span><span class="chance-val">'+(pct===null?'&mdash;':pct+'%')+'</span>'
      + '<span style="font-size:10px; color:var(--ink-muted); font-weight:600;">current chance</span></button>';
  }

  /* ============ ledger / leaderboard / wallet / profile ============ */
  const LEDGER_META = {
    signup:{label:'Signup reward', color:'good'}, kyc:{label:'Verification reward', color:'good'},
    checkin:{label:'Daily check‑in', color:'good'}, stake:{label:'Points committed', color:'muted'},
    win:{label:'Call correct', color:'good'}, lose:{label:'Call resolved', color:'muted'}
  };
  function ledgerIcon(type){
    const good = type==='win'||type==='signup'||type==='kyc'||type==='checkin';
    const bg = good ? 'color-mix(in srgb, var(--status-good) 18%, transparent)' : 'var(--surface-3)';
    const fg = good ? 'var(--status-good)' : 'var(--ink-muted)';
    const glyph = type==='stake' ? '&#8722;' : good ? '&#8593;' : '&#8226;';
    return '<div class="ico" style="background:'+bg+'; color:'+fg+'; font-weight:700; font-size:14px;">'+glyph+'</div>';
  }
  function renderLedger(){
    if(!state.ledger.length) return '<p class="hint" style="margin-top:16px;">No activity yet.</p>';
    const rows = state.ledger.slice().reverse().map(e=>{
      const sign = e.amount>0 ? '+' : e.amount<0 ? '−' : '';
      return '<div class="ledger-row">'+ledgerIcon(e.type)
        + '<div class="txt"><b>'+esc(e.label)+'</b><span>'+e.ts+'</span></div>'
        + '<div class="amt" style="color:'+(e.amount>0?'var(--status-good)':e.amount<0?'var(--ink)':'var(--ink-muted)')+';">'+sign+(e.amount?fmtNum(Math.abs(e.amount)):'0')+'<small>bal '+fmtNum(e.balanceAfter)+'</small></div></div>';
    }).join('');
    return '<h2 style="font-size:16px; margin:14px 0 4px;">Points ledger</h2><p class="hint">Append‑only. Every earn, commitment and reward is a permanent event.</p><div class="card" style="padding:2px 14px; margin-top:8px;">'+rows+'</div>';
  }

  function renderLeaderboard(){
    return '<h2 style="font-size:16px; margin:14px 0 4px;">Leaderboards</h2>'
      + '<p class="hint" style="margin-bottom:10px;">Daily, weekly and all-time rankings by lifetime points earned &mdash; committing points to a call never lowers your rank.</p>'
      + renderRankCard()
      + '<div class="feed-state"><b>Rankings open with sign-in.</b><span>Once calls are recorded, you&rsquo;ll see where you stand against everyone forecasting on Bharat Foreseez.</span></div>';
  }
  function renderWallet(){
    let html = '<h2 style="font-size:16px; margin:14px 0 4px;">Wallet</h2>'
      + '<div class="balance-card" style="margin-top:8px;"><div class="k">Balance</div><div class="v mono">'+fmtNum(balance())+' pts</div></div>'
      + '<div class="callout" style="margin-bottom:12px;"><strong>Foreseez Points are earned, never sold.</strong> They have no cash value and can&rsquo;t be bought, withdrawn or transferred. They are used only to make calls.</div>'
      + '<div class="earn-item"><div><b>Daily check&#8209;in</b><span>A fixed reward, once a day</span></div><button class="btn btn-sm" id="btnCheckin" '+(state.checkedIn?'disabled':'')+'>'+(state.checkedIn?'Done':'+50 pts')+'</button></div>'
      + '<div class="earn-item"><div><b>Age &amp; identity confirmed</b><span>One-time verification reward</span></div><span class="chip chip-status-good">Earned</span></div>';
    if(state.flags.plus) html += renderPlusCards();
    if(state.flags.user_created_polls) html += renderMyPolls();
    if(state.flags.prizes) html += renderWinnerPrizes();
    return html;
  }
  // Phase 2 (behind flags, off in Phase 1): Plus access tiers and partner prizes.
  function renderPlusCards(){
    return '<div class="plus-card"><div class="hd"><b style="font-size:13.5px;">Foreseez Plus</b>'+(state.plusTier==='plus'?'<span class="plus-badge">Active</span>':'')+'</div>'
      + '<p>A flat monthly access fee. Unlocks an ad&#8209;free feed, a profile badge, a higher daily limit (25 calls instead of 10) and deeper accuracy statistics. It never buys or credits points.</p>'
      + (state.plusTier ? '<button class="btn btn-sm" disabled>Subscribed</button>' : '<button class="btn btn-primary btn-sm" id="btnSubscribePlus">Subscribe to Plus</button>')
      + '</div>';
  }
  function renderWinnerPrizes(){
    const cards = WINNER_PRIZES.map(p=>'<div class="winner-card"><span class="ic">'+p.icon+'</span><span class="tag">'+esc(p.tag)+'</span><b>'+esc(p.name)+'</b><span class="hint">'+esc(p.desc)+'</span><span class="tier">'+esc(p.tier)+'</span></div>').join('');
    return '<h3 style="font-size:13px; margin:18px 0 8px;">Partner prizes &mdash; top players</h3><div class="winner-grid" style="margin-bottom:18px;">'+cards+'</div>';
  }
  // Rank card: a screenshot-worthy summary of the player's current named
  // badge, built specifically so a proud "Mahadrishta" or "Hall of
  // Famer" has something worth sharing outside the app, not just a number
  // buried in a leaderboard row.
  function renderRankCard(){
    const pts = lifetimeEarned();
    const tier = rankTierFor(pts);
    const next = RANK_TIERS.find(t => t.min > pts);
    return '<div class="rank-card" style="background:'+tier.color+';">'
      + '<div class="rank-card-top"><span class="rank-emoji">'+tier.emoji+'</span><span>'+esc(tier.name)+'</span></div>'
      + '<div class="rank-card-pts">'+fmtNum(pts)+' pts</div>'
      + (next ? '<div class="rank-card-next">'+fmtNum(next.min-pts)+' pts to '+esc(next.name)+'</div>' : '<div class="rank-card-next">Highest rank achieved</div>')
      + '<button class="btn btn-sm" id="btnShareRank" style="margin-top:12px; background:rgba(255,255,255,.22); color:#fff; border-color:rgba(255,255,255,.45);">Share my rank</button>'
      + '</div>';
  }
  function renderProfile(){
    return '<h2 style="font-size:16px; margin:14px 0 4px;">Profile</h2>'
      + renderRankCard()
      + '<div class="card" style="padding:14px 16px; display:flex; flex-direction:column; gap:10px;">'
      + '<div class="kyc-row"><div class="ico">'+svgIcon('user')+'</div><div class="txt"><b>'+esc(state.user.name)+(state.selfieVerified?' '+verifiedBadgeIcon():'')+(state.plus?' <span class="plus-badge" style="margin-left:4px;">'+(state.plusTier==='pro'?'Plus Pro':'Plus')+'</span>':'')+'</b><span>Signed in via '+esc(state.user.method)+'</span></div></div>'
      + '<div class="kyc-row"><div class="ico">'+checkIcon()+'</div><div class="txt"><b>Age &amp; consent confirmed</b><span>18+ declared and Terms &amp; Privacy consent given at sign&#8209;up</span></div></div>'
      + '<div class="kyc-row"><div class="ico">'+(state.phoneVerified?checkIcon():svgIcon('user'))+'</div><div class="txt"><b>Phone verified</b><span>Confirmed by OTP at sign&#8209;up</span></div></div>'
      + '<div class="kyc-row" style="align-items:center;"><div class="ico">'+(state.selfieVerified?checkIcon():svgIcon('user'))+'</div><div class="txt"><b>'+(state.selfieVerified?'Selfie verified':'Selfie not verified yet')+'</b><span>'+(state.selfieVerified?'Your blue Verified badge is active':'Confirm you’re a real person to earn your Verified badge')+'</span></div>'+(state.selfieVerified?'':'<button class="btn btn-sm" id="btnOpenSelfieSheet" style="flex:none; margin-left:8px;">Get Verified</button>')+'</div>'
      + '</div>'
      + renderGrievanceCard()
      + '<button class="btn btn-block" id="btnReset" style="margin-top:16px;">Reset preview data</button>'
      + '<p class="hint" style="text-align:center; margin-top:8px;">Clears calls and points kept on this device.</p>';
  }
  function renderGrievanceCard(){
    const g = state.grievance || {};
    const rows = [g.name && '<b>'+esc(g.name)+'</b>',
                  g.email && '<a href="mailto:'+esc(g.email)+'">'+esc(g.email)+'</a>',
                  g.phone && '<span>'+esc(g.phone)+'</span>',
                  g.address && '<span class="hint">'+esc(g.address)+'</span>'].filter(Boolean);
    return '<div class="card grievance"><span class="k">Help &amp; grievances</span>'
      + '<span>Raise a concern with our Grievance Officer'+(rows.length ? ':' : '.')+'</span>'
      + (rows.length ? rows.join('') : '<span class="hint">Contact details are being finalised.</span>')
      + '</div>';
  }

  /* ============ phone render / router ============ */
  function renderPhoneNav(){
    if(!state.user.signedIn){ document.getElementById('phoneNav').innerHTML=''; return; }
    const tabs = [['home','Home'],['pulse','Pulse'],['ledger','Ledger'],['leaderboard','Ranks'],['wallet','Wallet'],['profile','Profile']];
    const iconFor = {home:'home',pulse:'pulse',ledger:'ledger',leaderboard:'board',wallet:'wallet',profile:'user'};
    document.getElementById('phoneNav').innerHTML = tabs.map(([key,label])=>
      '<button data-nav="'+key+'" class="'+(state.phoneScreen===key?'active':'')+'">'+svgIcon(iconFor[key])+label+'</button>'
    ).join('');
  }
  function renderPhoneBody(){
    let html='';
    if(!state.user.signedIn) html = renderOnboarding();
    else if(state.phoneScreen==='home') html = renderHome();
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
      : '<p class="hint">No notifications yet &mdash; updates on questions you&rsquo;ve called will show up here.</p>';
    return '<div class="sheet-head"><h3 style="font-size:14px;">Notifications</h3><button class="btn btn-ghost btn-sm" id="btnCloseSheet" aria-label="Close">&#10005;</button></div><div class="sheet-body">'+rows+'</div>';
  }

  // Plus-subscriber poll creation: the second half of "capture more sentiment
  // data, not just run another prediction market" — a subscriber asks their
  // own Yes/No question, it runs in the live feed exactly like every seeded
  // topic, and every response feeds the same pool.yes/pool.no mechanic that
  // powers Pulse. No points are spent or charged to publish one.
  function renderCreatePollSheet(){
    const d = state._pollDraft || (state._pollDraft = {title:'', yes:'Yes', no:'No', hrs:72});
    const titleOk = (d.title||'').trim().length >= 4;
    const durations = [[24,'1 day'],[72,'3 days'],[168,'7 days']];
    return '<div class="sheet-head"><h3 style="font-size:14px;">Create a poll</h3><button class="btn btn-ghost btn-sm" id="btnCloseSheet" aria-label="Close">&#10005;</button></div>'
      + '<div class="sheet-body">'
      + '<p class="hint" style="margin-bottom:10px;">Ask consumers a real Yes/No question. It runs in the live feed like every other topic, and every response adds to the same real‑time sentiment pool &mdash; the data product described in the pitch.</p>'
      + '<div class="field"><label for="pollTitleInput">Question</label><input id="pollTitleInput" maxlength="120" placeholder="e.g. Will you try our new flavour this month?" value="'+esc(d.title)+'"></div>'
      + '<div class="field" style="display:flex; gap:8px;"><div style="flex:1; display:flex; flex-direction:column; gap:6px;"><label for="pollYesInput">&ldquo;Yes&rdquo; label</label><input id="pollYesInput" maxlength="24" value="'+esc(d.yes)+'"></div>'
      + '<div style="flex:1; display:flex; flex-direction:column; gap:6px;"><label for="pollNoInput">&ldquo;No&rdquo; label</label><input id="pollNoInput" maxlength="24" value="'+esc(d.no)+'"></div></div>'
      + '<div class="field"><label>Runs for</label><div class="chip-row">'
      + durations.map(([h,l])=>'<button data-poll-hrs="'+h+'" class="'+(d.hrs===h?'active':'')+'">'+l+'</button>').join('')
      + '</div></div>'
      + '<button class="btn btn-primary btn-block" id="btnPublishPoll" '+(titleOk?'':'disabled')+' style="margin-top:8px;">Publish to the live feed</button>'
      + '<p class="hint" style="margin-top:8px;">Lands in the Community Polls category, visible to every player. No points are spent or charged to run it.</p>'
      + '</div>';
  }
  function renderMyPolls(){
    const mine = (state.customPolls||[]).filter(p=>p.creator===state.user.name);
    if(!mine.length) return '';
    const rows = mine.map(p=>{
      const c = state.contests.find(x=>x.id===p.id);
      const total = c ? c.pool.yes + c.pool.no : 0;
      const yesPct = total ? Math.round(c.pool.yes/total*100) : 50;
      return '<div class="my-poll-row" data-open-contest="'+p.id+'" style="cursor:pointer;"><b>'+esc(p.title)+'</b><span class="hint">'+yesPct+'% &ldquo;'+esc(p.yes)+'&rdquo; &middot; '+fmtNum(total)+' pts reflected'+(c&&c.status==='resolved'?' &middot; resolved':'')+'</span></div>';
    }).join('');
    return '<h3 style="font-size:13px; margin:18px 0 8px;">Your polls</h3><div class="card" style="padding:2px 14px; margin-bottom:14px;">'+rows+'</div>';
  }
  function renderSheet(){
    const backdrop = document.getElementById('sheetBackdrop'), sheet = document.getElementById('sheet');
    if(state.notifPanelOpen){
      sheet.innerHTML = renderNotifPanel();
      backdrop.classList.add('open'); sheet.classList.add('open');
      return;
    }
    if(state.creatingPoll){
      sheet.innerHTML = renderCreatePollSheet();
      backdrop.classList.add('open'); sheet.classList.add('open');
      return;
    }
    if(state.selfieSheetOpen){
      sheet.innerHTML = renderSelfieSheet();
      backdrop.classList.add('open'); sheet.classList.add('open');
      return;
    }
    if(!state.openContest){ backdrop.classList.remove('open'); sheet.classList.remove('open'); sheet.innerHTML=''; return; }
    const {title, body} = renderContestSheet(state.openContest);
    sheet.innerHTML = '<div class="sheet-head"><h3 style="font-size:14px; max-width:80%;">Your call</h3><button class="btn btn-ghost btn-sm" id="btnCloseSheet" aria-label="Close">&#10005;</button></div><div class="sheet-body">'+body+'</div>';
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
        addLedger('kyc', 'Verified badge reward (selfie confirmed)', 100);
        if(state.obStep==='selfie'){ state.obStep = 'interests'; }
        else { state.selfieSheetOpen = false; }
        render(); toast('You’re Verified — +100 pts'); break;
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
        state.openContest = null; state.notifPanelOpen = false; state.creatingPoll = false;
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
        if(state._hookContestId){ addLedger('signup','First forecast reward', 30); }
        state._hookChoice = payload;
        render(); break;
      }
      case 'skipHook': { state.obStep='welcome'; render(); break; }
      case 'continueToWelcome': { state.obStep='welcome'; render(); break; }
      case 'enterApp': {
        state.user.signedIn = true;
        addLedger('signup','Welcome reward', 1000);
        addLedger('kyc','Verification reward', 150);
        state.catFilter = (state.interests && state.interests[0]) || 'all';
        state.phoneScreen='home';
        render(); toast('Welcome to Bharat Foreseez'); break;
      }
      case 'nav': { state.phoneScreen = payload; state._sheetSel=null; render(); break; }
      case 'filter': { state.catFilter = payload; render(); break; }
      case 'sort': { state.sortMode = payload; render(); break; }
      case 'openContest': { resetVoiceRecordingState(); state.openContest = payload; state.openCampaign=null; state._sheetSel=null; state._sheetStake=50; state._commentDraft=''; state._commentMedia=null; state._commentConsent=false; state.notifPanelOpen=false; state.creatingPoll=false; state.selfieSheetOpen=false; render(); break; }
      case 'openCampaign': { state.openCampaign = payload; state.openContest=null; state.notifPanelOpen=false; state.creatingPoll=false; state.selfieSheetOpen=false; render(); break; }
      case 'closeSheet': { state.openContest=null; state.openCampaign=null; state.notifPanelOpen=false; state.creatingPoll=false; state.selfieSheetOpen=false; render(); break; }
      case 'toggleBell': {
        state.openContest=null;
        state.creatingPoll=false;
        state.selfieSheetOpen=false;
        state.notifPanelOpen = true;
        state.notifications.forEach(n=>n.read=true);
        render(); break;
      }
      case 'openCreatePoll': {
        if(!state.plus){ toast('Subscribe to Foreseez Plus to create a poll'); return; }
        state._pollDraft = { title:'', yes:'Yes', no:'No', hrs:72 };
        state.openContest = null; state.notifPanelOpen = false; state.creatingPoll = true; state.selfieSheetOpen = false;
        render(); break;
      }
      case 'pollHrs': {
        if(!state._pollDraft) return;
        state._pollDraft.hrs = Number(payload);
        render(); break;
      }
      case 'publishPoll': {
        if(!state.plus){ toast('Subscribe to Foreseez Plus to create a poll'); return; }
        const d = state._pollDraft || {};
        const title = (d.title||'').trim();
        if(title.length < 4){ toast('Enter a question for your poll'); return; }
        const yesLabel = (d.yes||'').trim() || 'Yes';
        const noLabel = (d.no||'').trim() || 'No';
        const hrs = d.hrs || 72;
        const id = 'community-'+Date.now().toString(36)+Math.random().toString(36).slice(2,6);
        const seedYes = 8 + Math.floor(Math.random()*12), seedNo = 8 + Math.floor(Math.random()*12);
        const creatorName = state.user.name || 'A Plus subscriber';
        const poll = {
          id, category:'community', title, yes:yesLabel, no:noLabel, closesInHrs:hrs, creator:creatorName,
          desc:'A community poll from '+creatorName+', a Foreseez Plus subscriber. Same earn‑only mechanics as every other topic — every response feeds straight into the same real‑time sentiment pool.'
        };
        poll.closes = new Date(liveNow().getTime() + hrs*3600000);
        state.customPolls.push(poll);
        state.contests.push({ id, status:'open', resolvedOption:null, pool:{yes:seedYes, no:seedNo} });
        state.creatingPoll = false; state._pollDraft = null;
        pushActivity('<b>You</b> published a new community poll &mdash; &ldquo;'+esc(title)+'&rdquo;');
        render(); toast('Poll published to the live feed'); break;
      }
      case 'likeComment': {
        const list = state.comments[state.openContest];
        if(!list) return;
        const cm = list[Number(payload)];
        if(!cm) return;
        if(cm.likedByMe){ cm.likedByMe=false; cm.likes=Math.max(0,(cm.likes||0)-1); }
        else { cm.likedByMe=true; cm.likes=(cm.likes||0)+1; }
        render(); break;
      }
      case 'reportComment': {
        const list = state.comments[state.openContest];
        if(!list) return;
        const cm = list[Number(payload)];
        if(!cm || !cm.media || cm.media.reported) return;
        cm.media.reported = true;
        render(); toast('Reported — hidden pending moderator review. Thanks for keeping debates safe.'); break;
      }
      case 'toggleVoiceRecording': {
        if(state._voiceRecording) stopVoiceRecording(); else startVoiceRecording();
        break;
      }
      case 'removeCommentMedia': {
        state._commentMedia = null; state._commentConsent = false; render(); break;
      }
      case 'postComment': {
        const input = document.getElementById('commentInput');
        const txt = (input?input.value:'').trim();
        const media = state._commentMedia;
        if((!txt && !media) || !state.openContest) return;
        if(media && !state._commentConsent) return;
        const mine = state.predictions[state.openContest];
        ensureComments(state.openContest).unshift({ who: state.user.name||'You', txt, hrsAgo:0, side: mine?mine.option:null, likes:0, likedByMe:false, media: media||null });
        state._commentDraft=''; state._commentMedia=null; state._commentConsent=false;
        pushActivity('<b>You</b> commented on &ldquo;'+esc(contestDef(state.openContest).title)+'&rdquo;');
        render(); break;
      }
      case 'subscribePlus': {
        state.plus = true;
        state.plusTier = 'plus';
        render(); toast('Foreseez Plus activated (simulated) — no points were spent or credited');
        break;
      }
      case 'subscribePlusPro': {
        state.plus = true;
        state.plusTier = 'pro';
        render(); toast('Foreseez Plus Pro activated (simulated) — no points were spent or credited');
        break;
      }
      case 'selectOpt': { state._sheetSel = payload; render(); break; }
      case 'chip': {
        const bal = balance();
        state._sheetStake = payload==='max' ? Math.min(bal,500) : Number(payload);
        render(); break;
      }
      case 'placePrediction': {
        const input = document.getElementById('stakeInput');
        const amt = Math.round(Number(input.value));
        const sel = state._sheetSel;
        if(!sel){ toast('Choose an outcome first'); return; }
        if(!amt || amt < 10){ toast('Minimum commitment is 10 pts'); return; }
        if(amt > balance()){ toast('Not enough points'); return; }
        if(callsLeftToday()<=0){ toast('Daily limit of '+dailyCallCap()+' calls reached'); return; }
        const id = state.openContest, def = contestDef(id);
        if(!def || def.status!=='open' || !(def.closes > liveNow())){ toast('This question is no longer open'); return; }
        addLedger('stake', 'Committed points to “'+def.title+'”', -amt, id);
        state.predictions[id] = { option:sel, staked:amt };
        state.callsToday++;
        render(); toast('Call locked in'); break;
      }
      case 'checkin': { addLedger('checkin','Daily check‑in reward', 50); state.checkedIn=true; render(); toast('+50 pts'); break; }
      case 'reset': {
        const keep = { questionDefs:state.questionDefs, contests:state.contests, feedStatus:state.feedStatus,
                       newsFeed:state.newsFeed, newsAttribution:state.newsAttribution, flags:state.flags, grievance:state.grievance };
        state = Object.assign(defaultState(), keep, SHOW_ONBOARDING ? {} : demoSignedIn());
        render(); toast('Preview data cleared'); break;
      }
      case 'shareRank': {
        const tier = rankTierFor(balance());
        toast('Rank card ready to share (simulated) — "'+tier.name+'" on Bharat Foreseez');
        break;
      }
    }
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
    const t = e.target;
    const idHandlers = {
      btnGoogle:()=>place('google'), btnApple:()=>place('apple'), btnSendOtp:()=>place('sendOtp'),
      btnVerifyOtp:()=>place('verifyOtp'), btnResendOtp:()=>place('resendOtp'),
      btnFinishKyc:()=>place('finishKyc'), btnCloseSheet:()=>place('closeSheet'),
      btnContinueInterests:()=>place('continueInterests'), btnSkipHook:()=>place('skipHook'),
      btnContinueToWelcome:()=>place('continueToWelcome'), btnEnterApp:()=>place('enterApp'),
      btnPlacePrediction:()=>place('placePrediction'), btnCheckin:()=>place('checkin'), btnReset:()=>place('reset'),
      btnBell:()=>place('toggleBell'), btnTheme:()=>toggleTheme(), btnRetryFeed:()=>{ loadFeed(); loadTicker(); }, btnSubscribePlus:()=>place('subscribePlus'), btnSubscribePlusPro:()=>place('subscribePlusPro'), btnPostComment:()=>place('postComment'),
      btnOpenCreatePoll:()=>place('openCreatePoll'), btnPublishPoll:()=>place('publishPoll'),
      btnShareRank:()=>place('shareRank'),
      btnCaptureSelfie:()=>place('captureSelfie'), btnRetakeSelfie:()=>place('retakeSelfie'),
      btnConfirmSelfie:()=>place('confirmSelfie'), btnSkipSelfie:()=>place('skipSelfie'),
      btnOpenSelfieSheet:()=>place('openSelfieSheet'),
      btnAttachPhoto:()=>document.getElementById('commentPhotoInput').click(),
      btnAttachVideo:()=>document.getElementById('commentVideoInput').click(),
      btnRecordVoice:()=>place('toggleVoiceRecording'),
      btnRemoveCommentMedia:()=>place('removeCommentMedia')
    };
    const idBtn = t.closest('button[id]');
    if(idBtn && idHandlers[idBtn.id]){ idHandlers[idBtn.id](); return; }
    const navBtn = t.closest('button[data-nav]'); if(navBtn){ place('nav', navBtn.dataset.nav); return; }
    const filterBtn = t.closest('button[data-filter]'); if(filterBtn){ place('filter', filterBtn.dataset.filter); return; }
    const sortBtn = t.closest('button[data-sort]'); if(sortBtn){ place('sort', sortBtn.dataset.sort); return; }
    const cardOpen = t.closest('[data-open-contest]');
    if(cardOpen){ if(cardOpen.tagName==='A') e.preventDefault(); place('openContest', cardOpen.dataset.openContest); return; }
    const interestBtn = t.closest('button[data-interest]'); if(interestBtn){ place('toggleInterest', interestBtn.dataset.interest); return; }
    const hookBtn = t.closest('button[data-hook]'); if(hookBtn){ place('hookPick', hookBtn.dataset.hook); return; }
    const optBtnEl = t.closest('button[data-opt]'); if(optBtnEl && !optBtnEl.disabled){ place('selectOpt', optBtnEl.dataset.opt); return; }
    const chipBtn = t.closest('button[data-chip]'); if(chipBtn){ place('chip', chipBtn.dataset.chip); return; }
    const pollHrsBtn = t.closest('button[data-poll-hrs]'); if(pollHrsBtn){ place('pollHrs', pollHrsBtn.dataset.pollHrs); return; }
    const likeBtn = t.closest('button[data-like-comment]'); if(likeBtn){ place('likeComment', likeBtn.dataset.likeComment); return; }
    const reportBtn = t.closest('button[data-report-comment]'); if(reportBtn && !reportBtn.disabled){ place('reportComment', reportBtn.dataset.reportComment); return; }
    if(t.id==='sheetBackdrop') place('closeSheet');
  });
  document.getElementById('sheetBackdrop').addEventListener('click', ()=>place('closeSheet'));
  document.body.addEventListener('keydown', function(e){
    if((e.key==='Enter' || e.key===' ') && e.target.matches && e.target.matches('[data-open-contest][role="button"]')){
      e.preventDefault(); place('openContest', e.target.dataset.openContest); return;
    }
    if(e.key==='Enter'){
      if(e.target.id==='phoneInput') place('sendOtp');
      if(e.target.id==='otpInput') place('verifyOtp');
      if(e.target.id==='commentInput') place('postComment');
    }
  });
  document.body.addEventListener('input', function(e){
    const t = e.target;
    if(t.id==='searchInput'){ state.searchQuery = t.value; render(); }
    else if(t.id==='stakeInput'){ state._sheetStake = t.value===''? '' : Number(t.value); }
    else if(t.id==='commentInput'){ state._commentDraft = t.value; }
    else if(t.id==='fullNameInput'){ state.fullName = t.value; render(); }
    else if(t.id==='dobInput'){ state.dob = t.value; render(); }
    else if(t.id==='pollTitleInput'){ state._pollDraft.title = t.value; render(); }
    else if(t.id==='pollYesInput'){ state._pollDraft.yes = t.value; }
    else if(t.id==='pollNoInput'){ state._pollDraft.no = t.value; }
  });
  document.body.addEventListener('change', function(e){
    if(e.target.id==='rawToggle'){ place('toggleRaw', e.target.checked); }
    else if(e.target.id==='chkAgeDeclare'){ state.ageDeclared = e.target.checked; render(); }
    else if(e.target.id==='chkConsent'){ state.consentGiven = e.target.checked; render(); }
    else if(e.target.id==='chkMediaConsent'){ state._commentConsent = e.target.checked; render(); }
    else if(e.target.id==='commentPhotoInput'){ handleCommentFile('photo', e.target.files[0]); e.target.value=''; }
    else if(e.target.id==='commentVideoInput'){ handleCommentFile('video', e.target.files[0]); e.target.value=''; }
  });


  /* ============ live refresh ============ */
  function refreshIfVisible(){
    if(document.visibilityState==='visible' && state.user.signedIn && Date.now() - feedLoadedAt >= FEED_MIN_GAP_MS) loadFeed();
  }
  setInterval(refreshIfVisible, FEED_REFRESH_MS);
  setInterval(function(){ if(document.visibilityState==='visible') loadTicker(); }, TICKER_REFRESH_MS);
  document.addEventListener('visibilitychange', refreshIfVisible);

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
    fn();
    const newPhoneBody = document.getElementById('phoneBody');
    if(newPhoneBody) newPhoneBody.scrollTop = scrollTop;
    const newSheetBody = document.querySelector('.sheet-body');
    if(newSheetBody) newSheetBody.scrollTop = sheetScrollTop;
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

  // Onboarding + KYC is fully built but gated off for in-browser testing.
  // Set SHOW_ONBOARDING to true (e.g. for the packaged APK) to show the
  // first-run onboarding flow on launch instead of booting into the app.
  const SHOW_ONBOARDING = false;
  function demoSignedIn(){
    return {
      phoneScreen:'home', obStep:'welcome', catFilter:'all',
      user:{ signedIn:true, name:'Demo Player', method:'phone' },
      fullName:'Demo Player',
      phoneVerified:true, ageDeclared:true, consentGiven:true, selfieVerified:true,
      ledger:[
        { id:'lg-seed-1', type:'signup', label:'Welcome reward', amount:1000, balanceAfter:1000, contestId:null, ts:timeNow() },
        { id:'lg-seed-2', type:'kyc', label:'Verification reward', amount:150, balanceAfter:1150, contestId:null, ts:timeNow() }
      ]
    };
  }
  function start(){
    state = defaultState();
    if(!SHOW_ONBOARDING) Object.assign(state, demoSignedIn());
    render();
    loadAppConfig();
    loadFeed();
    loadTicker();
  }
  start();
})();
