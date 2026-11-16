import { useEffect, useState } from 'react';
import { api, getToken, setToken } from '../api.js';
import { ErrorBox, Spinner, rupees } from '../components.jsx';

// Account screen. Shows live app-config to everyone (public endpoint) and, once signed in,
// the profile and coin wallet. OTP sign-in hits the real backend and sends a real SMS.
export default function Login() {
  const [me, setMe] = useState(null);
  const [config, setConfig] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [step, setStep] = useState('phone');
  const [phone, setPhone] = useState('+91');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.appConfig().then(setConfig).catch(() => {});
    if (getToken()) {
      api.me().then((m) => { setMe(m); api.wallet().then(setWallet).catch(() => {}); }).catch(() => setToken(null));
    }
  }, []);

  async function send() {
    setError(null);
    if (!window.confirm(`Send a real OTP SMS to ${phone}?`)) return;
    setBusy(true);
    try { await api.otpSend(phone.trim()); setStep('code'); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function verify() {
    setError(null); setBusy(true);
    try {
      const r = await api.otpVerify(phone.trim(), code.trim());
      const token = r.token || r.access_token || r.data?.token;
      if (!token) throw new Error('No token field in verify response — see ENDPOINTS.md.');
      setToken(token);
      setMe(await api.me());
      api.wallet().then(setWallet).catch(() => {});
    } catch (e) { setError(e); } finally { setBusy(false); }
  }

  const ConfigTile = config && (
    <div className="tile">
      <div className="kicker">App</div>
      <p style={{ color: 'var(--muted)', fontSize: '0.84rem' }}>
        Build {config.latest_build} · min supported {config.min_supported_build}
        {config.phone_step_required ? ' · phone required' : ''}
      </p>
    </div>
  );

  if (me) {
    return (
      <>
        <h1 className="page-title">Account</h1>
        <div className="tile">
          <h3>{me.display_name || me.name || me.phone || 'Signed in'}</h3>
          <p>{me.handle ? `@${me.handle}` : me.id}</p>
        </div>
        {wallet && (
          <div className="tile">
            <div className="kicker">Wallet</div>
            <h3>◎ {wallet.balance ?? wallet.coins ?? 0}</h3>
            {(wallet.entries || wallet.items || []).slice(0, 5).map((e, i) => (
              <p key={i} style={{ color: 'var(--muted)', fontSize: '0.82rem', margin: '4px 0' }}>
                {e.title || e.reason || e.kind} · {e.amount > 0 ? '+' : ''}{e.amount ?? e.coins}
              </p>
            ))}
          </div>
        )}
        {ConfigTile}
        <button className="btn" onClick={() => { setToken(null); setMe(null); setWallet(null); setStep('phone'); }}>Log out</button>
      </>
    );
  }

  return (
    <>
      <h1 className="page-title">Sign in</h1>
      {error && <ErrorBox error={error} />}
      {step === 'phone' ? (
        <>
          <input className="field" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91XXXXXXXXXX" inputMode="tel" />
          <button className="btn" onClick={send} disabled={busy}>{busy ? 'Sending…' : 'Send OTP'}</button>
        </>
      ) : (
        <>
          <input className="field" value={code} onChange={(e) => setCode(e.target.value)} placeholder="6-digit code" inputMode="numeric" />
          <button className="btn" onClick={verify} disabled={busy}>{busy ? 'Verifying…' : 'Verify & sign in'}</button>
          <button className="back" onClick={() => setStep('phone')}>← Change number</button>
        </>
      )}
      <p className="note">
        Signs in against the real Aajki backend (<code>app.getkalki.com</code>). An OTP is a real SMS
        to the number you enter. Polls, stories and boards work without signing in.
      </p>
      {ConfigTile}
    </>
  );
}
