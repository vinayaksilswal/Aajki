import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { Poll, Spinner, ErrorBox, Empty } from '../components.jsx';

export default function Topic() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [t, setT] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setT(null); setError(null);
    api.topic(id).then((d) => { if (alive) setT(d); }).catch((e) => { if (alive) setError(e); });
    return () => { alive = false; };
  }, [id]);

  return (
    <>
      <button className="back" onClick={() => navigate(-1)}>← Back</button>
      {error && <ErrorBox error={error} />}
      {!t && !error && <Spinner />}
      {t && (
        <>
          <div className="kicker" style={{ color: 'var(--accent)' }}>{t.short_label || t.category}</div>
          <h1 className="page-title" style={{ marginTop: 4 }}>{t.title}</h1>
          {t.image_url && <img className="cover" src={t.image_url} alt="" />}
          {t.blurb && <p className="note" style={{ marginBottom: 16 }}>{t.blurb}</p>}
          <div className="section-label">{(t.polls?.length || 0)} POLLS</div>
          {(!t.polls || t.polls.length === 0) && <Empty>No polls in this topic.</Empty>}
          {t.polls?.map((p) => <Poll key={p.id} poll={p} />)}
        </>
      )}
    </>
  );
}
