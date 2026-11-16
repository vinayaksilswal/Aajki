import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { Spinner, ErrorBox, Empty } from '../components.jsx';
import { cacheStories } from './storyCache.js';

export default function Stories() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.storiesDaily().then((d) => { cacheStories(d.stories || []); setData(d); }).catch(setError);
  }, []);

  if (error) return <><h1 className="page-title">Stories</h1><ErrorBox error={error} /></>;
  if (!data) return <><h1 className="page-title">Stories</h1><Spinner /></>;

  const stories = data.stories || [];
  return (
    <>
      <h1 className="page-title">Stories</h1>
      <div className="section-label">EDITION {data.edition}</div>
      {stories.length === 0 && <Empty>No stories in this edition.</Empty>}
      {stories.map((s) => (
        <Link key={s.id} to={`/story/${s.id}`} className="tile"
          style={{ display: 'block', textDecoration: 'none', color: 'inherit' }}>
          <div className="kicker">{(s.desk || s.shelf || '').replace(/_/g, ' ')}</div>
          {s.cover?.image_key && <img className="cover" src={s.cover.image_key} alt={s.cover.alt || ''} loading="lazy" style={{ marginTop: 8 }} />}
          <h3>{s.cover?.hook || s.cover?.alt || s.path}</h3>
          <p style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>{s.questions?.length || 0} questions · tap to read</p>
        </Link>
      ))}
    </>
  );
}
