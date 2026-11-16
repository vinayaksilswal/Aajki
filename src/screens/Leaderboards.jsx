import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { Spinner, ErrorBox, Empty, rupees } from '../components.jsx';

export default function Leaderboards() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => { api.leaderboards().then(setData).catch(setError); }, []);

  if (error) return <><h1 className="page-title">Boards</h1><ErrorBox error={error} /></>;
  if (!data) return <><h1 className="page-title">Boards</h1><Spinner /></>;

  const boards = data.boards || [];
  return (
    <>
      <h1 className="page-title">Leaderboards</h1>
      {data.today_pool_paise != null && (
        <div className="tile">
          <div className="kicker">Today's pool</div>
          <h3>{rupees(data.today_pool_paise)}</h3>
          {data.copy?.subtitle && <p>{data.copy.subtitle}</p>}
        </div>
      )}
      {boards.length === 0 && <Empty>No active boards.</Empty>}
      {boards.map((b) => {
        const s = b.served || {};
        return (
          <Link to={`/board/${b.id}`} className="tile board" key={b.id}
            style={{ textDecoration: 'none', color: 'inherit' }}>
            <div className="art">🎁</div>
            <div className="meta">
              <h3>{b.title}</h3>
              <span>
                {s.round_label ? `${s.round_label} · ` : ''}{s.pitch || b.scope?.label}
                {s.players != null ? ` · ${s.players} players` : ''}
              </span>
            </div>
            {b.status === 'live' && <span className="badge-live">● LIVE</span>}
          </Link>
        );
      })}
    </>
  );
}
