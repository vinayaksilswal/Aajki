// Bharat Foreseez consumer app. Split out of the original single-file build.
const BRAND = import.meta.env.BASE_URL + 'brand/';

(function(){
  "use strict";

  /* ============ utils ============ */
  function mulberry32(a){ return function(){ a|=0; a=a+0x6D2B79F5|0; let t=Math.imul(a^a>>>15,1|a); t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296; }; }
  function clamp(v,a,b){ return Math.max(a,Math.min(b,v)); }
  function fmtNum(n){ return Math.round(n).toLocaleString('en-IN'); }
  const WEEKDAYS=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function fmtDate(d){ return d.getDate()+' '+MONTHS[d.getMonth()]; }
  function formatDateLong(d){ return WEEKDAYS[d.getDay()]+', '+d.getDate()+' '+MONTHS[d.getMonth()]; }
  function formatTime(d){ let h=d.getHours(); const m=String(d.getMinutes()).padStart(2,'0'); const ap=h>=12?'pm':'am'; h=h%12; if(h===0)h=12; return h+':'+m+' '+ap; }
  function isoIST(d){ const p=n=>String(n).padStart(2,'0'); return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'T'+p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds())+'+05:30'; }
  // NOW_BASE anchors "today" for the sentiment index's most-recent day and each
  // contest's countdown, captured once when the app boots. liveNow() is called
  // fresh everywhere a countdown or clock is actually drawn, so the app always
  // shows the real current time rather than a frozen demo timestamp.
  const NOW_BASE = new Date();
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
    {key:'entertainment', label:'Entertainment', color:'var(--cat-entertainment)', emoji:'🎬'},
    {key:'policy', label:'Policy', color:'var(--cat-policy)', emoji:'📜'},
    {key:'world', label:'World', color:'var(--cat-world)', emoji:'🌍'},
    {key:'brand', label:'Brand Polls', color:'var(--cat-brand)', emoji:'🎯'},
    {key:'community', label:'Community Polls', color:'var(--cat-community)', emoji:'💬'}
  ];
  const CAT_MAP = Object.fromEntries(CATS.map(c=>[c.key,c]));

  const CONTESTS_SEED = [
    {id:'elec-turnout', category:'elections', title:'Bihar bypoll turnout crosses 58%?', desc:"Election Commission provisional turnout figures for the scheduled Bihar assembly bypoll, measured against the 58% mark.", closesInHrs:176, yes:'Turnout ≥ 58%', no:'Turnout < 58%', pool:{yes:2150,no:2680}},
    {id:'elec-enrol', category:'elections', title:'Voter enrolment additions beat last quarter?', desc:'Net new voter enrolments this quarter, per ECI electoral rolls, compared with the previous quarter’s net additions.', closesInHrs:488, yes:'Enrolment up q/q', no:'Down or flat', pool:{yes:1340,no:980}},
    {id:'mkt-nifty', category:'markets', title:'Nifty 50 closes above 26,000 this month?', desc:'NSE closing value of the Nifty 50 index within the current trading month.', closesInHrs:365, yes:'Nifty > 26,000', no:'Nifty ≤ 26,000', pool:{yes:5200,no:4100}},
    {id:'mkt-repo', category:'markets', title:'RBI holds the repo rate at the next MPC meeting?', desc:'Monetary Policy Committee decision at its next scheduled meeting — hold vs. change.', closesInHrs:530, yes:'Rate held', no:'Rate changed', pool:{yes:6800,no:2300}},
    {id:'mkt-rupee', category:'markets', title:'Rupee strengthens past ₹87/USD before month‑end?', desc:'RBI reference rate for INR/USD closing stronger than 87.00 on any day before month‑end.', closesInHrs:319, yes:'Rupee > ₹87/USD', no:'Rupee ≤ ₹87/USD', pool:{yes:1900,no:3100}},
    {id:'sport-odi', category:'sports', title:"India wins the next ODI vs. Australia?", desc:"Result of India's next scheduled ODI fixture against Australia.", closesInHrs:106, yes:'India wins', no:"India doesn't win", pool:{yes:4400,no:2600}},
    {id:'sport-isl', category:'sports', title:"Home side wins tonight's ISL fixture?", desc:'Full‑time result of tonight’s Indian Super League fixture.', closesInHrs:14, yes:'Home side wins', no:"Home side doesn't win", pool:{yes:1580,no:1420}},
    {id:'sport-ag-medals', category:'sports', title:'India finishes inside the top 5 at the Aichi‑Nagoya Asian Games?', desc:'Final overall medal‑table placement (by total medals) for India when the Games close on October 4, 2026 — despite the widely‑reported accommodation and logistics disruptions.', closesInHrs:264, yes:'Top 5 finish', no:'Outside top 5', pool:{yes:2400,no:2100}},
    {id:'sport-ag-accom', category:'sports', title:'Asian Games organisers issue a formal apology over the housing crisis?', desc:'Whether Aichi‑Nagoya 2026 organisers or Nagoya city officials issue a formal apology or corrective statement after widespread athlete‑housing complaints from India, China, South Korea and the Philippines.', closesInHrs:216, yes:'Formal apology issued', no:'No formal apology', pool:{yes:1450,no:2050}},
    {id:'sport-ag-chanu', category:'sports', title:"Mirabai Chanu medals despite the Games' travel delays?", desc:'Weightlifter Mirabai Chanu faced lengthy arrival and accommodation delays at the Asian Games. Does she still win a medal in her event?', closesInHrs:72, yes:'Medals', no:"Doesn't medal", pool:{yes:1900,no:1600}},
    {id:'world-ru-tariff-india', category:'world', title:'US formally applies the new 100% Russian‑oil tariff to India?', desc:"Whether the White House applies the tariff authorised under the newly‑signed Sanctioning Russia and Iran Act to India specifically, given India's continued Russian energy imports.", closesInHrs:672, yes:'Tariff applied to India', no:'Not applied', pool:{yes:2600,no:3400}},
    {id:'world-ru-ukraine-truce', category:'world', title:'A new Russia–Ukraine truce holds for 7+ days this quarter?', desc:'Following the failed April and May 2026 truce attempts, does any newly announced ceasefire hold without a major documented violation for at least seven consecutive days?', closesInHrs:600, yes:'Holds 7+ days', no:'Breaks down sooner', pool:{yes:1750,no:2950}},
    {id:'mkt-rupee-tariff', category:'markets', title:'Rupee weakens past ₹89/USD on tariff uncertainty?', desc:'RBI reference rate for INR/USD closing weaker than 89.00 on any day this month, amid the new US sanctions‑linked tariff threat over Russian energy imports.', closesInHrs:310, yes:'Rupee > ₹89/USD (weaker)', no:'Rupee ≤ ₹89/USD', pool:{yes:2100,no:2900}},
    {id:'pol-dpdp', category:'policy', title:'Data Protection Rules notified this quarter?', desc:'Whether the DPDP Act rules are formally notified in the Gazette within the current quarter.', closesInHrs:368, yes:'Notified this quarter', no:'Not notified', pool:{yes:3300,no:2100}},
    {id:'pol-gst', category:'policy', title:'GST Council approves rate rationalisation this session?', desc:"Whether the GST Council's upcoming session approves the proposed slab rationalisation.", closesInHrs:248, yes:'Approved', no:'Not approved this session', pool:{yes:2450,no:2900}},
    {id:'elec-bypoll2', category:'elections', title:'Second phase bypoll turnout beats phase one?', desc:'Whether provisional turnout in the second phase exceeds the first phase’s figure.', closesInHrs:212, yes:'Beats phase one', no:'At or below phase one', pool:{yes:1120,no:1360}},
    {id:'mkt-gold', category:'markets', title:'Gold holds above ₹75,000/10g this month?', desc:'MCX gold futures closing price staying above ₹75,000 per 10 grams through month‑end.', closesInHrs:290, yes:'Holds above', no:'Dips below', pool:{yes:2600,no:1950}},
    {id:'sport-kabaddi', category:'sports', title:'Defending champions retain the Pro Kabaddi title?', desc:'Whether the reigning champions win the next Pro Kabaddi League season.', closesInHrs:540, yes:'Retain title', no:'New champion', pool:{yes:1780,no:2040}},
    {id:'pol-evtarget', category:'policy', title:'EV sales cross 10% of new registrations this quarter?', desc:'Whether electric vehicles reach 10% of new vehicle registrations nationally this quarter, per VAHAN data.', closesInHrs:410, yes:'Crosses 10%', no:'Stays below', pool:{yes:1990,no:2210}},
    {id:'world-fed', category:'world', title:'US Federal Reserve cuts rates at its next FOMC meeting?', desc:"Decision at the Federal Open Market Committee's next scheduled meeting — cut vs. hold/raise.", closesInHrs:340, yes:'Rate cut', no:'Held or raised', pool:{yes:3800,no:3100}},
    {id:'world-uk-turnout', category:'world', title:'UK general election turnout tops 65%?', desc:"Official UK Electoral Commission turnout figure for the next general election.", closesInHrs:720, yes:'Turnout ≥ 65%', no:'Turnout < 65%', pool:{yes:1450,no:1980}},
    {id:'world-sp500', category:'world', title:'S&P 500 closes at a fresh all‑time high this month?', desc:'Whether the S&P 500 sets a new closing record before month‑end.', closesInHrs:280, yes:'New high set', no:'No new high', pool:{yes:4200,no:3600}},
    {id:'world-cup', category:'world', title:'Defending champion advances past the group stage?', desc:"Whether the reigning champion progresses past the group stage at the next major international football tournament.", closesInHrs:600, yes:'Advances', no:'Eliminated in groups', pool:{yes:5100,no:1400}},
    {id:'world-un', category:'world', title:'UN Security Council passes the pending resolution this session?', desc:'Whether the resolution currently tabled at the UN Security Council is adopted this session.', closesInHrs:190, yes:'Passes', no:'Fails or vetoed', pool:{yes:1680,no:2260}},
    {id:'world-climate', category:'world', title:'Global temperature anomaly stays above +1.5°C this month?', desc:"Monthly global average surface temperature anomaly vs. pre‑industrial baseline, per Copernicus/NOAA data.", closesInHrs:250, yes:'Stays above +1.5°C', no:'Falls below', pool:{yes:2900,no:1700}},
    {id:'world-unga-jaishankar', category:'world', title:"Jaishankar's UNGA address names a country critically?", desc:"External Affairs Minister S. Jaishankar leads India's delegation and addresses the UNGA General Debate on September 26. Indian MEA convention typically avoids naming specific countries critically — does this address break from that pattern?", closesInHrs:54, yes:'Names a country critically', no:'No country named critically', pool:{yes:1200,no:2800}},
    {id:'world-unga-ai-res', category:'world', title:'UNGA adopts a dedicated AI‑governance resolution this session?', desc:"Following Digital Cooperation Day and the UN's newly appointed Global Advocate for Human‑centric Digital Governance, does the 81st UNGA session formally adopt a resolution specifically on AI governance?", closesInHrs:2160, yes:'Resolution adopted', no:'Not adopted this session', pool:{yes:1850,no:2150}},
    {id:'world-us-midterm-house', category:'world', title:'Democrats win a majority in the US House in the November midterms?', desc:'Party control of the US House of Representatives after the November 3, 2026 midterm elections. Republicans currently hold a narrow majority.', closesInHrs:720, yes:'Democrats win the House', no:'Republicans keep the House', pool:{yes:6200,no:3800}},
    {id:'world-us-midterm-senate', category:'world', title:'Democrats win control of the US Senate in the November midterms?', desc:'Party control of the US Senate after the November 3, 2026 midterm elections. Republicans currently hold the chamber and analysts widely describe the race for control as close.', closesInHrs:720, yes:'Democrats win the Senate', no:'Republicans keep the Senate', pool:{yes:4300,no:5200}},
    {id:'world-brazil-lula', category:'world', title:'Lula wins a fourth term as Brazil’s president?', desc:'Final result of Brazil’s 2026 presidential election, including the October 25 runoff if one is needed. Polls have shown President Lula and Senator Flávio Bolsonaro within a few points of each other.', closesInHrs:504, yes:'Lula is elected', no:'Another candidate is elected', pool:{yes:5100,no:4900}},
    {id:'ent-drishyam-250', category:'entertainment', title:'Drishyam: The Conclusion crosses ₹250 crore net in India by October 11?', desc:'India net box-office total for Ajay Devgn’s Drishyam: The Conclusion, released October 2, per major trade trackers, by the end of its second weekend.', closesInHrs:190, yes:'₹250 crore or more', no:'Below ₹250 crore', pool:{yes:3800,no:3300}},
    {id:'ent-udta-teer-open', category:'entertainment', title:'Udta Teer opens above ₹5 crore net on day one?', desc:'India net day-one collection for the October 9 release starring Ayushmann Khurrana and Sara Ali Khan, as reported by trade trackers.', closesInHrs:170, yes:'Above ₹5 crore', no:'₹5 crore or less', pool:{yes:2100,no:2900}},
    {id:'ent-avengers-dune', category:'entertainment', title:'Avengers: Doomsday out-earns Dune: Part Three on opening weekend?', desc:'Both Hollywood tentpoles are scheduled for December 18, 2026. Which film has the higher North American opening-weekend gross?', closesInHrs:1900, yes:'Avengers: Doomsday', no:'Dune: Part Three', pool:{yes:6900,no:2300}},
    {id:'ent-avengers-250m', category:'entertainment', title:'Avengers: Doomsday opens above $250 million in North America?', desc:'Opening-weekend domestic gross for Avengers: Doomsday, scheduled for release on December 18, 2026, per studio-reported actuals.', closesInHrs:1900, yes:'Above $250M', no:'$250M or less', pool:{yes:3400,no:3900}},
    {id:'ent-grammy-swift', category:'entertainment', title:'Taylor Swift earns an Album of the Year nomination at the 2027 Grammys?', desc:'The Recording Academy announces 2027 Grammy nominations on November 16, 2026, ahead of the ceremony on February 7, 2027.', closesInHrs:1030, yes:'Nominated', no:'Not nominated', pool:{yes:7200,no:2100}},
    {id:'ent-hot100-new1', category:'entertainment', title:'A new No. 1 takes over the Billboard Hot 100 on the October 17 chart?', desc:'Whether the song at No. 1 on the Billboard Hot 100 dated October 17, 2026 differs from the No. 1 on the chart dated October 10.', closesInHrs:190, yes:'New No. 1', no:'Same No. 1', pool:{yes:2600,no:4700}},
    {id:'elec-up-census', category:'elections', title:'UP caste census results released by the Feb 2027 deadline?', desc:"Whether the Uttar Pradesh caste census — cited by SBSP chief Om Prakash Rajbhar as the trigger for his renewed four‑way state‑division demand — is completed and its results released by the stated February 2027 deadline.", closesInHrs:3800, yes:'Released on time', no:'Delayed past deadline', pool:{yes:1650,no:2450}},
    {id:'elec-up-nda-rift', category:'elections', title:"UP's ruling NDA coalition avoids a public rupture over the state‑division row this quarter?", desc:"BJP ally Sanjeev Balyan has backed Om Prakash Rajbhar's UP state‑division proposal, while coalition partner the Nishad Party has strongly opposed it. Does the alliance avoid a formal, public split over this issue in the current quarter?", closesInHrs:1440, yes:'Coalition holds', no:'Public rupture occurs', pool:{yes:2900,no:1300}},
    {id:'elec-punjab-alliance', category:'elections', title:'BJP and Shiromani Akali Dal announce a formal 2027 alliance before year‑end?', desc:"BJP‑SAD alliance talks reportedly gained pace through August 2026, even as BJP's Punjab unit says it's preparing to contest all 117 seats alone. Is a formal pre‑poll alliance announced before December 31, 2026?", closesInHrs:2352, yes:'Alliance announced', no:'No alliance by year‑end', pool:{yes:1700,no:2300}},
    {id:'pol-upi-mdr', category:'policy', title:'New UPI merchant fee (MDR) framework takes effect on schedule?', desc:'The tiered UPI Merchant Discount Rate framework — free for P2P and small merchants, capped charges above ₹2,000 — is slated to take effect October 15, 2026. Does it roll out on that date without a deferral?', closesInHrs:504, yes:'Takes effect on schedule', no:'Deferred or delayed', pool:{yes:3200,no:1100}},
    {id:'pol-ecom-rules', category:'policy', title:'New e‑commerce consumer‑protection rules take effect on schedule?', desc:'New rules requiring algorithmic‑search disclosure, sponsored‑result labelling and dark‑pattern audits for e‑commerce platforms are slated to begin January 1, 2027. Do they take effect on that date as planned?', closesInHrs:2376, yes:'Takes effect on schedule', no:'Deferred or delayed', pool:{yes:2600,no:1500}},
    // Brand Polls: hypothetical sponsored questions — a consumer brand asks the
    // crowd for product feedback instead of running a traditional survey.
    // Same earn‑only mechanics as every other topic; the brand's product is
    // the subject, not something bought or staked. Aggregated, anonymized
    // sentiment from these is exactly the licensable data product described
    // in the pitch — this is that pillar made concrete inside the app.
    {id:'brand-suzuki-swift', category:'brand', sponsor:'Suzuki', title:'Will most players rate the new Swift facelift 4★ or higher?', desc:'Suzuki is gauging early consumer sentiment on its refreshed Swift hatchback ahead of launch. Aggregated, anonymized responses only — never individually identifiable.', closesInHrs:120, yes:'4★ or higher', no:'Below 4★', pool:{yes:2200,no:1400}},
    {id:'brand-bmw-ev', category:'brand', sponsor:'BMW', title:'Would you consider BMW’s upcoming compact EV for your next car?', desc:'BMW is testing purchase intent for a compact EV ahead of its India launch, using real player sentiment instead of a traditional panel survey.', closesInHrs:240, yes:'Would consider it', no:'Would not', pool:{yes:1850,no:2050}},
    {id:'brand-boat-earbuds', category:'brand', sponsor:'boAt', title:'Will boAt’s new earbuds outsell their previous flagship in month one?', desc:'boAt wants to know whether players expect the new launch to beat the outgoing model’s first‑month sales — a live crowd read ahead of the official numbers.', closesInHrs:340, yes:'Outsells it', no:'Falls short', pool:{yes:1620,no:1180}},
    // Sponsored campaign: a paid Suzuki sponsorship with its own real-world
    // prizes for the top 5 players on this one question — distinct from
    // the ordinary brand poll above. campaignId links it to CAMPAIGNS below.
    {id:'brand-suzuki-ev-accept', category:'brand', sponsor:'Suzuki', campaignId:'suzuki-ev-2026', title:'Would most Indian car buyers seriously consider an EV as their next car?', desc:'A paid Suzuki sponsorship: gauging real, India‑wide consumer sentiment on EV adoption ahead of a launch decision. Top 5 players on this question win real prizes from Suzuki — aggregated, anonymized responses only, never individually identifiable.', closesInHrs:168, yes:'Would seriously consider one', no:'Would not', pool:{yes:214000,no:166000}}
  ];
  // Anchor each contest's close time to the moment the app actually loaded,
  // rather than a fixed calendar date, so countdowns always make sense
  // whenever this prototype is opened.
  CONTESTS_SEED.forEach(c => { c.closes = new Date(NOW_BASE.getTime() + c.closesInHrs*3600000); });

  // Context-feed headlines: illustrative narrative copy giving each foreseeing
  // category real-world texture. Static seed + occasional new arrivals via
  // tickLive, same pattern as the activity strip — clearly labelled as
  // illustrative in the UI, never presented as a live news connection.
  const NEWS_SEED = [
    {cat:'world', text:'G20 finance deputies meet ahead of next month’s communiqué on cross-border payments.'},
    {cat:'world', text:'Brazil’s presidential race heads toward an October 25 runoff if no candidate clears 50% of valid votes; polls show Lula and Flávio Bolsonaro within a few points.'},
    {cat:'world', text:'US midterm campaigns enter their final month with control of both chambers of Congress in play on November 3.'},
    {cat:'entertainment', text:'Drishyam: The Conclusion posts one of the biggest Hindi openings of 2026, trade trackers report.'},
    {cat:'entertainment', text:'Recording Academy confirms Grammy nominations on November 16 and the ceremony on February 7, 2027.'},
    {cat:'entertainment', text:'Avengers: Doomsday and Dune: Part Three are both slated to open on December 18.'},
    {cat:'world', text:'Red Sea shipping volumes edge up as insurers reprice war-risk premiums.'},
    {cat:'markets', text:'FPI flows into Indian equities turn net positive for a second straight week.'},
    {cat:'markets', text:'Brent crude holds near recent range as OPEC+ output policy stays unchanged.'},
    {cat:'policy', text:'Parliamentary standing committee schedules review of the DPDP Rules implementation timeline.'},
    {cat:'policy', text:'RBI monetary policy committee minutes released; commentary flags food-price base effects.'},
    {cat:'elections', text:'Election Commission updates model code guidance ahead of the bypoll schedule.'},
    {cat:'elections', text:'State CEO offices report final electoral roll revision figures.'},
    {cat:'world', text:'EU council discusses tariff carve-outs in ongoing trade-framework talks.'},
    {cat:'world', text:'UN climate body publishes interim monitoring update on 1.5°C pathway tracking.'},
    {cat:'sports', text:'BCCI confirms venue schedule for the upcoming home international season.'},
    {cat:'markets', text:'Gold holds near recent highs as investors track central-bank reserve buying.'},
    {cat:'policy', text:'GST Council secretariat circulates agenda note ahead of the next session.'},
    {cat:'world', text:'Central banks in the G7 signal a data-dependent stance heading into next quarter.'},
    {cat:'world', text:'UNGA high-level week opens in New York with EAM Jaishankar set to lead the Indian delegation.'},
    {cat:'world', text:'UN Digital Cooperation Day spotlights human-centric AI governance ahead of the General Debate.'},
    {cat:'elections', text:'SBSP chief Om Prakash Rajbhar revives the four-way UP state-division debate ahead of 2027 polls.'},
    {cat:'elections', text:'UP coalition partners trade public statements over the state-division proposal.'},
    {cat:'elections', text:'Punjab BJP unit signals readiness to contest all 117 seats as SAD alliance talk continues.'},
    {cat:'policy', text:'NPCI circulates merchant guidance ahead of the tiered UPI fee framework taking effect next month.'},
    {cat:'policy', text:'Commerce ministry publishes draft compliance checklist for incoming e-commerce disclosure rules.'},
  ];
  function seedNewsFeed(){
    const rng = mulberry32(77);
    return NEWS_SEED.slice().sort(()=>rng()-0.5).map((n,i)=>({ cat:n.cat, text:n.text, minsAgo: 4 + i*7 + Math.floor(rng()*5) }));
  }

  const PRIZES = [
    {id:'earbuds', name:'Wireless Earbuds', short:'Earbuds', desc:'Over‑ear, 24h battery.', cost:1800, tag:'Electronics'},
    {id:'smartwatch', name:'Fitness Smartwatch', short:'Smartwatch', desc:'Heart‑rate + SpO2 tracking.', cost:3200, tag:'Electronics'},
    {id:'telescope', name:'Tabletop Telescope', short:'Telescope', desc:'70mm refractor with tripod.', cost:2400, tag:'Electronics'},
    {id:'boardgames', name:'Strategy Board‑Game Set', short:'Board Games', desc:'A curated 3‑game bundle.', cost:1200, tag:'Games'},
    {id:'cricketbat', name:'Signed Cricket Bat', short:'Cricket Bat', desc:'Team‑signed willow, display‑cased.', cost:5000, tag:'Collectible'},
    {id:'trek', name:'Weekend Trek Package', short:'Trek Package', desc:'Two‑person guided foothill trek.', cost:6500, tag:'Experience'}
  ];
  function bestPrizeFor(pts){
    const affordable = PRIZES.filter(p=>pts>=p.cost).sort((a,b)=>b.cost-a.cost);
    return affordable.length ? affordable[0] : null;
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

  // A handful of the most active seeded players are marked verified —
  // makes the badge read as a real, earned status other players also
  // have, not just a cosmetic toggle on the signed-in user.
  const LB_SEED = [
    {name:'Rhea Kapoor', pts:4820, verified:true},{name:'Aman Verma', pts:4510, verified:true},{name:'Kavya Iyer', pts:4275, verified:true},
    {name:'Devansh Rao', pts:3990, verified:true},{name:'Sanya Bhatt', pts:3820, verified:true},{name:'Ishaan Nair', pts:3640},
    {name:'Meera Joshi', pts:3410},{name:'Arjun Sethi', pts:3105},{name:'Priya Menon', pts:2870},
    {name:'Rohan Dutta', pts:2640},{name:'Tanvi Shah', pts:2390},{name:'Vikram Pillai', pts:2110},
    {name:'Omar Farsi', pts:3560, verified:true},{name:'Lena Kovač', pts:2980},{name:'Marco Rossi', pts:2510}
  ];

  // Sponsored Campaigns: a paid brand campaign that offers its own real-world
  // prizes to the top players on ONE specific question — distinct from
  // the app-wide Winner Prizes above. This is the "Sponsorship" revenue line
  // from the pitch made concrete: campaign-scoped ranking reuses the same
  // pari-mutuel payout every topic already runs on (net points won on this
  // campaign's question), it does not invent a new scoring mechanic. Real,
  // non-cash prizes still require the same selfie/KYC verification every
  // other prize-eligible action in this app requires, since fulfilment means
  // shipping or crediting an actual, identified person.
  const CAMPAIGNS = {
    'suzuki-ev-2026': {
      id:'suzuki-ev-2026',
      sponsor:'Suzuki',
      title:'Suzuki EV Acceptance Index — India',
      contestId:'brand-suzuki-ev-accept',
      blurb:'A paid Suzuki sponsorship: gauging real consumer sentiment on EV adoption across India before committing to a launch strategy. Aggregated, anonymized responses power the read Suzuki buys — individual foresights are never sold or shared identifiably.',
      rankedBy:'net Foreseez Points won on this one campaign question',
      entrants:3180,
      correctShare:0.55,
      prizes:[
        {rank:1, name:'iPhone 17 Pro',            icon:'📱', value:'Fulfilled directly by Suzuki, after KYC match'},
        {rank:2, name:'iPad',                      icon:'📱', value:'Fulfilled directly by Suzuki, after KYC match'},
        {rank:3, name:'Fitness Smartwatch',          icon:'⌚', value:'Fulfilled directly by Suzuki, after KYC match'},
        {rank:4, name:'Wireless Earbuds',            icon:'🎧', value:'Fulfilled directly by Suzuki, after KYC match'},
        {rank:5, name:'Suzuki Rider Gear Hamper',    icon:'🎁', value:'Fulfilled directly by Suzuki, after KYC match'}
      ]
    }
  };
  // Illustrative top-5 stakers for the campaign demo — scored with the exact
  // same payout math as every other topic (staked × total/winning pool),
  // just seeded with larger, veteran-player stake sizes so a "top 5 out
  // of thousands" outcome looks like what real conviction-weighted ranking
  // produces once resolved.
  const CAMPAIGN_TOP5 = {
    'suzuki-ev-2026': [
      {name:'Rhea Kapoor',  staked:4800},
      {name:'Aman Verma',   staked:4200},
      {name:'Omar Farsi',   staked:3650},
      {name:'Devansh Rao',  staked:3300},
      {name:'Kavya Iyer',   staked:2900}
    ]
  };

  const COMMENT_TEMPLATES = [
    'Leaning {side} based on the last few data points.',
    'Went with {side} — feels like the safer read here.',
    'Not obvious either way, but tilting {side}.',
    '{side} looks right if the recent trend holds.',
    'Historical base rates favour {side} here.',
    'Volume’s been picking up on {side} the last hour.',
    'Going against the crowd on this one — {side}.'
  ];
  function hashStr(s){ let h=0; for(let i=0;i<s.length;i++){ h=(Math.imul(31,h)+s.charCodeAt(i))|0; } return h>>>0; }

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
      contests: CONTESTS_SEED.map(c => ({ id:c.id, status:'open', resolvedOption:null, pool:{yes:c.pool.yes,no:c.pool.no} })),
      predictions:{},
      redeemed:{},
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
      newsFeed: seedNewsFeed(),
      lbPoints: Object.fromEntries(LB_SEED.map(p=>[p.name,p.pts])),
      _commentMedia:null, _commentConsent:false, _voiceRecording:false, _voiceElapsed:0
    };
  }
  let state = defaultState();

  function contestDef(id){ return CONTESTS_SEED.find(c=>c.id===id) || (state.customPolls||[]).find(c=>c.id===id); }
  // Daily call limits by plan: free 10, Plus 25, Plus Pro unlimited.
  const DAILY_CALL_LIMITS = { free:10, plus:25, pro:Infinity };
  function dailyCallCap(){ return state.plusTier==='pro' ? DAILY_CALL_LIMITS.pro : (state.plus ? DAILY_CALL_LIMITS.plus : DAILY_CALL_LIMITS.free); }
  function rollCallDay(){ const k = liveNow().toDateString(); if(state.callsDay!==k){ state.callsDay=k; state.callsToday=0; } }
  function callsLeftToday(){ rollCallDay(); return Math.max(0, dailyCallCap() - state.callsToday); }
  function balance(){ return state.ledger.length ? state.ledger[state.ledger.length-1].balanceAfter : 0; }
  function addLedger(type,label,amount,contestId){
    const bal = balance() + amount;
    state.ledger.push({ id:'lg'+state.ledger.length+'-'+Date.now(), type, label, amount, balanceAfter:bal, contestId:contestId||null, ts:timeNow() });
    return bal;
  }

  /* ============ comments / activity / notifications ============ */
  function ensureComments(contestId){
    if(state.comments[contestId]) return state.comments[contestId];
    const def = contestDef(contestId);
    const rng = mulberry32(hashStr(contestId));
    const n = 2 + Math.floor(rng()*4);
    const pool = LB_SEED.slice();
    const list = [];
    for(let i=0;i<n;i++){
      const person = pool.splice(Math.floor(rng()*pool.length),1)[0] || {name:'Anon Player'};
      const sideKey = rng() < 0.55 ? 'yes' : 'no';
      const sideLabel = sideKey==='yes' ? def.yes : def.no;
      const tmpl = COMMENT_TEMPLATES[Math.floor(rng()*COMMENT_TEMPLATES.length)];
      const hrsAgo = 1 + Math.floor(rng()*47);
      const likes = Math.floor(rng()*24);
      list.push({ who:person.name, txt:tmpl.replace('{side}', sideLabel), hrsAgo, side:sideKey, likes, likedByMe:false });
    }
    list.sort((a,b)=>a.hrsAgo-b.hrsAgo);
    state.comments[contestId] = list;
    return list;
  }

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
        +'<div class="callout"><strong>+30 pts</strong> &mdash; first foresight bonus, already credited to your wallet.</div>'
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
    if(c.status==='resolved') return '<span class="chip chip-status-muted"><span class="chip-dot"></span>Resolved</span>';
    const diff = contestDef(c.id).closes - liveNow();
    if(diff < 24*3600000) return '<span class="chip chip-status-warn"><span class="chip-dot"></span>Closing soon</span>';
    return '<span class="chip chip-status-good"><span class="chip-dot"></span>Open</span>';
  }
  function closesText(def){
    const diff = def.closes - liveNow();
    if(diff<=0) return 'Closed';
    const days = Math.floor(diff/86400000), hrs = Math.floor((diff%86400000)/3600000);
    return days>=1 ? days+'d '+hrs+'h left' : hrs+'h left';
  }

  // Shown right on Home so a prize catalogue is the first thing a player sees
  // after signing in — the "what could I win" hook, before any topic list.
  function renderHomePrizeStrip(){
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
      if(state.catFilter!=='all' && def.category!==state.catFilter) return false;
      if(q && !(def.title.toLowerCase().includes(q) || def.desc.toLowerCase().includes(q))) return false;
      return true;
    });
    filtered = filtered.slice().sort((a,b)=>{
      if(state.sortMode==='trending'){
        return (b.pool.yes+b.pool.no) - (a.pool.yes+a.pool.no);
      }
      return contestDef(a.id).closes - contestDef(b.id).closes;
    });
    const cards = filtered.map(c=>{
      const def = contestDef(c.id);
      const cat = CAT_MAP[def.category];
      const total = c.pool.yes + c.pool.no;
      const yesPct = Math.round((c.pool.yes/total)*100);
      const mine = state.predictions[c.id];
      return '<div class="contest-card" data-open-contest="'+c.id+'">'
        +(def.sponsor ? '<span class="sponsor-chip"><span class="mk">'+esc(def.sponsor[0])+'</span>Sponsored by '+esc(def.sponsor)+'</span>' : '')
        +(def.creator ? '<span class="creator-chip"><span class="mk">'+esc((def.creator||'A')[0])+'</span>Poll by '+esc(def.creator)+'</span>' : '')
        +'<div class="row1"><span class="chip" style="background:color-mix(in srgb, '+cat.color+' 16%, transparent); color:'+cat.color+';"><span class="chip-dot"></span>'+cat.label+'</span>'+statusChip(c)+'</div>'
        +'<h4>'+esc(def.title)+'</h4>'
        +'<div class="prob-row"><span class="prob-num">'+yesPct+'%</span><span class="prob-lbl">chance of &ldquo;'+esc(def.yes)+'&rdquo;'+(mine?' &middot; you foresaw':'')+'</span></div>'
        +'<div class="prob-bar"><i style="width:'+yesPct+'%;"></i></div>'
        +'<div class="meta"><span>'+(c.status==='resolved' ? ('Result: '+(c.resolvedOption==='yes'?def.yes:def.no)) : closesText(def))+'</span><span class="vol">'+fmtNum(total)+' pts in play</span></div>'
        +'</div>';
    }).join('') || '<p class="hint">No topics match — try another category or search term.</p>';

    const filters = '<div class="cat-filters">'
      + '<button data-filter="all" class="'+(state.catFilter==='all'?'active':'')+'">All</button>'
      + CATS.map(c=>'<button data-filter="'+c.key+'" class="'+(state.catFilter===c.key?'active':'')+'"><span class="cat-dot" style="background:'+c.color+';"></span>'+c.label+'</button>').join('')
      + '</div>';

    const activity = '<div class="activity-strip"><div class="hd"><h3><span class="live-label"><span class="live-dot"></span>Live activity</span></h3></div>'
      + (state.activity.length
          ? state.activity.slice(0,5).map(a=>'<div class="act-row">'+a.text+'<span class="t">'+a.ts+'</span></div>').join('')
          : '<div class="act-row" style="border-bottom:0;">Markets tick on their own — leave this open and watch it fill in.</div>')
      + '</div>';

    return '<div class="greet"><div><h2>Namaste, '+esc(state.user.name)+(state.selfieVerified?' '+verifiedBadgeIcon():'')+' '+rankBadgeChip(balance())+(state.plus?' <span class="plus-badge">'+(state.plusTier==='pro'?'Plus Pro':'Plus')+'</span>':'')+'</h2><div class="sub">'+state.contests.filter(c=>c.status==='open').length+' topics open &middot; '+formatDateLong(liveNow())+'</div></div></div>'
      + '<div class="balance-card"><div class="k">Foreseez Points</div><div class="v mono">'+fmtNum(balance())+'</div></div>'
      + renderHomePrizeStrip()
      + renderNewsTicker()
      + '<div class="search-row"><input id="searchInput" type="search" placeholder="Search topics…" value="'+esc(state.searchQuery||'')+'">'
      + '<div class="sort-toggle"><button data-sort="closing" class="'+(state.sortMode==='closing'?'active':'')+'">Closing soon</button><button data-sort="trending" class="'+(state.sortMode==='trending'?'active':'')+'">Trending</button></div></div>'
      + filters + activity + '<div>' + cards + '</div>';
  }
  function renderNewsTicker(){
    const items = (state.newsFeed||[]).slice(0,10).map(n=>{
      const cat = CAT_MAP[n.cat];
      return '<span class="news-item"><span class="cat-dot" style="background:'+cat.color+';"></span>'+esc(n.text)+'</span>';
    }).join('<span class="news-sep">&bull;</span>');
    return '<div class="news-ticker"><div class="news-hd"><span class="live-label"><span class="live-dot"></span>Context feed</span><span class="news-note">Illustrative headlines, not a live news connection</span></div>'
      + '<div class="news-track-wrap"><div class="news-track">'+items+'<span class="news-sep">&bull;</span>'+items+'</div></div></div>';
  }

  // Pulse: the product's actual differentiator made visible on-screen. Every
  // open contest already carries a live pool.yes/pool.no split — this screen
  // does nothing but aggregate that same real data up to category level and
  // surface it as a first-class destination, instead of leaving it implicit
  // inside individual contest cards. Framed explicitly as "not a market" so
  // it reads as a data/insights product, not a Kalshi/Polymarket clone.
  function pulseStats(){
    const open = state.contests.filter(c=>c.status==='open');
    const byCat = {};
    CATS.forEach(cat=>{ byCat[cat.key] = { vol:0, count:0, confSum:0 }; });
    let totalVol = 0;
    const ranked = [];
    open.forEach(c=>{
      const def = contestDef(c.id);
      const total = c.pool.yes + c.pool.no;
      if(!total) return;
      const yesPct = Math.round((c.pool.yes/total)*100);
      const conf = Math.max(yesPct, 100-yesPct);
      const b = byCat[def.category];
      b.vol += total; b.count += 1; b.confSum += conf;
      totalVol += total;
      ranked.push({ id:c.id, def, yesPct, conf, total });
    });
    return { open, byCat, totalVol, ranked };
  }
  function renderPulse(){
    const { open, byCat, totalVol, ranked } = pulseStats();
    const activeCats = CATS.filter(cat => byCat[cat.key].count);

    const tiles = activeCats.map(cat=>{
      const b = byCat[cat.key];
      const avgConf = Math.round(b.confSum / b.count);
      return '<div class="tile callout" style="border-color:color-mix(in srgb, '+cat.color+' 35%, var(--border));">'
        + '<div class="top"><span class="cat-dot" style="background:'+cat.color+';"></span>'+cat.label+'</div>'
        + '<div class="val">'+avgConf+'%</div>'
        + '<div class="delta" style="color:var(--ink-muted); font-weight:600;">avg. lean to larger side</div>'
        + '<div class="hint" style="margin-top:6px;">'+b.count+' live question'+(b.count===1?'':'s')+' &middot; '+fmtNum(b.vol)+' pts reflected</div>'
        + '</div>';
    }).join('');

    function insightRow(r){
      const cat = CAT_MAP[r.def.category];
      return '<div class="feed-row" data-open-contest="'+r.id+'" style="cursor:pointer;">'
        + '<span class="who"><span class="cat-dot" style="background:'+cat.color+'; margin-right:6px;"></span>'+esc(r.def.title)+'</span>'
        + '<span class="meta">'+r.conf+'% lean &middot; '+fmtNum(r.total)+' pts</span></div>';
    }
    const decisive = ranked.slice().sort((a,b)=>b.conf-a.conf).slice(0,3);
    const contested = ranked.slice().sort((a,b)=>a.conf-b.conf).slice(0,3);

    return '<div class="dash-head"><div><h2 style="font-size:19px;">Pulse &mdash; what India foresees</h2>'
      + '<p>Aggregated live across every open question. Not odds, not a trade &mdash; this is what the crowd believes, captured before the answer is known.</p></div>'
      + '<span class="live-label"><span class="live-dot"></span>Live</span></div>'
      + '<div class="callout" style="margin-bottom:16px;"><strong>'+fmtNum(totalVol)+' points</strong> reflected across <strong>'+open.length+' open question'+(open.length===1?'':'s')+'</strong> in '+activeCats.length+' categories right now. This is the licensable sentiment product from the pitch, made visible &mdash; not a separate feature bolted on.</div>'
      + '<div class="tiles">'+tiles+'</div>'
      + '<div class="chart-card callout"><h3 style="margin-bottom:2px;">Most decisive</h3><p class="hint" style="margin-bottom:8px;">Where the crowd is most confident.</p>'
      + (decisive.map(insightRow).join('') || '<p class="hint">Not enough live questions yet.</p>') + '</div>'
      + '<div class="chart-card callout"><h3 style="margin-bottom:2px;">Most contested</h3><p class="hint" style="margin-bottom:8px;">Where the crowd is genuinely split &mdash; 50/50 territory.</p>'
      + (contested.map(insightRow).join('') || '<p class="hint">Not enough live questions yet.</p>') + '</div>'
      + '<p class="news-note" style="margin-top:2px; margin-bottom:14px;">Prototype note: activity volumes are simulated demo data, the same seed used everywhere else in this app &mdash; the aggregation mechanic itself (live pool &rarr; live consensus read) is real, and is what a production backend would scale into the licensed brand-insights product.</p>';
  }

  function renderContestSheet(id){
    const def = contestDef(id);
    const c = state.contests.find(x=>x.id===id);
    const cat = CAT_MAP[def.category];
    const total = c.pool.yes + c.pool.no;
    const yesPct = Math.round((c.pool.yes/total)*100), noPct = 100-yesPct;
    const yesMult = (total/c.pool.yes).toFixed(2), noMult = (total/c.pool.no).toFixed(2);
    const mine = state.predictions[id];
    const sel = state._sheetSel || (mine ? mine.option : null);
    const stakeAmt = (state._sheetStake===undefined || state._sheetStake===null) ? 50 : state._sheetStake;

    let body = (def.sponsor ? '<span class="sponsor-chip"><span class="mk">'+esc(def.sponsor[0])+'</span>Sponsored by '+esc(def.sponsor)+'</span><br>' : '')
      + (def.creator ? '<span class="creator-chip"><span class="mk">'+esc((def.creator||'A')[0])+'</span>Poll by '+esc(def.creator)+'</span><br>' : '')
      + '<span class="chip" style="background:color-mix(in srgb, '+cat.color+' 16%, transparent); color:'+cat.color+'; margin-bottom:8px;"><span class="chip-dot"></span>'+cat.label+'</span>'
      + '<h3 style="font-size:15.5px; margin-top:4px;">'+esc(def.title)+'</h3>'
      + '<p style="font-size:12.5px; color:var(--ink-2); line-height:1.55;">'+esc(def.desc)+'</p>'
      + '<div class="prob-bar" style="margin-top:10px;"><i style="width:'+yesPct+'%;"></i></div>'
      + '<div class="meta" style="margin-top:4px; display:flex; justify-content:space-between;"><span>'+yesPct+'% Yes</span><span class="vol">'+fmtNum(total)+' pts in play</span></div>'
      + (def.campaignId ? '<button class="btn btn-sm" data-open-campaign="'+def.campaignId+'" style="margin-top:10px; width:100%; background:color-mix(in srgb, var(--cat-brand) 14%, var(--surface)); border-color:color-mix(in srgb, var(--cat-brand) 45%, var(--border)); color:var(--cat-brand);">🏆 Real prizes for the top 5 — view campaign &amp; leaderboard</button>' : '');

    if(c.status==='resolved'){
      const won = mine && mine.option===c.resolvedOption;
      body += '<div class="callout" style="margin-top:10px;"><strong>Resolved: '+(c.resolvedOption==='yes'?def.yes:def.no)+'</strong><br>'
        + (mine ? (won ? 'Your foresight was correct — reward credited to your ledger.' : 'Your foresight did not match — no reward, your committed points were not returned.') : 'You did not submit a foresight on this topic.')
        + '</div>';
    } else {
      body += '<div class="opt-grid" style="margin-top:12px;">'
        + optBtn('yes', def.yes, yesPct, yesMult, sel, mine)
        + optBtn('no', def.no, noPct, noMult, sel, mine)
        + '</div>';
      if(mine){
        body += '<div class="callout">You committed <strong>'+fmtNum(mine.staked)+' pts</strong> to &ldquo;'+(mine.option==='yes'?def.yes:def.no)+'&rdquo;. Awaiting resolution.</div>';
      } else {
        body += '<div class="field" style="margin-top:6px;"><label for="stakeInput">Points to commit</label><input class="mono" id="stakeInput" type="number" min="10" max="'+balance()+'" value="'+stakeAmt+'"></div>'
          + '<div class="chip-row">'
          + [25,50,100,250].map(v=>'<button data-chip="'+v+'">'+v+'</button>').join('')
          + '<button data-chip="max">Max</button></div>'
          + '<button class="btn btn-primary btn-block" id="btnPlacePrediction" '+(sel&&callsLeftToday()>0?'':'disabled')+'>Make your call</button>'
          + '<p class="hint" style="margin:8px 0 0; text-align:center;">'+(state.plusTier==='pro' ? 'Unlimited daily calls' : callsLeftToday()+' of '+dailyCallCap()+' daily calls left &middot; '+(state.plus?'Plus Pro removes the limit':'Plus raises it to '+DAILY_CALL_LIMITS.plus))+'</p>';
      }
      body += '<details class="demo-ctl"><summary>Demo: simulate the real&#8209;world result</summary><div class="inner">'
        + '<p class="hint" style="margin:0;">Stands in for the Foresight Resolution Service ingesting a verified outcome. Pick what actually happened:</p>'
        + '<button class="btn btn-sm" data-resolve="yes">Resolve as: '+def.yes+'</button>'
        + '<button class="btn btn-sm" data-resolve="no">Resolve as: '+def.no+'</button>'
        + '</div></details>';
    }

    const comments = ensureComments(id);
    body += '<div class="discuss"><h4>Debate &middot; '+comments.length+'</h4>'
      + comments.map((cm,i)=>{
          const badge = cm.side ? '<span class="side-badge '+cm.side+'">'+esc(cm.side==='yes'?def.yes:def.no)+'</span>' : '';
          return '<div class="comment-row"><div class="row-top"><span class="who">'+esc(cm.who)+'</span>'+badge+'<span class="t">'+cm.hrsAgo+'h ago</span></div>'
            + (cm.txt ? '<span class="txt">'+esc(cm.txt)+'</span>' : '')
            + renderCommentMedia(cm)
            + '<button class="like-btn '+(cm.likedByMe?'on':'')+'" data-like-comment="'+i+'">&#9829; '+(cm.likes||0)+'</button>'
            + (cm.media ? '<button class="report-link" data-report-comment="'+i+'" '+(cm.media.reported?'disabled':'')+'>'+(cm.media.reported?'Reported':'Report')+'</button>' : '')
            + '</div>';
        }).join('')
      + renderCommentForm()
      + '</div>';

    return { title: def.title, body };
  }
  function optBtn(key,label,pct,mult,sel,mine){
    const disabled = !!mine;
    return '<button class="opt-btn '+key+' '+(sel===key?'sel':'')+'" data-opt="'+key+'" '+(disabled?'disabled style="opacity:.6;"':'')+'>'
      + '<span class="lbl">'+esc(label)+'</span><span class="odds">'+pct+'%</span>'
      + '<span style="font-size:10px; color:var(--ink-muted); font-weight:600;">'+mult+'&times; return if correct</span></button>';
  }

  /* ============ ledger / leaderboard / wallet / profile ============ */
  const LEDGER_META = {
    signup:{label:'Signup bonus', color:'good'}, kyc:{label:'KYC bonus', color:'good'},
    checkin:{label:'Daily check‑in', color:'good'}, stake:{label:'Points committed', color:'muted'},
    win:{label:'Call correct', color:'good'}, lose:{label:'Call resolved', color:'muted'}, redeem:{label:'Prize redeemed', color:'muted'}
  };
  function ledgerIcon(type){
    const good = type==='win'||type==='signup'||type==='kyc'||type==='checkin';
    const bg = good ? 'color-mix(in srgb, var(--status-good) 18%, transparent)' : 'var(--surface-3)';
    const fg = good ? 'var(--status-good)' : 'var(--ink-muted)';
    const glyph = type==='stake' ? '&#8722;' : type==='redeem' ? '&#127873;' : good ? '&#8593;' : '&#8226;';
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

  // Campaign-scoped leaderboard: ranks players on ONE sponsored
  // question's net points only, not the global all-time balance
  // renderLeaderboard() below uses. The named top 5 are scored with the
  // exact same pari-mutuel payout math as any other topic; the field behind
  // them is simulated (same illustrative-data pattern as LB_SEED/tickLive
  // elsewhere) purely so rank arithmetic ("you placed #N of ~3,180") has
  // real numbers to count against. A production build would score this
  // against live multi-user data instead.
  function campaignField(campaignId){
    const camp = CAMPAIGNS[campaignId];
    const c = camp && state.contests.find(x=>x.id===camp.contestId);
    if(!camp || !c || c.status!=='resolved') return null;
    const total = c.pool.yes + c.pool.no, winPool = c.pool[c.resolvedOption];
    const mult = winPool ? total/winPool : 1;
    const top5 = (CAMPAIGN_TOP5[campaignId]||[]).map(p=>({
      name:p.name, staked:p.staked, net:Math.round(p.staked*(mult-1)), verified:true
    }));
    const rng = mulberry32(hashStr(campaignId));
    const restN = Math.max(0, camp.entrants - top5.length);
    const rest = [];
    for(let i=0;i<restN;i++){
      const stake = Math.round(15 + Math.pow(rng(),5)*900);
      const correct = rng() < camp.correctShare;
      rest.push(correct ? Math.round(stake*(mult-1)) : -stake);
    }
    return { camp, contest:c, mult, top5, rest };
  }
  function renderCampaignSheet(campaignId){
    const camp = CAMPAIGNS[campaignId];
    const c = state.contests.find(x=>x.id===camp.contestId);
    const def = contestDef(camp.contestId);
    const resolved = c.status==='resolved';
    const mine = state.predictions[camp.contestId];

    let body = '<span class="sponsor-chip"><span class="mk">'+esc(camp.sponsor[0])+'</span>Sponsored by '+esc(camp.sponsor)+'</span>'
      + '<h3 style="font-size:15.5px; margin-top:6px;">'+esc(camp.title)+'</h3>'
      + '<p style="font-size:12.5px; color:var(--ink-2); line-height:1.55;">'+esc(camp.blurb)+'</p>';

    body += '<div style="display:flex; flex-direction:column; gap:8px; margin-top:12px;">'
      + camp.prizes.map(p=>'<div class="winner-card" style="flex-direction:row; align-items:center; gap:10px;"><span class="ic">'+p.icon+'</span><div style="flex:1; display:flex; flex-direction:column; gap:2px;"><b>Rank '+p.rank+' &mdash; '+esc(p.name)+'</b><span class="hint">'+esc(p.value)+'</span></div></div>').join('')
      + '</div>';

    body += '<details class="demo-ctl"><summary>How is the campaign leaderboard calculated?</summary><div class="inner">'
      + '<p class="hint" style="margin:0;">Ranked by <strong>'+esc(camp.rankedBy)+'</strong> &mdash; the same pari&#8209;mutuel payout every topic uses (points committed &times; total&frasl;winning pool), just scored on this one question. Real prizes for the top 5, never purchased or point&#8209;redeemed &mdash; fulfilment requires the same selfie/KYC verification every other prize in this app requires.</p>'
      + '</div></details>';

    if(!resolved){
      body += '<div class="callout" style="margin-top:12px;">This campaign question is still open &mdash; the leaderboard finalizes once it resolves.'+(mine?'':' You haven&rsquo;t foreseen on it yet.')+'</div>'
        + '<button class="btn btn-primary btn-block" data-open-contest="'+camp.contestId+'" style="margin-top:8px;">'+(mine?'View the question':'Make your call')+'</button>';
    } else {
      const field = campaignField(campaignId);
      const winLabel = c.resolvedOption==='yes' ? def.yes : def.no;
      body += '<div class="callout" style="margin-top:12px;"><strong>Resolved: '+esc(winLabel)+'</strong> &middot; '+fmtNum(camp.entrants)+' players on this campaign question.</div>';

      // Rank the real signed-in user against the FULL field (named top 5 +
      // the simulated rest) for their overall placement — then, separately,
      // merge them into the displayed top-5 table itself if their net
      // actually clears it, so the table never shows a stale name outranked
      // by the real player sitting just below it.
      const myNet = mine ? state.ledger.filter(e=>e.contestId===camp.contestId).reduce((s,e)=>s+e.amount,0) : null;
      const candidates = field.top5.map(p=>({name:p.name, net:p.net, verified:true, me:false}))
        .concat(mine ? [{name:state.user.name||'You', net:myNet, verified:state.selfieVerified, me:true}] : []);
      candidates.sort((a,b)=>b.net-a.net);
      const displayTop5 = candidates.slice(0,5);

      const head = '<div class="lb-head"><span class="rank">#</span><span class="av"></span><span class="nm">Player</span><span class="rw">Prize</span><span class="pt">Pts won</span></div>';
      const rows = displayTop5.map((p,i)=>{
        const prize = camp.prizes[i];
        return '<div class="lb-row '+(p.me?'me':'')+'"><span class="rank">'+(i+1)+'</span><span class="av">'+(p.me?'YOU':esc(p.name.split(' ').map(w=>w[0]).join('')))+'</span><span class="nm"><b>'+(p.me?'You':esc(p.name))+'</b> '+(p.verified?verifiedBadgeIcon():'')+'</span><span class="rw">'+esc(prize.icon)+' '+esc(prize.name)+'</span><span class="pt mono">+'+fmtNum(p.net)+'</span></div>';
      }).join('');

      body += '<h4 style="font-size:12.5px; margin:14px 0 4px; color:var(--ink-2);">Campaign leaderboard &mdash; top 5</h4>'
        + '<div class="card" style="padding:6px 10px;">'+head+rows+'</div>';

      if(mine){
        const beatenBy = field.top5.map(p=>p.net).concat(field.rest).filter(v=>v>myNet).length;
        const myRank = beatenBy + 1;
        const inTop5 = myRank<=5;
        body += '<div class="callout" style="margin-top:10px;'+(inTop5?' border-color:var(--accent);':'')+'">'
          + '<strong>Your result:</strong> '+(myNet>=0?'+':'')+fmtNum(myNet)+' pts on this question &mdash; placed <strong>#'+fmtNum(myRank)+'</strong> of '+fmtNum(camp.entrants+1)+'.'
          + (inTop5
              ? (state.selfieVerified
                  ? ' You&rsquo;re inside the prize band &mdash; your KYC is verified, so fulfilment can proceed.'
                  : ' You&rsquo;re inside the prize band, but prize fulfilment needs your identity verified first &mdash; complete selfie verification in Profile to claim it.')
              : ' Outside the top 5 this time &mdash; a bigger foresight on a correct call is what closes that gap, same as any other topic.')
          + '</div>';
      } else {
        body += '<p class="hint" style="margin-top:8px;">You didn&rsquo;t make a foresight on this campaign&rsquo;s question, so you&rsquo;re not scored on it.</p>';
      }
      body += '<p class="news-note" style="margin-top:10px;">Prototype note: the named top 5 use the same live payout math as every topic; the remaining field behind them is simulated so rank arithmetic has real numbers to count against &mdash; a production build would score this against live multi&#8209;user data, with fulfilment reviewed against KYC before any prize ships.</p>';
    }

    return { title: camp.title, body };
  }
  function renderLeaderboard(){
    const list = LB_SEED.map(p=>({name:p.name, pts:(state.lbPoints&&state.lbPoints[p.name]!==undefined)?state.lbPoints[p.name]:p.pts, me:false, verified:!!p.verified})).concat([{name:state.user.name||'You', pts:balance(), me:true, verified:state.selfieVerified}]);
    list.sort((a,b)=>b.pts-a.pts);
    const head = '<div class="lb-head"><span class="rank">#</span><span class="av"></span><span class="nm">Player</span><span class="rw">Reward unlocked</span><span class="pt">Points</span></div>';
    const rows = list.map((p,i)=>{
      const prize = bestPrizeFor(p.pts);
      const rewardTxt = prize ? esc(prize.short) : 'Keep foreseeing';
      return '<div class="lb-row '+(p.me?'me':'')+'"><span class="rank">'+(i+1)+'</span><span class="av">'+(p.me?'YOU':p.name.split(' ').map(w=>w[0]).join(''))+'</span><span class="nm"><b>'+(p.me?'You':esc(p.name))+(p.verified?' '+verifiedBadgeIcon():'')+'</b>'+rankBadgeChip(p.pts, true)+'</span><span class="rw">'+rewardTxt+'</span><span class="pt mono">'+fmtNum(p.pts)+'</span></div>';
    }).join('');
    return '<h2 style="font-size:16px; margin:14px 0 4px;">Leaderboard</h2><p class="hint" style="margin-bottom:8px;">Reward unlocked shows the highest non&#8209;cash prize each rank could redeem today &mdash; earned, never bought. Top monthly ranks also win Winner Prizes — see Wallet.</p><div class="card" style="padding:6px 10px;">'+head+rows+'</div>';
  }
  function renderWallet(){
    const prizes = PRIZES.map(p=>{
      const owned = state.redeemed[p.id];
      const can = balance() >= p.cost && !owned;
      return '<div class="prize-card"><span class="tag">'+p.tag+'</span><b>'+p.name+'</b><span class="hint">'+p.desc+'</span>'
        + '<span class="cost mono">'+fmtNum(p.cost)+' pts</span>'
        + '<button class="btn btn-sm" data-redeem="'+p.id+'" '+(owned||!can?'disabled':'')+'>'+(owned?'Redeemed':'Redeem')+'</button></div>';
    }).join('');
    const winnerPrizes = WINNER_PRIZES.map(p=>{
      return '<div class="winner-card"><span class="ic">'+p.icon+'</span><span class="tag">'+esc(p.tag)+'</span><b>'+esc(p.name)+'</b><span class="hint">'+esc(p.desc)+'</span><span class="tier">'+esc(p.tier)+'</span></div>';
    }).join('');
    return '<h2 style="font-size:16px; margin:14px 0 4px;">Wallet</h2>'
      + '<div class="balance-card" style="margin-top:8px;"><div class="k">Balance</div><div class="v mono">'+fmtNum(balance())+' pts</div></div>'
      + '<div class="plus-card"><div class="hd"><b style="font-size:13.5px;">Foreseez Plus</b>'+(state.plusTier==='plus'?'<span class="plus-badge">Active</span>':'<span class="plus-badge" style="background:var(--baseline); color:var(--ink-2);">₹99/mo</span>')+'</div>'
      + '<p>Flat monthly access fee — separate from anything you foresee, and never convertible into predictions or prizes. Unlocks an ad&#8209;free feed, a profile badge, a higher daily limit (25 calls a day instead of 10) and deeper accuracy analytics. It never buys or credits Foreseez Points; those stay earn&#8209;only, matching PROGA&rsquo;s Online Social Game path.</p>'
      + (state.plusTier==='plus' ? '<button class="btn btn-sm" disabled>Subscribed</button>' : '<button class="btn btn-primary btn-sm" id="btnSubscribePlus">Subscribe to Plus — ₹99/mo (simulated)</button>')
      + '</div>'
      + '<div class="plus-card"><div class="hd"><b style="font-size:13.5px;">Foreseez Plus Pro</b>'+(state.plusTier==='pro'?'<span class="plus-badge">Active</span>':'<span class="plus-badge" style="background:var(--baseline); color:var(--ink-2);">₹249/mo</span>')+'</div>'
      + '<p>Everything in Plus, with no daily limit on calls, plus early access to new prediction markets — elections, policy, geopolitics — before they open to everyone, and private leagues to run alongside friends. Still a flat access fee, not currency spent inside a prediction.</p>'
      + (state.plusTier==='pro' ? '<button class="btn btn-sm" disabled>Subscribed</button>' : '<button class="btn btn-primary btn-sm" id="btnSubscribePlusPro">Subscribe to Plus Pro — ₹249/mo (simulated)</button>')
      + '</div>'
      + '<div class="plus-card" style="margin-bottom:14px;"><div class="hd"><b style="font-size:13.5px;">Run your own poll</b>'+(state.plus?'<span class="plus-badge">Plus</span>':'<span class="plus-badge" style="background:var(--baseline); color:var(--ink-2);">Plus only</span>')+'</div>'
      + '<p>Ask consumers a Yes/No question of your own. It runs in the live feed and feeds straight into the same real&#8209;time sentiment pool as every other topic.</p>'
      + (state.plus ? '<button class="btn btn-primary btn-sm" id="btnOpenCreatePoll">Create a poll</button>' : '<button class="btn btn-sm" disabled>Subscribe to Plus to unlock</button>')
      + '</div>'
      + renderMyPolls()
      + '<div class="callout" style="margin-bottom:12px;"><strong>Foreseez Points are always earned, never sold.</strong> The only in&#8209;app purchases in this prototype are the Plus and Plus Pro subscriptions above — flat access fees to the app, never currency spent inside a prediction.</div>'
      + '<div class="earn-item"><div><b>Daily check‑in</b><span>Come back once a day</span></div><button class="btn btn-sm" id="btnCheckin" '+(state.checkedIn?'disabled':'')+'>'+(state.checkedIn?'Done':'+50 pts')+'</button></div>'
      + '<div class="earn-item"><div><b>Complete KYC</b><span>Name &amp; age verified</span></div><span class="chip chip-status-good">Earned</span></div>'
      + '<h3 style="font-size:13px; margin:18px 0 4px;">Winner Prizes &mdash; top players</h3>'
      + '<p class="hint" style="margin-bottom:8px;">Awarded — never purchased or point&#8209;redeemed — to the top&#8209;ranked players on the monthly leaderboard. Flagship devices plus free access to leading learning platforms, useful for students and university players using Bharat Foreseez as a study tool.</p>'
      + '<div class="winner-grid" style="margin-bottom:18px;">'+winnerPrizes+'</div>'
      + '<h3 style="font-size:13px; margin:18px 0 4px;">Sponsored Campaigns &mdash; real prizes</h3>'
      + '<p class="hint" style="margin-bottom:8px;">A brand pays to run one question; the top 5 players on that question win prizes the brand supplies directly — separate from the Winner Prizes above.</p>'
      + '<div style="display:flex; flex-direction:column; gap:8px; margin-bottom:18px;">' + Object.values(CAMPAIGNS).map(camp=>{
          const cc = state.contests.find(x=>x.id===camp.contestId);
          const status = cc && cc.status==='resolved' ? 'Resolved — leaderboard final' : 'Open now';
          return '<div class="winner-card" style="flex-direction:row; align-items:center; gap:10px; cursor:pointer;" data-open-campaign="'+camp.id+'"><span class="ic">🏆</span><div style="flex:1;"><b>'+esc(camp.title)+'</b><span class="hint" style="display:block;">Sponsored by '+esc(camp.sponsor)+' &middot; '+status+'</span></div></div>';
        }).join('') + '</div>'
      + '<h3 style="font-size:13px; margin:18px 0 8px;">Redeem &mdash; non‑cash prizes only</h3>'
      + '<div class="prize-grid">'+prizes+'</div>';
  }
  // Rank card: a screenshot-worthy summary of the player's current named
  // badge, built specifically so a proud "Mahadrishta" or "Hall of
  // Famer" has something worth sharing outside the app, not just a number
  // buried in a leaderboard row.
  function renderRankCard(){
    const pts = balance();
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
      + '<button class="btn btn-block" id="btnReset" style="margin-top:16px;">Reset demo</button>'
      + '<p class="hint" style="text-align:center; margin-top:8px;">Clears all prototype activity and returns to onboarding.</p>';
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
      : '<p class="hint">No notifications yet — they&rsquo;ll show up here as markets move.</p>';
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
    if(state.openCampaign){
      const camp = renderCampaignSheet(state.openCampaign);
      sheet.innerHTML = '<div class="sheet-head"><h3 style="font-size:14px; max-width:80%;">Sponsored Campaign</h3><button class="btn btn-ghost btn-sm" id="btnCloseSheet" aria-label="Close">&#10005;</button></div><div class="sheet-body">'+camp.body+'</div>';
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
        addLedger('kyc', 'Verified badge bonus (selfie confirmed)', 100);
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
        const pick = openList.slice().sort((a,b)=>(b.pool.yes+b.pool.no)-(a.pool.yes+a.pool.no))[0];
        state._hookContestId = pick ? pick.id : null;
        state._hookChoice = null;
        state.obStep = 'hook';
        render(); break;
      }
      case 'hookPick': {
        if(state._hookChoice) return;
        const c = state.contests.find(x=>x.id===state._hookContestId);
        if(c){
          c.pool[payload] += 30;
          addLedger('signup','First foresight bonus', 30);
        }
        state._hookChoice = payload;
        render(); break;
      }
      case 'skipHook': { state.obStep='welcome'; render(); break; }
      case 'continueToWelcome': { state.obStep='welcome'; render(); break; }
      case 'enterApp': {
        state.user.signedIn = true;
        addLedger('signup','Welcome bonus', 1000);
        addLedger('kyc','Age & identity verified bonus', 150);
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
        if(callsLeftToday()<=0){ toast('Daily limit of '+dailyCallCap()+' calls reached'+(state.plusTier==='pro'?'':' — upgrade for more')); return; }
        const id = state.openContest, def = contestDef(id), c = state.contests.find(x=>x.id===id);
        addLedger('stake', 'Committed points to “'+def.title+'”', -amt, id);
        c.pool[sel] += amt;
        state.predictions[id] = { option:sel, staked:amt };
        state.callsToday++;
        render(); toast('Call locked in'); break;
      }
      case 'resolve': {
        const id = state.openContest, def = contestDef(id), c = state.contests.find(x=>x.id===id);
        c.status='resolved'; c.resolvedOption = payload;
        const mine = state.predictions[id];
        if(mine){
          if(mine.option===payload){
            const total = c.pool.yes + c.pool.no, winPool = c.pool[payload];
            const payout = Math.round(mine.staked * (total/winPool));
            addLedger('win', 'Correct: “'+def.title+'”', payout, id);
            toast('Call correct — +'+fmtNum(payout)+' pts');
          } else {
            addLedger('lose', 'Resolved: “'+def.title+'” — no reward', 0, id);
            toast('Resolved — no reward this time');
          }
        } else { toast('Topic resolved'); }
        render(); break;
      }
      case 'checkin': { addLedger('checkin','Daily check‑in', 50); state.checkedIn=true; render(); toast('+50 pts'); break; }
      case 'redeem': {
        const p = PRIZES.find(x=>x.id===payload);
        if(balance() < p.cost) return;
        addLedger('redeem', 'Redeemed: '+p.name, -p.cost);
        state.redeemed[p.id] = true;
        render(); toast('Redeemed: '+p.name); break;
      }
      case 'reset': {
        state = defaultState(); render(); toast('Demo reset'); break;
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
      btnBell:()=>place('toggleBell'), btnTheme:()=>toggleTheme(), btnSubscribePlus:()=>place('subscribePlus'), btnSubscribePlusPro:()=>place('subscribePlusPro'), btnPostComment:()=>place('postComment'),
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
    const cardOpen = t.closest('[data-open-contest]'); if(cardOpen){ place('openContest', cardOpen.dataset.openContest); return; }
    const campOpen = t.closest('[data-open-campaign]'); if(campOpen){ place('openCampaign', campOpen.dataset.openCampaign); return; }
    const interestBtn = t.closest('button[data-interest]'); if(interestBtn){ place('toggleInterest', interestBtn.dataset.interest); return; }
    const hookBtn = t.closest('button[data-hook]'); if(hookBtn){ place('hookPick', hookBtn.dataset.hook); return; }
    const optBtnEl = t.closest('button[data-opt]'); if(optBtnEl && !optBtnEl.disabled){ place('selectOpt', optBtnEl.dataset.opt); return; }
    const chipBtn = t.closest('button[data-chip]'); if(chipBtn){ place('chip', chipBtn.dataset.chip); return; }
    const resolveBtn = t.closest('button[data-resolve]'); if(resolveBtn){ place('resolve', resolveBtn.dataset.resolve); return; }
    const redeemBtn = t.closest('button[data-redeem]'); if(redeemBtn && !redeemBtn.disabled){ place('redeem', redeemBtn.dataset.redeem); return; }
    const pollHrsBtn = t.closest('button[data-poll-hrs]'); if(pollHrsBtn){ place('pollHrs', pollHrsBtn.dataset.pollHrs); return; }
    const likeBtn = t.closest('button[data-like-comment]'); if(likeBtn){ place('likeComment', likeBtn.dataset.likeComment); return; }
    const reportBtn = t.closest('button[data-report-comment]'); if(reportBtn && !reportBtn.disabled){ place('reportComment', reportBtn.dataset.reportComment); return; }
    if(t.id==='sheetBackdrop') place('closeSheet');
  });
  document.getElementById('sheetBackdrop').addEventListener('click', ()=>place('closeSheet'));
  document.body.addEventListener('keydown', function(e){
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


  /* ============ live-ticking markets ============ */
  function tickLive(){
    if(!state.user.signedIn) return;
    const openContests = state.contests.filter(c=>c.status==='open');
    if(!openContests.length) return;
    const c = openContests[Math.floor(Math.random()*openContests.length)];
    const def = contestDef(c.id);
    const side = Math.random() < 0.5 ? 'yes' : 'no';
    const amt = 20 + Math.floor(Math.random()*180);
    c.pool[side] += amt;
    const total = c.pool.yes + c.pool.no;
    const pct = Math.round((c.pool[side]/total)*100);
    const person = LB_SEED[Math.floor(Math.random()*LB_SEED.length)];
    state.lbPoints[person.name] = (state.lbPoints[person.name]||0) + Math.floor(amt*0.15);
    pushActivity('<b>'+esc(person.name)+'</b> foresaw &ldquo;'+esc(side==='yes'?def.yes:def.no)+'&rdquo; in '+esc(def.title));
    if(Math.random() < 0.35){
      pushNotification('New activity on &ldquo;'+def.title+'&rdquo; — now '+pct+'% '+(side==='yes'?def.yes:def.no)+'.');
    }
    if(Math.random() < 0.25){
      const n = NEWS_SEED[Math.floor(Math.random()*NEWS_SEED.length)];
      state.newsFeed = [{cat:n.cat, text:n.text, minsAgo:0}, ...(state.newsFeed||[])].slice(0,12);
    }
    render();
  }
  setInterval(tickLive, 17000);

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
        { id:'lg-seed-1', type:'signup', label:'Welcome bonus', amount:1000, balanceAfter:1000, contestId:null, ts:timeNow() },
        { id:'lg-seed-2', type:'kyc', label:'Age & identity verified bonus', amount:150, balanceAfter:1150, contestId:null, ts:timeNow() }
      ]
    };
  }
  function start(initialData){
    state = Object.assign(defaultState(), initialData||{});
    if(!SHOW_ONBOARDING && !(initialData && initialData.user)){ Object.assign(state, demoSignedIn()); }
    render();
  }
  if(window.claude && window.claude.hot && window.claude.hot.ready){
    window.claude.hot.ready(start);
  } else {
    start(window.claude && window.claude.hot ? window.claude.hot.data : null);
  }
  if(window.claude && window.claude.hot && window.claude.hot.snapshot){
    window.claude.hot.snapshot(function(){ return state; });
  }
})();
