// UI strings in English and Hindi (spec s.4: English and Hindi at launch, all text
// externalised for further languages). Add a language by adding a column here.
// Question titles, headlines and comments are shown as written.

const STRINGS = {
  nav_home: ['Home', 'होम'],
  nav_pulse: ['Pulse', 'पल्स'],
  nav_ledger: ['My calls', 'मेरी कॉल'],
  nav_ranks: ['Ranks', 'रैंक'],
  nav_wallet: ['Rewards', 'रिवॉर्ड'],
  nav_profile: ['Profile', 'प्रोफ़ाइल'],
  namaste: ['Namaste', 'नमस्ते'],
  points: ['Foreseez Points', 'फ़ोरसीज़ पॉइंट्स'],
  committed: ['committed to open calls', 'खुली कॉल में लगाए गए'],
  search: ['Search questions…', 'प्रश्न खोजें…'],
  closing_soon: ['Closing soon', 'जल्द बंद'],
  trending: ['Trending', 'ट्रेंडिंग'],
  all: ['All', 'सभी'],
  no_open: ['No open questions right now.', 'अभी कोई खुला प्रश्न नहीं है।'],
  no_open_sub: ['New questions are added through the day — check back soon.', 'दिन भर नए प्रश्न जुड़ते हैं — थोड़ी देर में फिर देखें।'],
  make_call: ['Make your call', 'अपनी कॉल करें'],
  points_to_commit: ['Points to commit', 'लगाने के पॉइंट'],
  how_resolves: ['How this resolves', 'परिणाम कैसे तय होगा'],
  debate: ['Debate', 'चर्चा'],
  post: ['Post', 'पोस्ट'],
  reply: ['Reply', 'जवाब'],
  report: ['Report', 'रिपोर्ट'],
  block: ['Block', 'ब्लॉक'],
  delete: ['Delete', 'हटाएँ'],
  my_calls: ['My calls', 'मेरी कॉल'],
  points_ledger: ['Points ledger', 'पॉइंट लेजर'],
  leaderboards: ['Leaderboards', 'लीडरबोर्ड'],
  daily: ['Today', 'आज'],
  weekly: ['This week', 'इस सप्ताह'],
  all_time: ['All time', 'अब तक'],
  rewards: ['Rewards', 'रिवॉर्ड'],
  daily_checkin: ['Daily check-in', 'दैनिक चेक-इन'],
  daily_quiz: ['Daily quiz', 'दैनिक क्विज़'],
  badges: ['Badges', 'बैज'],
  profile: ['Profile', 'प्रोफ़ाइल'],
  language: ['Language', 'भाषा'],
  take_break: ['Take a break', 'ब्रेक लें'],
  help: ['Help & grievances', 'सहायता और शिकायत'],
  privacy: ['Your data', 'आपका डेटा'],
  pulse_title: ['Pulse — what India foresees', 'पल्स — भारत क्या सोचता है'],
  retry: ['Try again', 'फिर कोशिश करें'],
  loading: ['Loading…', 'लोड हो रहा है…'],
  session_reminder: ['You’ve been here a while. A short break helps.', 'आप काफ़ी देर से यहाँ हैं। थोड़ा ब्रेक लें।'],
};

const LANG_KEY = 'bf-lang';
let lang = 'en';
try { if (localStorage.getItem(LANG_KEY) === 'hi') lang = 'hi'; } catch (_) {}

export function t(key) {
  const row = STRINGS[key];
  if (!row) return key;
  return (lang === 'hi' ? row[1] : row[0]) || row[0];
}

export function getLang() { return lang; }

export function setLang(next) {
  lang = next === 'hi' ? 'hi' : 'en';
  try { localStorage.setItem(LANG_KEY, lang); } catch (_) {}
  document.documentElement.lang = lang;
}

document.documentElement.lang = lang;
