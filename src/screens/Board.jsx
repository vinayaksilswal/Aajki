import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { Spinner, ErrorBox, Empty, rupees } from '../components.jsx';

export default function Board() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setD(null); setError(null);
    api.board(id).then((r) => { if (alive) setD(r); }).catch((e) => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [id]);

  if (error) return <><button className="back" onClick={() => navigate(-1)}>← Back</button><ErrorBox error={error} /></>;
  if (!d) return <><button className="back" onClick={() => navigate(-1)}>← Back</button><Spinner /></>;

  const b = d.board || {};
  const wins = d.recent_wins || [];
  return (
    <>
      <button className="back" onClick={() => navigate(-1)}>← Back</button>
      <h1 className="page-title" style={{ marginTop: 4 }}>{b.title}</h1>
      <div className="tile">
        <div className="kicker">{b.scope?.label || 'Board'}{b.status === 'live' ? ' · LIVE' : ''}</div>
        {b.campaign_pool_paise != null && <h3>{rupees(b.campaign_pool_paise)} pool</h3>}
        {b.campaign_line && <p>{b.campaign_line}</p>}
        {(b.starts_on || b.ends_on) && <p style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>{b.starts_on} → {b.ends_on}</p>}
      </div>

      <div className="section-label">RECENT WINNERS</div>
      {wins.length === 0 && <Empty>No winners yet.</Empty>}
      {wins.map((w, i) => (
        <div className="tile board" key={i}>
          <div className="art" style={{ fontSize: '1rem', fontWeight: 800 }}>{w.tier_name?.[0] || '★'}</div>
          <div className="meta">
            <h3 style={{ fontSize: '0.95rem' }}>{w.name}</h3>
            <span>{w.tier_name || `Tier ${w.tier}`} · {new Date(w.won_at).toLocaleDateString()}</span>
          </div>
          <span className="badge-live" style={{ color: 'var(--accent)' }}>{w.prize_line || rupees(w.prize_each_paise)}</span>
        </div>
      ))}
    </>
  );
}
